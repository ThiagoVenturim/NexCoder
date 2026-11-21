"""VCS and repository management providers for Azure DevOps, GitLab, Git, SVN, and TortoiseGit."""

from __future__ import annotations

from nexcoder_planning.vcs.audit import VCSAuditLogger, get_vcs_audit_logger
from nexcoder_planning.vcs.azure_devops import AzureDevOpsProvider
from nexcoder_planning.vcs.base import RepoManagementProvider, UnsupportedCapabilityError
from nexcoder_planning.vcs.factory import get_vcs_provider
from nexcoder_planning.vcs.git_provider import GitProvider
from nexcoder_planning.vcs.gitlab import GitLabProvider
from nexcoder_planning.vcs.models import (
    AuditRecord,
    IssueItem,
    PipelineItem,
    PullRequestItem,
    RepoItem,
    VCSCommit,
    VCSDiff,
    VCSLogEntry,
    VCSProviderType,
    VCSStatus,
)
from nexcoder_planning.vcs.svn import SVNProvider
from nexcoder_planning.vcs.tortoisegit import TortoiseGitProvider

__all__ = [
    "AuditRecord",
    "AzureDevOpsProvider",
    "GitLabProvider",
    "GitProvider",
    "IssueItem",
    "PipelineItem",
    "PullRequestItem",
    "RepoItem",
    "RepoManagementProvider",
    "SVNProvider",
    "TortoiseGitProvider",
    "UnsupportedCapabilityError",
    "VCSAuditLogger",
    "VCSCommit",
    "VCSDiff",
    "VCSLogEntry",
    "VCSProviderType",
    "VCSStatus",
    "get_vcs_audit_logger",
    "get_vcs_provider",
]
