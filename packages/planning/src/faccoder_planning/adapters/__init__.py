"""Platform adapters for issue trackers (GitHub, GitLab, Azure DevOps)."""

from faccoder_planning.adapters.azure_devops import AzureDevOpsAdapter
from faccoder_planning.adapters.base import (
    IssueSyncResult,
    PlatformAdapter,
    ProjectV2Info,
    ProjectV2Item,
    ProjectV2ItemResult,
    RemoteIssue,
    RemoteMilestone,
    SyncSummary,
    embed_faccoder_id,
    extract_faccoder_id,
)
from faccoder_planning.adapters.github import GitHubAdapter
from faccoder_planning.adapters.gitlab import GitLabAdapter

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
    "embed_faccoder_id",
    "extract_faccoder_id",
]
