"""Tests for IaCEngine preview planning, confirmation gates, and control plane audit."""

import pytest
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_control.metering.cost_tracker import CostTracker
from nexcoder_iac.engine import IaCEngine
from nexcoder_iac.models import IaCTarget, IaCTool


def test_engine_generate_and_audit():
    audit_log = AppendOnlyAuditLog()
    cost_tracker = CostTracker()
    engine = IaCEngine(audit_log=audit_log, cost_tracker=cost_tracker)

    artifacts = engine.generate(
        spec="Quero subir uma aplicacao FastAPI com Postgres e nginx",
        target=IaCTarget.LOCAL_COMPOSE,
        actor="developer-alice",
    )

    assert artifacts.target == IaCTarget.LOCAL_COMPOSE
    assert artifacts.tool == IaCTool.COMPOSE
    assert len(artifacts.files) >= 3

    # Check audit log event
    events = audit_log.query()
    assert len(events) == 1
    assert events[0].event_type == "iac.generate"
    assert events[0].actor == "developer-alice"
    assert "local_compose" in events[0].details["target"]

    # Check cost tracker entry
    summaries = cost_tracker.aggregate_by(dimension="person")
    assert "developer-alice" in summaries
    assert summaries["developer-alice"].calls_count == 1


def test_engine_plan_preview():
    engine = IaCEngine()
    artifacts = engine.generate(
        spec="App Django com Postgres na AWS",
        target=IaCTarget.AWS,
        tool=IaCTool.TERRAFORM,
    )

    preview = engine.plan(artifacts, actor="bob", dry_run=True)
    assert preview.target == IaCTarget.AWS
    assert preview.tool == IaCTool.TERRAFORM
    assert len(preview.planned_resources) >= 3
    assert preview.total_estimated_cost_usd_month > 0.0
    assert preview.dry_run is True


def test_engine_apply_gated_by_confirmation():
    engine = IaCEngine()
    artifacts = engine.generate("Simple web app", target=IaCTarget.LOCAL_COMPOSE)
    preview = engine.plan(artifacts)

    # Without confirmation, must raise PermissionError
    with pytest.raises(PermissionError, match="requires explicit confirmation"):
        engine.apply(preview, confirm=False)

    # With confirmation, succeeds
    result = engine.apply(preview, confirm=True, dry_run=True)
    assert result.success is True
    assert result.status == "simulated_applied"
    assert len(result.applied_resources) > 0


def test_engine_destroy_gated_by_confirmation():
    engine = IaCEngine()

    with pytest.raises(PermissionError, match="requires explicit confirmation"):
        engine.destroy(target=IaCTarget.AWS, resource_name="production-app", confirm=False)

    result = engine.destroy(target=IaCTarget.AWS, resource_name="production-app", confirm=True, dry_run=True)
    assert result.success is True
    assert result.status == "simulated_destroyed"
