"""Langfuse observability reader for cost, error, latency, and feedback telemetry."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class LangfuseTraceSummary(BaseModel):
    trace_id: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    error: str | None = None
    user_feedback: int | None = None  # 1 for positive, -1 for negative
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tags: list[str] = Field(default_factory=list)


class ObservabilityReport(BaseModel):
    total_calls: int
    total_cost_usd: float
    total_tokens: int
    error_rate: float
    negative_feedback_count: int
    error_clusters: dict[str, int] = Field(default_factory=dict)
    high_latency_calls: list[LangfuseTraceSummary] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class LangfuseLogReader:
    """Ingests and analyzes Langfuse traces to identify operational bottlenecks and errors."""

    def __init__(self, latency_threshold_ms: float = 5000.0) -> None:
        self.latency_threshold_ms = latency_threshold_ms

    def parse_traces_from_jsonl(self, path: str | Path) -> list[LangfuseTraceSummary]:
        """Parse serialized trace lines from a JSONL export."""
        p = Path(path)
        if not p.is_file():
            return []

        traces: list[LangfuseTraceSummary] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                traces.append(LangfuseTraceSummary(**data))
            except Exception:  # noqa: BLE001, S112
                continue
        return traces

    def analyze_traces(self, traces: list[LangfuseTraceSummary]) -> ObservabilityReport:
        """Synthesize metrics, calculate error clusters, and extract optimization targets."""
        if not traces:
            return ObservabilityReport(
                total_calls=0,
                total_cost_usd=0.0,
                total_tokens=0,
                error_rate=0.0,
                negative_feedback_count=0,
                error_clusters={},
                high_latency_calls=[],
                recommendations=["No traces recorded yet."],
            )

        total_calls = len(traces)
        total_cost = sum(t.cost_usd for t in traces)
        total_tokens = sum(t.input_tokens + t.output_tokens for t in traces)

        error_clusters: dict[str, int] = {}
        error_count = 0
        negative_feedback = 0
        high_latency: list[LangfuseTraceSummary] = []

        for t in traces:
            if t.error:
                error_count += 1
                # Cluster errors by simplified prefix
                category = t.error.split(":")[0].strip()[:40]
                error_clusters[category] = error_clusters.get(category, 0) + 1

            if t.user_feedback and t.user_feedback < 0:
                negative_feedback += 1

            if t.latency_ms >= self.latency_threshold_ms:
                high_latency.append(t)

        error_rate = round(error_count / total_calls, 4)

        recommendations: list[str] = []
        if error_rate > 0.05:
            recommendations.append(f"High error rate ({error_rate:.1%}). Investigate error clusters.")
        if negative_feedback > 0:
            recommendations.append(f"{negative_feedback} user negative feedbacks recorded.")
        if high_latency:
            recommendations.append(
                f"{len(high_latency)} calls exceeded latency threshold ({self.latency_threshold_ms}ms)."
            )

        return ObservabilityReport(
            total_calls=total_calls,
            total_cost_usd=round(total_cost, 4),
            total_tokens=total_tokens,
            error_rate=error_rate,
            negative_feedback_count=negative_feedback,
            error_clusters=error_clusters,
            high_latency_calls=high_latency,
            recommendations=recommendations,
        )
