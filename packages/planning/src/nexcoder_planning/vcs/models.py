"""Data models for unified VCS and repository management providers."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class VCSProviderType(StrEnum):
    """Supported version control and repository management provider types."""

    AZURE_DEVOPS = "azure_devops"
    GITLAB = "gitlab"
    GIT = "git"
    SVN = "svn"
    TORTOISE_GIT = "tortoise_git"


class RepoItem(BaseModel):
    """Normalized repository metadata."""

    id: str
    name: str
    description: str = ""
    default_branch: str = "main"
    web_url: str = ""
    clone_url_http: str = ""
    clone_url_ssh: str = ""
    is_private: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class IssueItem(BaseModel):
    """Normalized issue or work item representation."""

    id: str
    number: int | None = None
    title: str
    body: str = ""
    state: str = "open"
    author: str = ""
    url: str = ""
    labels: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class PullRequestItem(BaseModel):
    """Normalized pull request or merge request representation."""

    id: str
    number: int | None = None
    title: str
    description: str = ""
    source_branch: str
    target_branch: str
    state: str = "open"
    author: str = ""
    url: str = ""
    is_draft: bool = False
    merge_commit_sha: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PipelineItem(BaseModel):
    """Normalized CI/CD pipeline or build run representation."""

    id: str
    name: str = ""
    status: str = "queued"
    ref: str = ""
    sha: str = ""
    url: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class VCSCommit(BaseModel):
    """Commit or revision record across Git or SVN."""

    revision: str
    author: str = ""
    date: str = ""
    message: str = ""
    files_changed: list[str] = Field(default_factory=list)


class VCSDiff(BaseModel):
    """Diff content representation."""

    target: str = ""
    old_revision: str = ""
    new_revision: str = ""
    patch: str = ""
    additions: int = 0
    deletions: int = 0


class VCSStatus(BaseModel):
    """Working copy status representation."""

    branch_or_rev: str = ""
    clean: bool = True
    staged_files: list[str] = Field(default_factory=list)
    modified_files: list[str] = Field(default_factory=list)
    untracked_files: list[str] = Field(default_factory=list)


class VCSLogEntry(BaseModel):
    """Log entry for historical inspectability."""

    revision: str
    author: str = ""
    date: str = ""
    message: str = ""


class AuditRecord(BaseModel):
    """Audit entry for VCS and repository management operations."""

    id: str
    timestamp: str
    provider: str
    action: str
    resource_type: str
    resource_id: str = ""
    actor: str = "nexcoder"
    success: bool = True
    error_message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
