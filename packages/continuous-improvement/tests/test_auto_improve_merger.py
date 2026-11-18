"""Unit tests for merge engine safety gates, quota checks, budget limits, and audit trails."""

from pathlib import Path

import pytest
from nexcoder_continuous_improvement.auto_improve.merger import AutoMergeEngine
from nexcoder_continuous_improvement.auto_improve.models import (
    AgentExecutionResult,
    SafetyViolationError,
    VerificationResult,
)
from nexcoder_continuous_improvement.auto_improve.quota import DailyQuotaTracker
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_control.metering.budgets import BudgetPolicy


def make_agent_result(all_green: bool = True, branch: str = "feat/auto-issue-10") -> AgentExecutionResult:
    return AgentExecutionResult(
        issue_id=10,
        branch_name=branch,
        success=all_green,
        verification=VerificationResult(
            tests_passed=all_green,
            lint_passed=all_green,
            no_emoji_passed=all_green,
            no_internal_passed=all_green,
        ),
        files_changed=["pkg/file.py"],
    )


def test_merge_engine_successful_develop_merge(tmp_path: Path) -> None:
    audit_log = AppendOnlyAuditLog()
    quota_tracker = DailyQuotaTracker(max_daily_merges=5)
    engine = AutoMergeEngine(repo_dir=tmp_path, quota_tracker=quota_tracker, audit_log=audit_log)

    res = make_agent_result(all_green=True)
    decision = engine.evaluate_and_merge(res, target_branch="develop")

    assert decision.allowed is True
    assert decision.target_branch == "develop"
    assert decision.merge_commit_sha is not None
    assert decision.audit_event_hash is not None

    assert quota_tracker.get_used_today() == 1
    assert len(audit_log._events) == 1
    assert audit_log._events[0].event_type == "auto_merge_develop"
    assert audit_log.verify_integrity()[0] is True


def test_safety_guardrails_strictly_block_main_merge(tmp_path: Path) -> None:
    audit_log = AppendOnlyAuditLog()
    engine = AutoMergeEngine(repo_dir=tmp_path, audit_log=audit_log)
    res = make_agent_result(all_green=True)

    with pytest.raises(SafetyViolationError, match="Target branch 'main' is protected"):
        engine.evaluate_and_merge(res, target_branch="main")

    with pytest.raises(SafetyViolationError, match="Target branch 'master' is protected"):
        engine.evaluate_and_merge(res, target_branch="master")

    # Safety violation must be recorded in audit log
    assert any(e.event_type == "safety_violation_blocked" for e in audit_log._events)
    assert audit_log.verify_integrity()[0] is True


def test_safety_guardrails_prevent_force_merge(tmp_path: Path) -> None:
    engine = AutoMergeEngine(repo_dir=tmp_path)
    res = make_agent_result(all_green=True)

    with pytest.raises(SafetyViolationError, match="Force operations and force push are strictly prohibited"):
        engine.evaluate_and_merge(res, target_branch="develop", force=True)


def test_merge_blocked_when_verification_fails(tmp_path: Path) -> None:
    audit_log = AppendOnlyAuditLog()
    engine = AutoMergeEngine(repo_dir=tmp_path, audit_log=audit_log)
    res = make_agent_result(all_green=False)

    decision = engine.evaluate_and_merge(res, target_branch="develop")

    assert decision.allowed is False
    assert "Verification failed" in decision.reason
    assert any(e.event_type == "merge_rejected_verification" for e in audit_log._events)


def test_merge_blocked_when_daily_quota_exhausted(tmp_path: Path) -> None:
    audit_log = AppendOnlyAuditLog()
    quota_tracker = DailyQuotaTracker(max_daily_merges=1)
    quota_tracker.record_merge()  # use up the 1 merge

    engine = AutoMergeEngine(repo_dir=tmp_path, quota_tracker=quota_tracker, audit_log=audit_log)
    res = make_agent_result(all_green=True)

    decision = engine.evaluate_and_merge(res, target_branch="develop")

    assert decision.allowed is False
    assert "Daily automated merge limit reached" in decision.reason
    assert any(e.event_type == "merge_rejected_quota" for e in audit_log._events)


def test_merge_blocked_when_budget_hard_limit_exceeded(tmp_path: Path) -> None:
    audit_log = AppendOnlyAuditLog()
    policy = BudgetPolicy(
        dimension="agent",
        entity_id="continuous-improvement",
        limit_usd=10.0,
        enforce_hard_limit=True,
    )
    engine = AutoMergeEngine(
        repo_dir=tmp_path,
        audit_log=audit_log,
        budget_policy=policy,
        current_spend_usd=9.50,
    )
    res = make_agent_result(all_green=True)

    # Cost of 1.00 would bring total to 10.50 > 10.00
    decision = engine.evaluate_and_merge(res, target_branch="develop", estimated_cost_usd=1.00)

    assert decision.allowed is False
    assert "Budget hard limit exceeded" in decision.reason
    assert any(e.event_type == "merge_rejected_budget" for e in audit_log._events)
