"""Round-robin over several API keys with per-key cooldown.

When a key answers 429 (quota), it is suspended for as long as the provider
asked (``retry in Ns``) and the next free key is used immediately. Transient
server errors (500, 503, 504, timeouts) rotate with a short cooldown. Any other
error propagates, because retrying it would only waste money.

The whole operation has a time budget, so a request never keeps hammering
exhausted quotas for minutes.

Provider API key rotation hardened for production use.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult
from pydantic import ConfigDict, PrivateAttr

logger = logging.getLogger(__name__)


def classify_error(message: str) -> str:
    """Return 'quota', 'context', 'model', 'transient' or 'fatal' for a provider error message."""
    msg = message.lower()
    if any(
        t in msg
        for t in (
            "context_length_exceeded",
            "maximum context length",
            "string too long",
            "too many tokens",
            "prompt is too long",
            "context window",
            "estouro de contexto",
        )
    ):
        return "context"
    if "429" in msg or "resource_exhausted" in msg or "quota" in msg or "rate limit" in msg:
        return "quota"
    if "404" in msg or "not found" in msg or "not supported" in msg:
        return "model"
    if any(
        t in msg
        for t in (
            "500",
            "503",
            "504",
            "unavailable",
            "deadline",
            "timed out",
            "timeout",
            "internal error",
            "overloaded",
        )
    ):
        return "transient"
    return "fatal"


def requested_wait(message: str, attempt: int) -> float:
    msg = message.lower()
    reset_match = re.search(r"resets?\s+in\s+(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", msg)
    if reset_match and any(reset_match.groups()):
        hours = float(reset_match.group(1) or 0)
        minutes = float(reset_match.group(2) or 0)
        seconds = float(reset_match.group(3) or 0)
        total = hours * 3600.0 + minutes * 60.0 + seconds
        if total > 0:
            return total + 1.0

    match = re.search(r"retry\s+in\s+(\d+(?:\.\d+)?)s", msg)
    if match:
        return float(match.group(1)) + 1.0
    return 2.0 * (attempt + 1)


class RotatingChatModel(BaseChatModel):
    """A chat model that spreads calls across equivalent instances (one per key) or fallback chains."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    deadline_seconds: float = 90.0
    max_attempts: int = 12
    fallback_chain: bool = False

    _instances: list[BaseChatModel] = PrivateAttr()
    _model_names: list[str] = PrivateAttr(default_factory=list)
    _cursor: int = PrivateAttr(default=0)
    _cooldown_until: dict[int, float] = PrivateAttr(default_factory=dict)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def __init__(
        self,
        instances: list[BaseChatModel],
        model_names: list[str] | None = None,
        fallback_chain: bool = False,
        **kwargs: Any,
    ):
        super().__init__(fallback_chain=fallback_chain, **kwargs)
        if not instances:
            raise ValueError("RotatingChatModel needs at least one instance")
        self._instances = list(instances)
        self.fallback_chain = fallback_chain
        if model_names:
            self._model_names = list(model_names)
        else:
            self._model_names = [self._extract_name(m, i) for i, m in enumerate(self._instances)]

    @staticmethod
    def _extract_name(model: Any, idx: int) -> str:
        for attr in ("model_name", "model", "_model_name", "_model"):
            val = getattr(model, attr, None)
            if isinstance(val, str) and val:
                return val
        return f"model-{idx}"

    def _get_model_name(self, idx: int) -> str:
        if 0 <= idx < len(self._model_names):
            return self._model_names[idx]
        return f"model-{idx}"

    @property
    def _llm_type(self) -> str:
        return "rotating"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return RotatingChatModel(
            [m.bind_tools(tools, **kwargs) for m in self._instances],
            model_names=self._model_names,
            fallback_chain=self.fallback_chain,
            deadline_seconds=self.deadline_seconds,
            max_attempts=self.max_attempts,
        )

    # Selection -----------------------------------------------------------

    def _next(self) -> tuple[int, BaseChatModel]:
        now = time.monotonic()
        with self._lock:
            total = len(self._instances)
            if self.fallback_chain:
                for idx in range(total):
                    if self._cooldown_until.get(idx, 0.0) <= now:
                        return idx, self._instances[idx]
                idx = min(range(total), key=lambda i: self._cooldown_until.get(i, 0.0))
                return idx, self._instances[idx]

            for _ in range(total):
                idx = self._cursor
                self._cursor = (self._cursor + 1) % total
                if self._cooldown_until.get(idx, 0.0) <= now:
                    return idx, self._instances[idx]
            idx = min(self._cooldown_until, key=self._cooldown_until.get)
            return idx, self._instances[idx]

    def _cool(self, idx: int, seconds: float) -> None:
        with self._lock:
            self._cooldown_until[idx] = time.monotonic() + max(0.0, seconds)

    def _wait_needed(self) -> float:
        now = time.monotonic()
        with self._lock:
            total = len(self._instances)
            if self.fallback_chain:
                for i in range(total):
                    if self._cooldown_until.get(i, 0.0) <= now:
                        return 0.0
                future = [self._cooldown_until.get(i, 0.0) - now for i in range(total)]
                return min(future) if future else 0.0
            if len(self._cooldown_until) < total:
                return 0.0
            future = [t - now for t in self._cooldown_until.values() if t > now]
            return min(future) if len(future) == total else 0.0

    def _handle(self, exc: Exception, idx: int, attempt: int) -> bool:
        """Apply cooldown for a failure. Return False when the error must propagate."""
        kind = classify_error(str(exc))
        if kind == "quota":
            wait_sec = requested_wait(str(exc), attempt)
            self._cool(idx, wait_sec)
        elif kind == "context":
            wait_sec = 300.0
            self._cool(idx, wait_sec)
        elif kind == "model":
            wait_sec = 300.0
            self._cool(idx, wait_sec)
        elif kind == "transient":
            wait_sec = min(2.0 * (attempt + 1), 15.0)
            self._cool(idx, wait_sec)
        else:
            return False

        total = len(self._instances)
        next_idx = (idx + 1) % total if self.fallback_chain else self._cursor
        source_model = self._get_model_name(idx)
        target_model = self._get_model_name(next_idx)

        from faccoder_core.observability.usage import current_meter

        meter = current_meter()
        if meter is not None:
            meter.record_fallback(source_model, target_model, kind, wait_sec)

        logger.warning(
            "model instance %s (%s) failed (%s), rotating to %s (%s) [wait=%.1fs]: %s",
            idx,
            source_model,
            kind,
            next_idx,
            target_model,
            wait_sec,
            exc,
        )
        return True

    def _attempts(self) -> int:
        return max(1, min(len(self._instances) * 3, self.max_attempts))

    # Generation ----------------------------------------------------------

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        start = time.monotonic()
        last: Exception | None = None
        for attempt in range(self._attempts()):
            if attempt >= 2 and time.monotonic() - start > self.deadline_seconds:
                break
            idx, model = self._next()
            try:
                return model._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as exc:  # noqa: BLE001 - classified below
                if not self._handle(exc, idx, attempt):
                    raise
                last = exc
                wait = self._wait_needed()
                if wait:
                    time.sleep(min(wait, max(0.0, self.deadline_seconds - (time.monotonic() - start))))
        raise last or RuntimeError("no attempt was executed")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        start = time.monotonic()
        last: Exception | None = None
        for attempt in range(self._attempts()):
            if attempt >= 2 and time.monotonic() - start > self.deadline_seconds:
                break
            idx, model = self._next()
            try:
                return await model._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as exc:  # noqa: BLE001 - classified below
                if not self._handle(exc, idx, attempt):
                    raise
                last = exc
                wait = self._wait_needed()
                if wait:
                    await asyncio.sleep(min(wait, max(0.0, self.deadline_seconds - (time.monotonic() - start))))
        raise last or RuntimeError("no attempt was executed")
