"""Control plane integration adapter for extracting real AI token consumption and costs."""

from __future__ import annotations

from typing import Any

from nexcoder_planning.cost.models import AISpec


def extract_ai_spec_from_tracker(
    cost_tracker: Any,
    app_id: str | None = None,
    pipeline_id: str | None = None,
    default_tier: str = "medium",
) -> AISpec:
    """Extract actual token consumption and dollar spend from a CostTracker instance.

    Integrates with nexcoder_control.metering.cost_tracker.CostTracker.
    """
    if cost_tracker is None:
        return AISpec(model_tier=default_tier)

    total_input = 0
    total_output = 0
    total_usd = 0.0
    calls_count = 0
    spend_by_model: dict[str, float] = {}

    if hasattr(cost_tracker, "aggregate_by"):
        dimension = "app" if app_id else ("pipeline" if pipeline_id else "app")
        summaries = cost_tracker.aggregate_by(dimension)
        target_key = app_id or pipeline_id

        if target_key and target_key in summaries:
            s = summaries[target_key]
            total_input = s.total_input_tokens
            total_output = s.total_output_tokens
            total_usd = s.total_cost_usd
            calls_count = s.calls_count
            spend_by_model = dict(s.spend_by_model)
        else:
            for s in summaries.values():
                total_input += s.total_input_tokens
                total_output += s.total_output_tokens
                total_usd += s.total_cost_usd
                calls_count += s.calls_count
                for m, val in s.spend_by_model.items():
                    spend_by_model[m] = spend_by_model.get(m, 0.0) + val
    elif hasattr(cost_tracker, "_entries"):
        for entry in getattr(cost_tracker, "_entries", []):
            if app_id and getattr(entry, "app_id", None) != app_id:
                continue
            if pipeline_id and getattr(entry, "pipeline_id", None) != pipeline_id:
                continue
            total_input += getattr(entry, "input_tokens", 0)
            total_output += getattr(entry, "output_tokens", 0)
            usd = getattr(entry, "cost_usd", 0.0)
            total_usd += usd
            calls_count += 1
            model = getattr(entry, "model", "unknown")
            spend_by_model[model] = spend_by_model.get(model, 0.0) + usd

    if total_usd > 0:
        cost_usd_val = round(total_usd, 4)
    elif total_input > 0 or total_output > 0:
        cost_usd_val = round((total_input * 1.50 + total_output * 6.00) / 1_000_000, 4)
    else:
        cost_usd_val = None

    return AISpec(
        estimated_tokens_input=total_input or 500_000,
        estimated_tokens_output=total_output or 150_000,
        model_tier=default_tier,
        estimated_runs=calls_count or 1,
        control_plane_cost_usd=cost_usd_val,
        control_plane_metadata={
            "app_id": app_id,
            "pipeline_id": pipeline_id,
            "calls_count": calls_count,
            "spend_by_model": spend_by_model,
        },
    )
