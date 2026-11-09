"""Tests for MCP middleware metering, cost tracking, budgets, and tamper-evident audit."""

from __future__ import annotations

import pytest
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_control.metering.budgets import BudgetAlert, BudgetExceededError, BudgetManager, BudgetPolicy
from nexcoder_control.metering.cost_tracker import CostTracker
from nexcoder_control.metering.mcp_middleware import MCPToolMeter


class TestMCPToolMeter:
    def test_record_invocation(self, tool_meter: MCPToolMeter) -> None:
        record = tool_meter.record_invocation(
            tool_name="code_search",
            duration_ms=45.2,
            success=True,
            caller="agent_1",
            app_id="app_qa",
            input_tokens=1000,
            output_tokens=200,
            model="gpt-4.1-mini",
        )
        assert record.tool_name == "code_search"
        assert record.cost_usd > 0.0

        metrics = tool_meter.get_tool_metrics("code_search")[0]
        assert metrics.invocations == 1
        assert metrics.errors == 0
        assert metrics.avg_duration_ms == 45.2
        assert metrics.total_input_tokens == 1000

    def test_wrap_sync_handler(self, tool_meter: MCPToolMeter) -> None:
        def my_tool(x: int) -> int:
            return x * 2

        wrapped = tool_meter.wrap_sync(
            tool_name="multiplier",
            handler=my_tool,
            caller="tester",
            estimated_input_tokens=50,
            estimated_output_tokens=10,
        )

        assert wrapped(5) == 10
        metrics = tool_meter.get_tool_metrics("multiplier")[0]
        assert metrics.invocations == 1
        assert metrics.errors == 0

    def test_wrap_sync_handler_error(self, tool_meter: MCPToolMeter) -> None:
        def failing_tool() -> None:
            raise ValueError("Tool failed")

        wrapped = tool_meter.wrap_sync(
            tool_name="broken_tool",
            handler=failing_tool,
        )

        with pytest.raises(ValueError, match="Tool failed"):
            wrapped()

        metrics = tool_meter.get_tool_metrics("broken_tool")[0]
        assert metrics.invocations == 1
        assert metrics.errors == 1
        assert metrics.error_rate == 1.0


class TestCostTracker:
    def test_multi_dimensional_aggregation(self, cost_tracker: CostTracker) -> None:
        cost_tracker.record_usage(
            model="gpt-4.1-mini",
            input_tokens=1_000_000,
            output_tokens=500_000,
            app_id="billing_service",
            person_id="alice",
            agent_id="code-intel-agent",
            pipeline_id="pipe_pr_review",
        )
        cost_tracker.record_usage(
            model="gpt-4.1-mini",
            input_tokens=500_000,
            output_tokens=250_000,
            app_id="billing_service",
            person_id="bob",
            agent_id="security-agent",
            pipeline_id="pipe_pr_review",
        )

        # Aggregate by app
        app_summary = cost_tracker.aggregate_by("app")
        assert "billing_service" in app_summary
        assert app_summary["billing_service"].calls_count == 2

        # Aggregate by person
        person_summary = cost_tracker.aggregate_by("person")
        assert "alice" in person_summary
        assert "bob" in person_summary

        # Aggregate by agent
        agent_summary = cost_tracker.aggregate_by("agent")
        assert "code-intel-agent" in agent_summary
        assert "security-agent" in agent_summary

        assert cost_tracker.total_spend() > 0.0


class TestBudgetsAndAlerts:
    def test_threshold_alerts_and_hard_limit(
        self,
        cost_tracker: CostTracker,
        budget_manager: BudgetManager,
    ) -> None:
        alerts_received: list[BudgetAlert] = []
        budget_manager.register_alert_listener(lambda a: alerts_received.append(a))

        policy = BudgetPolicy(
            policy_id="pol_app_1",
            dimension="app",
            entity_id="test_app",
            limit_usd=10.0,
            thresholds=[0.8, 1.0],
            enforce_hard_limit=True,
        )
        budget_manager.add_policy(policy)

        # Spend $5.00 (50%) -> no alert
        cost_tracker.record_usage(
            model="claude-haiku-5-5",
            input_tokens=5_000_000,  # $1/M -> $5.00
            output_tokens=0,
            app_id="test_app",
        )
        budget_manager.evaluate_entity("app", "test_app")
        assert len(alerts_received) == 0

        # Spend additional $3.50 -> Total $8.50 (85%) -> triggers 80% threshold alert
        cost_tracker.record_usage(
            model="claude-haiku-5-5",
            input_tokens=3_500_000,  # $3.50
            output_tokens=0,
            app_id="test_app",
        )
        new_alerts = budget_manager.evaluate_entity("app", "test_app")
        assert len(new_alerts) == 1
        assert new_alerts[0].threshold == 0.8
        assert len(alerts_received) == 1

        # Spend additional $2.00 -> Total $10.50 (105%) -> triggers 100% alert and raises BudgetExceededError
        cost_tracker.record_usage(
            model="claude-haiku-5-5",
            input_tokens=2_000_000,  # $2.00
            output_tokens=0,
            app_id="test_app",
        )
        with pytest.raises(BudgetExceededError, match="hard limit of \\$10.00 exceeded"):
            budget_manager.evaluate_entity("app", "test_app")


class TestAppendOnlyAuditLog:
    def test_cryptographic_chain_integrity(self, audit_log: AppendOnlyAuditLog) -> None:
        audit_log.record_event(
            event_type="auth.login",
            actor="alice",
            action="login",
            resource="control_plane",
            severity="info",
        )
        audit_log.record_event(
            event_type="key.created",
            actor="alice",
            action="create",
            resource="key_1",
            severity="info",
        )
        audit_log.record_event(
            event_type="approval.granted",
            actor="admin",
            action="approve",
            resource="action_deploy",
            severity="warning",
        )

        is_valid, msg = audit_log.verify_integrity()
        assert is_valid is True
        assert "3 events intact" in msg

    def test_tamper_detection_fails_integrity(self, audit_log: AppendOnlyAuditLog) -> None:
        audit_log.record_event("test.event1", "actor", "action", "res")
        audit_log.record_event("test.event2", "actor", "action", "res")

        # Tamper with an event in memory
        audit_log._events[0].action = "tampered_action"

        is_valid, msg = audit_log.verify_integrity()
        assert is_valid is False
        assert "Tampered event payload" in msg or "Hash chain broken" in msg
