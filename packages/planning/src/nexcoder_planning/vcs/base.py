"""Unified abstract base class for repository and VCS management providers."""

from __future__ import annotations

import hmac
import os
from abc import ABC
from typing import Any

from nexcoder_planning.vcs.audit import VCSAuditLogger, get_vcs_audit_logger
from nexcoder_planning.vcs.models import (
    IssueItem,
    PipelineItem,
    PullRequestItem,
    RepoItem,
    VCSCommit,
    VCSDiff,
    VCSLogEntry,
    VCSStatus,
)


class UnsupportedCapabilityError(NotImplementedError):
    """Raised when an operation is requested that the provider does not support."""


class RepoManagementProvider(ABC):  # noqa: B024
    """Common abstraction for repository management and version control systems.

    Supports Azure DevOps, GitLab, Git, SVN, and TortoiseGit through a uniform API,
    enforcing safe secret loading, timing-attack resistant comparisons, and audit tracking.
    """

    name: str = "base"
    capabilities: set[str] = set()

    def __init__(self, audit_logger: VCSAuditLogger | None = None) -> None:
        self.audit_logger = audit_logger or get_vcs_audit_logger()

    @staticmethod
    def secure_compare(val_a: str, val_b: str) -> bool:
        """Constant-time token and digest comparison to protect against timing attacks."""
        if not isinstance(val_a, str) or not isinstance(val_b, str):
            return False
        return hmac.compare_digest(val_a.encode("utf-8"), val_b.encode("utf-8"))

    @staticmethod
    def load_secret_from_env(*env_vars: str) -> str | None:
        """Load authentication secret strictly from environment variables without hardcoded defaults."""
        for var in env_vars:
            val = os.getenv(var)
            if val and val.strip():
                return val.strip()
        return None

    def check_capability(self, capability: str) -> None:
        """Ensure provider supports the specified capability."""
        if capability not in self.capabilities:
            raise UnsupportedCapabilityError(
                f"Provider '{self.name}' does not support '{capability}'. Supported: {sorted(self.capabilities)}"
            )

    def _audit(
        self,
        action: str,
        resource_type: str,
        resource_id: str = "",
        success: bool = True,
        error_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Audit an action under this provider."""
        self.audit_logger.record(
            provider=self.name,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            success=success,
            error_message=error_message,
            details=details or {},
        )

    # Repository operations
    def list_repositories(self) -> list[RepoItem]:
        self.check_capability("repositories")
        raise NotImplementedError

    def get_repository(self, repo_id: str) -> RepoItem:
        self.check_capability("repositories")
        raise NotImplementedError

    def create_repository(self, name: str, description: str = "", private: bool = True) -> RepoItem:
        self.check_capability("repositories")
        raise NotImplementedError

    # Issue / Work item operations
    def list_issues(self, state: str = "open") -> list[IssueItem]:
        self.check_capability("issues")
        raise NotImplementedError

    def get_issue(self, issue_id: str) -> IssueItem:
        self.check_capability("issues")
        raise NotImplementedError

    def create_issue(
        self,
        title: str,
        body: str = "",
        labels: list[str] | None = None,
    ) -> IssueItem:
        self.check_capability("issues")
        raise NotImplementedError

    def update_issue(
        self,
        issue_id: str,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        labels: list[str] | None = None,
    ) -> IssueItem:
        self.check_capability("issues")
        raise NotImplementedError

    # Pull Request / Merge Request operations
    def list_pull_requests(self, state: str = "open") -> list[PullRequestItem]:
        self.check_capability("pull_requests")
        raise NotImplementedError

    def get_pull_request(self, pr_id: str) -> PullRequestItem:
        self.check_capability("pull_requests")
        raise NotImplementedError

    def create_pull_request(
        self,
        title: str,
        body: str,
        source_branch: str,
        target_branch: str,
    ) -> PullRequestItem:
        self.check_capability("pull_requests")
        raise NotImplementedError

    def merge_pull_request(self, pr_id: str, commit_message: str = "") -> PullRequestItem:
        self.check_capability("pull_requests")
        raise NotImplementedError

    # Pipelines / CI operations
    def list_pipelines(self) -> list[PipelineItem]:
        self.check_capability("pipelines")
        raise NotImplementedError

    def get_pipeline_run(self, pipeline_id: str, run_id: str) -> PipelineItem:
        self.check_capability("pipelines")
        raise NotImplementedError

    def trigger_pipeline(
        self,
        pipeline_id: str,
        ref: str = "main",
        variables: dict[str, str] | None = None,
    ) -> PipelineItem:
        self.check_capability("pipelines")
        raise NotImplementedError

    # VCS / Working copy operations
    def checkout(self, ref: str, target_dir: str | None = None) -> bool:
        self.check_capability("vcs")
        raise NotImplementedError

    def commit(self, message: str, files: list[str] | None = None) -> VCSCommit:
        self.check_capability("vcs")
        raise NotImplementedError

    def get_log(self, limit: int = 10) -> list[VCSLogEntry]:
        self.check_capability("vcs")
        raise NotImplementedError

    def get_diff(self, target: str | None = None) -> VCSDiff:
        self.check_capability("vcs")
        raise NotImplementedError

    def get_status(self) -> VCSStatus:
        self.check_capability("vcs")
        raise NotImplementedError
