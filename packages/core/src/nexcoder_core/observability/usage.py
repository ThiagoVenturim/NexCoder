"""Usage metering: who spent how many tokens, and how much money.

Langfuse answers "how much did this trace cost". This module answers "whose
bill is it": every call adds its tokens and cost to the *current scope* (an API
key, a person, an agent run). Scopes are context variables, so concurrent
requests never mix their numbers.

Usage::

    with usage_scope(owner="team-a", run_id="run-42") as meter:
        model.invoke("...")
    meter.cost_usd, meter.input_tokens
"""

from __future__ import annotations

import contextvars
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from nexcoder_core.observability.pricing import cost_usd


@dataclass
class UsageMeter:
    owner: str = "anonymous"
    run_id: str | None = None
    budget_usd: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    by_model: dict[str, float] = field(default_factory=dict)
    fallbacks: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, model: str, input_tokens: int, output_tokens: int) -> None:
        cost = cost_usd(model, input_tokens, output_tokens)
        with self._lock:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.cost_usd += cost
            self.calls += 1
            self.by_model[model] = self.by_model.get(model, 0.0) + cost

    def record_fallback(
        self,
        source_model: str,
        target_model: str,
        reason: str,
        wait_seconds: float = 0.0,
    ) -> None:
        with self._lock:
            self.fallbacks.append(
                {
                    "source_model": source_model,
                    "target_model": target_model,
                    "reason": reason,
                    "wait_seconds": wait_seconds,
                    "timestamp": time.time(),
                }
            )

    @property
    def over_budget(self) -> bool:
        return self.budget_usd is not None and self.cost_usd >= self.budget_usd


class BudgetExceededError(RuntimeError):
    pass


_current: contextvars.ContextVar[UsageMeter | None] = contextvars.ContextVar("nexcoder_usage", default=None)


def current_meter() -> UsageMeter | None:
    return _current.get()


@contextmanager
def usage_scope(
    owner: str = "anonymous", run_id: str | None = None, budget_usd: float | None = None
) -> Iterator[UsageMeter]:
    meter = UsageMeter(owner=owner, run_id=run_id, budget_usd=budget_usd)
    token = _current.set(meter)
    try:
        yield meter
    finally:
        _current.reset(token)


def _token_counts(response: LLMResult) -> tuple[int, int]:
    """Extract (input, output) tokens from the many shapes providers use."""
    usage = (response.llm_output or {}).get("token_usage") or (response.llm_output or {}).get("usage") or {}
    inp = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    out = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    if inp or out:
        return int(inp), int(out)
    for generations in response.generations:
        for gen in generations:
            meta = getattr(getattr(gen, "message", None), "usage_metadata", None) or {}
            inp += meta.get("input_tokens", 0)
            out += meta.get("output_tokens", 0)
    return int(inp), int(out)


class UsageCallback(BaseCallbackHandler):
    """LangChain callback that feeds the active UsageMeter and enforces its budget."""

    def __init__(self, model: str):
        self.model = model

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        meter = current_meter()
        if meter is not None and meter.over_budget:
            raise BudgetExceededError(
                f"Budget of {meter.budget_usd:.2f} USD reached for '{meter.owner}' (spent {meter.cost_usd:.4f} USD)."
            )

    def on_chat_model_start(self, serialized: dict[str, Any], messages: list, **kwargs: Any) -> None:
        self.on_llm_start(serialized, [], **kwargs)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        meter = current_meter()
        if meter is None:
            return
        inp, out = _token_counts(response)
        meter.add(self.model, inp, out)
