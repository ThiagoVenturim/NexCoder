"""MCP tool metering middleware: tracking per-tool invocations, latency, tokens, and cost."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from faccoder_core.observability.pricing import cost_usd
from pydantic import BaseModel, Field


class ToolInvocationRecord(BaseModel):
    """Record of a single tool execution."""

    tool_name: str
    caller: str = "anonymous"
    app_id: str | None = None
    agent_id: str | None = None
    pipeline_id: str | None = None
    duration_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    success: bool = True
    error_message: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ToolMetrics:
    """Aggregated operational metrics for a specific tool."""

    tool_name: str
    invocations: int = 0
    errors: int = 0
    total_duration_ms: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0

    @property
    def error_rate(self) -> float:
        return (self.errors / self.invocations) if self.invocations > 0 else 0.0

    @property
    def avg_duration_ms(self) -> float:
        return (self.total_duration_ms / self.invocations) if self.invocations > 0 else 0.0

    @property
    def p95_duration_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = math.ceil(0.95 * len(sorted_latencies)) - 1
        return sorted_latencies[max(0, min(idx, len(sorted_latencies) - 1))]


class MCPToolMeter:
    """Middleware and accumulator for MCP tool calls."""

    def __init__(self, default_model: str = "gpt-4.1-mini") -> None:
        self.default_model = default_model
        self._metrics: dict[str, ToolMetrics] = {}
        self._records: list[ToolInvocationRecord] = []
        self._lock = threading.Lock()

    def record_invocation(
        self,
        tool_name: str,
        duration_ms: float,
        success: bool = True,
        caller: str = "anonymous",
        app_id: str | None = None,
        agent_id: str | None = None,
        pipeline_id: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str | None = None,
        error_message: str | None = None,
    ) -> ToolInvocationRecord:
        """Record completed tool invocation with tokens and calculated cost."""
        calculated_cost = cost_usd(model or self.default_model, input_tokens, output_tokens)
        record = ToolInvocationRecord(
            tool_name=tool_name,
            caller=caller,
            app_id=app_id,
            agent_id=agent_id,
            pipeline_id=pipeline_id,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=calculated_cost,
            success=success,
            error_message=error_message,
        )

        with self._lock:
            self._records.append(record)
            if tool_name not in self._metrics:
                self._metrics[tool_name] = ToolMetrics(tool_name=tool_name)
            m = self._metrics[tool_name]
            m.invocations += 1
            if not success:
                m.errors += 1
            m.total_duration_ms += duration_ms
            m.latencies_ms.append(duration_ms)
            # Cap stored individual latencies to prevent memory unbounded growth
            if len(m.latencies_ms) > 2000:
                m.latencies_ms = m.latencies_ms[-1000:]
            m.total_input_tokens += input_tokens
            m.total_output_tokens += output_tokens
            m.total_cost_usd += calculated_cost

        return record

    def wrap_sync(
        self,
        tool_name: str,
        handler: Callable[..., Any],
        caller: str = "anonymous",
        app_id: str | None = None,
        agent_id: str | None = None,
        pipeline_id: str | None = None,
        estimated_input_tokens: int = 0,
        estimated_output_tokens: int = 0,
        model: str | None = None,
    ) -> Callable[..., Any]:
        """Wrap synchronous tool handler function with timing and metrics recording."""

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            success = True
            error_msg: str | None = None
            try:
                return handler(*args, **kwargs)
            except Exception as exc:
                success = False
                error_msg = str(exc)
                raise
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                self.record_invocation(
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    success=success,
                    caller=caller,
                    app_id=app_id,
                    agent_id=agent_id,
                    pipeline_id=pipeline_id,
                    input_tokens=estimated_input_tokens,
                    output_tokens=estimated_output_tokens,
                    model=model,
                    error_message=error_msg,
                )

        return wrapped

    def get_tool_metrics(self, tool_name: str | None = None) -> list[ToolMetrics]:
        """Get copy of metrics for all tools or a single tool."""
        with self._lock:
            if tool_name:
                m = self._metrics.get(tool_name)
                return [m] if m else []
            return list(self._metrics.values())

    def get_recent_records(self, limit: int = 100) -> list[ToolInvocationRecord]:
        """Get recent invocation records in reverse chronological order."""
        with self._lock:
            return list(reversed(self._records[-limit:]))
