"""Platform adapters for issue trackers (GitHub, GitLab, Azure DevOps)."""

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

__all__ = [
    "AzureDevOpsAdapter",
    "GitHubAdapter",
    "GitLabAdapter",
    "IssueSyncResult",
    "PlatformAdapter",
    "ProjectV2Info",
    "ProjectV2Item",
    "ProjectV2ItemResult",
    "RemoteIssue",
    "RemoteMilestone",
    "SyncSummary",
    "embed_nexcoder_id",
    "extract_nexcoder_id",
]
