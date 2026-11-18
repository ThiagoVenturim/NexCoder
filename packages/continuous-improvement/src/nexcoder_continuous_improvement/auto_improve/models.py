"""Domain models, verification results, and exceptions for the auto-improvement loop."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from nexcoder_continuous_improvement.issues.planning_bridge import FindingCategory


class SafetyViolationError(RuntimeError):
    """Raised when an operation violates core safety rules (e.g. touching main, force pushing)."""


class DailyLimitExceededError(RuntimeError):
    """Raised when the daily ceiling for automated merges has been reached."""


class VerificationFailedError(RuntimeError):
    """Raised when one or more verification checks fail prior to merge."""


class AutoIssue(BaseModel):
    """Representation of an auto-improvement issue opened on a platform tracker."""

    issue_id: str | int
    title: str
    body: str
    labels: list[str] = Field(default_factory=lambda: ["auto"])
    url: str = ""
    status: str = "open"
    fingerprint: str = ""
    category: FindingCategory = FindingCategory.TODO_DEBT
    layer: str = "core"
    priority: str = "medium"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    """Results from local verification pipeline (tests, lint, emoji check, leak check)."""

    tests_passed: bool = True
    tests_output: str = ""
    lint_passed: bool = True
    lint_output: str = ""
    no_emoji_passed: bool = True
    no_emoji_output: str = ""
    no_internal_passed: bool = True
    no_internal_output: str = ""
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_all_green(self) -> bool:
        """Return True only if all verification gates passed cleanly."""
        return (
            self.tests_passed
            and self.lint_passed
            and self.no_emoji_passed
            and self.no_internal_passed
        )

    def failure_summary(self) -> list[str]:
        """Return human-readable list of failed verification gates."""
        reasons: list[str] = []
        if not self.tests_passed:
            reasons.append(f"tests: {self.tests_output.strip() or 'failed'}")
        if not self.lint_passed:
            reasons.append(f"lint: {self.lint_output.strip() or 'failed'}")
        if not self.no_emoji_passed:
            reasons.append(f"emoji: {self.no_emoji_output.strip() or 'failed'}")
        if not self.no_internal_passed:
            reasons.append(f"internal_refs: {self.no_internal_output.strip() or 'failed'}")
        return reasons


class AgentExecutionResult(BaseModel):
    """Result of automated developer agent execution on a feature branch."""

    issue_id: str | int
    branch_name: str
    success: bool
    commits: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    diff_summary: str = ""
    verification: VerificationResult = Field(default_factory=VerificationResult)
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MergeDecision(BaseModel):
    """Outcome of an evaluation to merge an automated improvement branch into develop."""

    allowed: bool
    reason: str
    target_branch: str = "develop"
    source_branch: str = ""
    merge_commit_sha: str | None = None
    audit_event_hash: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AutoImproveCycleReport(BaseModel):
    """Consolidated summary report of an automated continuous improvement execution cycle."""

    cycle_id: str
    started_at: datetime
    completed_at: datetime
    findings_detected: int = 0
    findings_by_category: dict[str, int] = Field(default_factory=dict)
    issues_created: list[AutoIssue] = Field(default_factory=list)
    branches_evaluated: list[str] = Field(default_factory=list)
    merges_executed: list[str] = Field(default_factory=list)
    merges_blocked: list[str] = Field(default_factory=list)
    quota_used_today: int = 0
    quota_remaining_today: int = 0
    budget_spent_usd: float = 0.0
    audit_chain_length: int = 0
    audit_head_hash: str = ""
    status: str = "completed"
    summary: str = ""
