from __future__ import annotations

import time
from typing import Any

from nexcoder_core.observability.usage import current_meter
from pydantic import BaseModel, Field

from nexcoder_agents.engine.blocks.base import BaseBlock
from nexcoder_agents.engine.models import BlockResult, BlockStatus


class ExecutionLimits(BaseModel):
    """Resource constraints and boundaries for pipeline runs."""

    max_depth: int = 20
    max_budget_usd: float | None = None
    allowed_tools: list[str] | None = None
    timeout_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuardrailBlock(BaseBlock):
    """Enforces execution boundaries: depth, timeout, budget, and tool authorization."""

    def __init__(
        self,
        name: str = "guardrail",
        limits: ExecutionLimits | None = None,
        raise_on_violation: bool = False,
    ) -> None:
        super().__init__(name=name, block_type="guardrail")
        self.limits = limits or ExecutionLimits()
        self.raise_on_violation = raise_on_violation

    def execute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        context = context or {}
        metadata = state.get("metadata", {})
        data = state.get("data", {})
        history = state.get("history", [])

        # 1. Depth check (number of executed blocks in history)
        curr_depth = len(history)
        if curr_depth >= self.limits.max_depth:
            err = (
                f"Guardrail violation: maximum execution depth ({self.limits.max_depth}) "
                f"exceeded (current: {curr_depth})."
            )
            if self.raise_on_violation:
                raise RuntimeError(err)
            return BlockResult(
                block_name=self.name,
                status=BlockStatus.FAILURE,
                error=err,
                message="Pipeline halted by depth guardrail.",
            )

        # 2. Timeout check
        started_at = metadata.get("started_at")
        if self.limits.timeout_seconds is not None and started_at is not None:
            elapsed = time.time() - float(started_at)
            if elapsed >= self.limits.timeout_seconds:
                err = (
                    f"Guardrail violation: timeout of {self.limits.timeout_seconds:.1f}s "
                    f"exceeded (elapsed: {elapsed:.1f}s)."
                )
                if self.raise_on_violation:
                    raise TimeoutError(err)
                return BlockResult(
                    block_name=self.name,
                    status=BlockStatus.FAILURE,
                    error=err,
                    message="Pipeline halted by timeout guardrail.",
                )

        # 3. Budget check (via nexcoder_core meter or data['cost_usd'])
        meter = current_meter()
        current_cost = meter.cost_usd if meter is not None else float(data.get("cost_usd", 0.0))
        if self.limits.max_budget_usd is not None and current_cost >= self.limits.max_budget_usd:
            err = (
                f"Guardrail violation: budget cap of ${self.limits.max_budget_usd:.4f} USD exceeded "
                f"(current cost: ${current_cost:.4f} USD)."
            )
            if self.raise_on_violation:
                raise RuntimeError(err)
            return BlockResult(
                block_name=self.name,
                status=BlockStatus.FAILURE,
                error=err,
                message="Pipeline halted by budget guardrail.",
            )

        # 4. Allowed tools whitelist check
        if self.limits.allowed_tools is not None:
            allowed_set = set(self.limits.allowed_tools)
            requested_tools = data.get("requested_tools") or state.get("inputs", {}).get("requested_tools") or []
            unauthorized = [t for t in requested_tools if t not in allowed_set]
            if unauthorized:
                err = f"Guardrail violation: unauthorized tools requested: {', '.join(unauthorized)}."
                if self.raise_on_violation:
                    raise PermissionError(err)
                return BlockResult(
                    block_name=self.name,
                    status=BlockStatus.FAILURE,
                    error=err,
                    message="Pipeline halted by tool authorization guardrail.",
                )

        return BlockResult(
            block_name=self.name,
            status=BlockStatus.SUCCESS,
            message="All guardrail checks passed successfully.",
        )
