"""Round-robin over several API keys with per-key cooldown.

When a key answers 429 (quota), it is suspended for as long as the provider
asked (``retry in Ns``) and the next free key is used immediately. Transient
server errors (500, 503, 504, timeouts) rotate with a short cooldown. Any other
error propagates, because retrying it would only waste money.

The whole operation has a time budget, so a request never keeps hammering
exhausted quotas for minutes.

Ported and generalised from the Gemini key rotation used in production at ApoIA.
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
    """Return 'quota', 'model', 'transient' or 'fatal' for a provider error message."""
    msg = message.lower()
    if "429" in msg or "resource_exhausted" in msg or "quota" in msg or "rate limit" in msg:
        return "quota"
    if "404" in msg or "not found" in msg or "not supported" in msg:
        return "model"
    if any(t in msg for t in ("500", "503", "504", "unavailable", "deadline", "timed out", "timeout",
                              "internal error", "overloaded")):
        return "transient"
    return "fatal"


def requested_wait(message: str, attempt: int) -> float:
    match = re.search(r"retry in (\d+(?:\.\d+)?)s", message.lower())
    if match:
        return float(match.group(1)) + 1.0
    return 2.0 * (attempt + 1)


class RotatingChatModel(BaseChatModel):
    """A chat model that spreads calls across equivalent instances (one per key)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    deadline_seconds: float = 90.0
    max_attempts: int = 12

    _instances: list[BaseChatModel] = PrivateAttr()
    _cursor: int = PrivateAttr(default=0)
    _cooldown_until: dict[int, float] = PrivateAttr(default_factory=dict)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def __init__(self, instances: list[BaseChatModel], **kwargs: Any):
        super().__init__(**kwargs)
        if not instances:
            raise ValueError("RotatingChatModel needs at least one instance")
        self._instances = list(instances)

    @property
    def _llm_type(self) -> str:
        return "rotating"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return RotatingChatModel([m.bind_tools(tools, **kwargs) for m in self._instances])

    # Selection -----------------------------------------------------------

    def _next(self) -> tuple[int, BaseChatModel]:
        now = time.monotonic()
        with self._lock:
            total = len(self._instances)
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
            if len(self._cooldown_until) < len(self._instances):
                return 0.0
            future = [t - now for t in self._cooldown_until.values() if t > now]
            return min(future) if len(future) == len(self._instances) else 0.0

    def _handle(self, exc: Exception, idx: int, attempt: int) -> bool:
        """Apply cooldown for a failure. Return False when the error must propagate."""
        kind = classify_error(str(exc))
        if kind == "quota":
            self._cool(idx, requested_wait(str(exc), attempt))
        elif kind == "model":
            self._cool(idx, 300.0)
        elif kind == "transient":
            self._cool(idx, min(2.0 * (attempt + 1), 15.0))
        else:
            return False
        logger.warning("model instance %s failed (%s), rotating: %s", idx, kind, exc)
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
