"""Unit tests for Langfuse telemetry and error cluster reader."""

import json
from pathlib import Path

from faccoder_continuous_improvement.observability.langfuse_reader import (
    LangfuseLogReader,
    LangfuseTraceSummary,
)


def test_analyze_traces_error_clustering_and_cost() -> None:
    reader = LangfuseLogReader(latency_threshold_ms=2000.0)

    traces = [
        LangfuseTraceSummary(
            trace_id="tr-1",
            model="gemini-1.5-flash",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.0001,
            latency_ms=800.0,
            user_feedback=1,
        ),
        LangfuseTraceSummary(
            trace_id="tr-2",
            model="gemini-1.5-flash",
            input_tokens=200,
            output_tokens=100,
            cost_usd=0.0002,
            latency_ms=2500.0,
            error="RateLimitError: 429 quota exhausted",
        ),
        LangfuseTraceSummary(
            trace_id="tr-3",
            model="claude-3-5-sonnet",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.003,
            latency_ms=1200.0,
            user_feedback=-1,
        ),
    ]

    report = reader.analyze_traces(traces)

    assert report.total_calls == 3
    assert report.total_tokens == 1150
    assert report.total_cost_usd > 0.003
    assert report.negative_feedback_count == 1
    assert "RateLimitError" in report.error_clusters
    assert len(report.high_latency_calls) == 1
    assert len(report.recommendations) >= 2


def test_parse_traces_from_jsonl(tmp_path: Path) -> None:
    reader = LangfuseLogReader()
    log_file = tmp_path / "langfuse_traces.jsonl"
    entries = [
        {"trace_id": "t1", "model": "m1", "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.001, "latency_ms": 100},
        {
            "trace_id": "t2",
            "model": "m2",
            "input_tokens": 20,
            "output_tokens": 10,
            "cost_usd": 0.002,
            "latency_ms": 200,
        },
    ]
    log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")

    parsed = reader.parse_traces_from_jsonl(log_file)
    assert len(parsed) == 2
    assert parsed[0].trace_id == "t1"
    assert parsed[1].cost_usd == 0.002
