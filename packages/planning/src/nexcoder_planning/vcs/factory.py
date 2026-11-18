"""Factory and resolver for VCS and repository management providers."""

from __future__ import annotations

from typing import Any

from nexcoder_planning.vcs.azure_devops import AzureDevOpsProvider
from nexcoder_planning.vcs.base import RepoManagementProvider
from nexcoder_planning.vcs.git_provider import GitProvider
from nexcoder_planning.vcs.gitlab import GitLabProvider
from nexcoder_planning.vcs.models import VCSProviderType
from nexcoder_planning.vcs.svn import SVNProvider
from nexcoder_planning.vcs.tortoisegit import TortoiseGitProvider


def get_vcs_provider(
    provider_type: str | VCSProviderType,
    **kwargs: Any,
) -> RepoManagementProvider:
    """Instantiate a repository or VCS management provider by name or type."""
    norm_type = str(provider_type).lower().replace("-", "_")
    if norm_type in ("azure_devops", "azure", "ado", VCSProviderType.AZURE_DEVOPS.value):
        return AzureDevOpsProvider(**kwargs)
    if norm_type in ("gitlab", "gl", VCSProviderType.GITLAB.value):
        return GitLabProvider(**kwargs)
    if norm_type in ("git", VCSProviderType.GIT.value):
        return GitProvider(**kwargs)
    if norm_type in ("svn", "subversion", VCSProviderType.SVN.value):
        return SVNProvider(**kwargs)
    if norm_type in ("tortoise_git", "tortoisegit", "tgit", VCSProviderType.TORTOISE_GIT.value):
        return TortoiseGitProvider(**kwargs)

    raise ValueError(
        f"Unknown VCS provider '{provider_type}'. Supported: azure_devops, gitlab, git, svn, tortoise_git"
    )
