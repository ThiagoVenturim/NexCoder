from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any


def format_sse_event(data: Any, event: str | None = None, event_id: str | None = None) -> str:
    """Format an SSE message according to the W3C EventSource standard."""
    lines: list[str] = []
    if event:
        lines.append(f"event: {event}")
    if event_id:
        lines.append(f"id: {event_id}")

    payload = json.dumps(data, default=str) if not isinstance(data, str) else data
    for line in payload.splitlines():
        lines.append(f"data: {line}")

    lines.append("\n")
    return "\n".join(lines)


async def pipeline_event_generator(
    pipeline_name: str,
    inputs: dict[str, Any] | None = None,
) -> AsyncGenerator[str, None]:
    """Stream live events for pipeline execution over SSE."""
    yield format_sse_event(
        {"status": "started", "pipeline": pipeline_name, "message": f"Pipeline {pipeline_name} initialized."},
        event="pipeline_started",
    )
    await asyncio.sleep(0.01)

    try:
        from faccoder_interfaces.tools.agents import run_pipeline

        # Yield progress events
        yield format_sse_event(
            {"status": "running", "pipeline": pipeline_name, "stage": "validating_inputs"},
            event="stage_progress",
        )
        await asyncio.sleep(0.01)

        result = run_pipeline(pipeline_name=pipeline_name, inputs=inputs)

        yield format_sse_event(
            result,
            event="pipeline_completed" if result.get("run_status") != "failed" else "pipeline_failed",
        )
    except Exception as exc:
        yield format_sse_event(
            {"status": "error", "pipeline": pipeline_name, "error": str(exc)},
            event="pipeline_error",
        )
