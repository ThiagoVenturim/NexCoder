"""Cost aggregation per app, person, agent, and pipeline."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any, Literal

from nexcoder_core.observability.pricing import cost_usd
from pydantic import BaseModel, Field

DimensionType = Literal["app", "person", "agent", "pipeline"]


class CostEntry(BaseModel):
    """Normalized cost event with multi-dimensional attribution."""

    app_id: str = "default_app"
    person_id: str = "anonymous"
    agent_id: str = "generic_agent"
    pipeline_id: str = "adhoc_pipeline"
    model: str = "unknown"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class DimensionSummary(BaseModel):
    """Aggregated financial summary for an entity under a given dimension."""

    dimension: DimensionType
    entity_id: str
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    calls_count: int = 0
    spend_by_model: dict[str, float] = Field(default_factory=dict)


class CostTracker:
    """Thread-safe multi-dimensional cost accumulator."""

    def __init__(self) -> None:
        self._entries: list[CostEntry] = []
        self._lock = threading.Lock()

    def record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        app_id: str | None = None,
        person_id: str | None = None,
        agent_id: str | None = None,
        pipeline_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CostEntry:
        """Record model token consumption, compute cost, and store attributed entry."""
        usd = cost_usd(model, input_tokens, output_tokens)
        entry = CostEntry(
            app_id=app_id or "default_app",
            person_id=person_id or "anonymous",
            agent_id=agent_id or "generic_agent",
            pipeline_id=pipeline_id or "adhoc_pipeline",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=usd,
            metadata=metadata or {},
        )
        with self._lock:
            self._entries.append(entry)
        return entry

    def aggregate_by(
        self,
        dimension: DimensionType,
        since: datetime | None = None,
    ) -> dict[str, DimensionSummary]:
        """Aggregate total spend and tokens grouped by the requested dimension."""
        with self._lock:
            entries = list(self._entries)

        summaries: dict[str, DimensionSummary] = {}

        for entry in entries:
            if since and entry.timestamp < since:
                continue

            entity_id: str
            if dimension == "app":
                entity_id = entry.app_id
            elif dimension == "person":
                entity_id = entry.person_id
            elif dimension == "agent":
                entity_id = entry.agent_id
            elif dimension == "pipeline":
                entity_id = entry.pipeline_id
            else:
                entity_id = "unknown"

            if entity_id not in summaries:
                summaries[entity_id] = DimensionSummary(
                    dimension=dimension,
                    entity_id=entity_id,
                )

            s = summaries[entity_id]
            s.total_cost_usd += entry.cost_usd
            s.total_input_tokens += entry.input_tokens
            s.total_output_tokens += entry.output_tokens
            s.calls_count += 1
            s.spend_by_model[entry.model] = s.spend_by_model.get(entry.model, 0.0) + entry.cost_usd

        return summaries

    def total_spend(self, since: datetime | None = None) -> float:
        """Return overall system-wide spend in USD."""
        with self._lock:
            if since is None:
                return sum(e.cost_usd for e in self._entries)
            return sum(e.cost_usd for e in self._entries if e.timestamp >= since)

    def get_entries(self, limit: int = 100) -> list[CostEntry]:
        """Return the most recent cost entries."""
        with self._lock:
            return list(reversed(self._entries[-limit:]))
