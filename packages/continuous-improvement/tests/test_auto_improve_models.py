"""Unit tests for auto-improvement domain models and verification structures."""

from nexcoder_continuous_improvement.auto_improve.models import (
    AutoIssue,
    DailyLimitExceededError,
    MergeDecision,
    SafetyViolationError,
    VerificationFailedError,
    VerificationResult,
)
from nexcoder_continuous_improvement.issues.planning_bridge import FindingCategory


def test_verification_result_all_green() -> None:
    res = VerificationResult(
        tests_passed=True,
        lint_passed=True,
        no_emoji_passed=True,
        no_internal_passed=True,
    )
    assert res.is_all_green is True
    assert res.failure_summary() == []


def test_verification_result_failures() -> None:
    res = VerificationResult(
        tests_passed=False,
        tests_output="1 failed test",
        lint_passed=False,
        lint_output="E501 line too long",
        no_emoji_passed=False,
        no_emoji_output="Found emoji",
        no_internal_passed=False,
        no_internal_output="Found internal ref",
    )
    assert res.is_all_green is False
    summary = res.failure_summary()
    assert len(summary) == 4
    assert any("tests:" in s for s in summary)
    assert any("lint:" in s for s in summary)
    assert any("emoji:" in s for s in summary)
    assert any("internal_refs:" in s for s in summary)


def test_auto_issue_properties() -> None:
    issue = AutoIssue(
        issue_id=42,
        title="Resolve debt",
        body="Given X When Y Then Z",
        category=FindingCategory.TODO_DEBT,
        labels=["auto", "type:todo_debt"],
    )
    assert issue.issue_id == 42
    assert "auto" in issue.labels
    assert issue.status == "open"


def test_merge_decision() -> None:
    dec = MergeDecision(
        allowed=True,
        reason="All green",
        target_branch="develop",
        source_branch="feat/auto-issue-42",
        merge_commit_sha="abcdef123456",
    )
    assert dec.allowed is True
    assert dec.target_branch == "develop"
    assert dec.merge_commit_sha == "abcdef123456"


def test_exception_types() -> None:
    assert issubclass(SafetyViolationError, RuntimeError)
    assert issubclass(DailyLimitExceededError, RuntimeError)
    assert issubclass(VerificationFailedError, RuntimeError)
