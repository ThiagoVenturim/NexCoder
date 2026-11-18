"""Unit tests for reporting and dashboard payload generation."""

from datetime import UTC, datetime

from nexcoder_continuous_improvement.auto_improve.models import AutoImproveCycleReport, AutoIssue
from nexcoder_continuous_improvement.auto_improve.quota import DailyQuotaTracker
from nexcoder_continuous_improvement.auto_improve.reporter import AutoImproveReporter
from nexcoder_continuous_improvement.issues.planning_bridge import FindingCategory
from nexcoder_control.metering.audit import AppendOnlyAuditLog


def test_reporter_markdown_and_dict() -> None:
    quota = DailyQuotaTracker(max_daily_merges=5)
    quota.record_merge()
    audit = AppendOnlyAuditLog()
    evt = audit.record_event(
        event_type="test_event",
        actor="worker",
        action="test",
        resource="res",
    )

    reporter = AutoImproveReporter(quota_tracker=quota, audit_log=audit)

    now = datetime.now(UTC)
    report = AutoImproveCycleReport(
        cycle_id="cycle-test-01",
        started_at=now,
        completed_at=now,
        findings_detected=3,
        findings_by_category={"todo_debt": 2, "security": 1},
        issues_created=[
            AutoIssue(
                issue_id=1,
                title="Fix TODO in auth",
                body="Body",
                category=FindingCategory.TODO_DEBT,
                status="closed",
            )
        ],
        branches_evaluated=["feat/auto-issue-1-fix-todo"],
        merges_executed=["feat/auto-issue-1-fix-todo"],
        merges_blocked=[],
        quota_used_today=1,
        quota_remaining_today=4,
        budget_spent_usd=0.50,
        audit_chain_length=1,
        audit_head_hash=evt.event_hash,
        status="completed",
    )

    md = reporter.build_markdown_report(report)
    assert "# Auto-Improvement Cycle Report" in md
    assert "cycle-test-01" in md
    assert "**Findings Detected**: 3" in md
    assert "**todo_debt**: 2" in md
    assert "**Daily Merges Used**: 1" in md
    assert "**Daily Merges Remaining**: 4" in md

    # Ensure no emoji in markdown report
    from nexcoder_continuous_improvement.auto_improve.agent_bridge import EMOJI_PATTERN
    assert not EMOJI_PATTERN.search(md)

    dashboard = reporter.to_dashboard_dict(report)
    assert dashboard["cycle_id"] == "cycle-test-01"
    assert dashboard["metrics"]["findings_detected"] == 3
    assert dashboard["metrics"]["daily_quota_used"] == 1
    assert dashboard["audit"]["verified"] is True
