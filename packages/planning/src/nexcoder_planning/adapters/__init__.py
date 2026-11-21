"""Platform adapters for issue trackers (GitHub, GitLab, Azure DevOps, Redmine)."""

from nexcoder_planning.adapters.azure_devops import AzureDevOpsAdapter
from nexcoder_planning.adapters.base import (
    IssueSyncResult,
    PlatformAdapter,
    ProjectV2Info,
    ProjectV2Item,
    ProjectV2ItemResult,
    RemoteIssue,
    RemoteMilestone,
    SyncSummary,
    embed_nexcoder_id,
    extract_nexcoder_id,
)
from nexcoder_planning.adapters.github import GitHubAdapter
from nexcoder_planning.adapters.gitlab import GitLabAdapter
from nexcoder_planning.adapters.redmine import RedmineAdapter

__all__ = [
    "AzureDevOpsAdapter",
    "GitHubAdapter",
    "GitLabAdapter",
    "IssueSyncResult",
    "PlatformAdapter",
    "ProjectV2Info",
    "ProjectV2Item",
    "ProjectV2ItemResult",
    "RedmineAdapter",
    "RemoteIssue",
    "RemoteMilestone",
    "SyncSummary",
    "embed_nexcoder_id",
    "extract_nexcoder_id",
]
