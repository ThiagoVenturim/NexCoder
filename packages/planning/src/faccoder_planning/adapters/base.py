"""Base classes and utilities for idempotent platform issue adapters."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from faccoder_planning.models import Plan, Task

MARKER_REGEX = re.compile(r"<!--\s*faccoder-id:\s*([a-zA-Z0-9_\-]+)\s*-->")
MARKER_TEMPLATE = "<!-- faccoder-id: {faccoder_id} -->"


def extract_faccoder_id(text: str) -> str | None:
    """Extract faccoder tracking UUID from issue text or markdown body."""
    if not text:
        return None
    match = MARKER_REGEX.search(text)
    return match.group(1) if match else None


def embed_faccoder_id(body: str, faccoder_id: str) -> str:
    """Ensure the text contains the hidden tracking marker."""
    existing_id = extract_faccoder_id(body)
    if existing_id == faccoder_id:
        return body
    marker = MARKER_TEMPLATE.format(faccoder_id=faccoder_id)
    if not body.strip():
        return marker
    return f"{body.rstrip()}\n\n{marker}"


class RemoteIssue(BaseModel):
    """Normalized representation of an issue on a remote tracker."""

    id: str
    number: int | None = None
    title: str
    body: str = ""
    faccoder_id: str | None = None
    url: str | None = None
    status: str = "open"
    labels: list[str] = Field(default_factory=list)


class IssueSyncResult(BaseModel):
    """Outcome of attempting to sync a local task to a remote issue."""

    task_id: str
    faccoder_id: str
    action: str  # created, updated, skipped, dry_run_create, dry_run_update
    remote_id: str | None = None
    remote_number: int | None = None
    url: str | None = None
    message: str = ""
    dry_run: bool = True


class RemoteMilestone(BaseModel):
    """Normalized milestone or sprint target on a platform tracker."""

    id: str
    number: int
    title: str
    description: str = ""
    state: str = "open"
    due_on: str | None = None
    url: str | None = None


class ProjectV2Info(BaseModel):
    """Metadata for a GitHub Projects v2 Kanban board."""

    id: str
    number: int
    title: str
    url: str | None = None
    owner: str = ""


class ProjectV2Item(BaseModel):
    """An individual item card in a Projects v2 board."""

    id: str
    content_id: str
    content_type: str = "Issue"
    title: str = ""
    status: str | None = None


class ProjectV2ItemResult(BaseModel):
    """Result of adding or updating an item in Projects v2."""

    project_id: str
    item_id: str | None = None
    content_id: str
    action: str  # added, skipped, dry_run_add
    message: str = ""
    dry_run: bool = True


class SyncSummary(BaseModel):
    """Aggregated results across all synchronized tasks in a plan."""

    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    results: list[IssueSyncResult] = Field(default_factory=list)


class PlatformAdapter(ABC):
    """Abstract interface for issue tracking platform adapters."""

    def __init__(self, dry_run: bool = True):
        # By default dry_run is True to prevent accidental modifications
        self.dry_run = dry_run

    @abstractmethod
    def list_issues(self) -> list[RemoteIssue]:
        """Fetch all existing issues, handling remote pagination."""

    def find_issue_by_marker(self, faccoder_id: str) -> RemoteIssue | None:
        """Locate an existing remote issue by its unique embedded tracking marker."""
        for issue in self.list_issues():
            if issue.faccoder_id == faccoder_id or extract_faccoder_id(issue.body) == faccoder_id:
                return issue
        return None

    @abstractmethod
    def create_issue(self, task: Task, dry_run: bool | None = None) -> IssueSyncResult:
        """Create a new remote issue for a task with embedded tracking marker."""

    @abstractmethod
    def update_issue(self, remote: RemoteIssue, task: Task, dry_run: bool | None = None) -> IssueSyncResult:
        """Update an existing remote issue if title, body, or metadata have changed."""

    def sync_task(self, task: Task, dry_run: bool | None = None) -> IssueSyncResult:
        """Idempotently create or update a single task issue."""
        is_dry = self.dry_run if dry_run is None else dry_run
        existing = self.find_issue_by_marker(task.faccoder_id)

        if existing is None:
            return self.create_issue(task, dry_run=is_dry)

        # Check if update is required
        expected_body = task.format_markdown_body()
        title_changed = existing.title.strip() != task.title.strip()
        body_changed = existing.body.strip() != expected_body.strip()

        if title_changed or body_changed:
            return self.update_issue(existing, task, dry_run=is_dry)

        return IssueSyncResult(
            task_id=task.id,
            faccoder_id=task.faccoder_id,
            action="skipped",
            remote_id=existing.id,
            remote_number=existing.number,
            url=existing.url,
            message="No changes detected between task and remote issue.",
            dry_run=is_dry,
        )

    def sync_plan(self, plan: Plan, dry_run: bool | None = None) -> SyncSummary:
        """Idempotently sync all tasks in a plan to the target issue tracker."""
        is_dry = self.dry_run if dry_run is None else dry_run
        results: list[IssueSyncResult] = []
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for task in plan.all_tasks():
            res = self.sync_task(task, dry_run=is_dry)
            results.append(res)
            if "create" in res.action:
                created_count += 1
            elif "update" in res.action:
                updated_count += 1
            elif res.action == "skipped":
                skipped_count += 1

        return SyncSummary(
            total=len(results),
            created=created_count,
            updated=updated_count,
            skipped=skipped_count,
            results=results,
        )

    def list_milestones(self) -> list[RemoteMilestone]:
        """Fetch all existing milestones on the remote platform."""
        return []

    def create_milestone(
        self,
        title: str,
        description: str = "",
        due_on: str | None = None,
        dry_run: bool | None = None,
    ) -> RemoteMilestone:
        """Create a new milestone on the remote platform."""
        return RemoteMilestone(
            id="dry-run-milestone",
            number=999,
            title=title,
            description=description,
            state="open",
            due_on=due_on,
        )

    def get_or_create_milestone(
        self,
        title: str,
        description: str = "",
        due_on: str | None = None,
        dry_run: bool | None = None,
    ) -> RemoteMilestone:
        """Find an existing milestone by title or create it if missing."""
        for m in self.list_milestones():
            if m.title.strip().lower() == title.strip().lower():
                return m
        return self.create_milestone(title, description=description, due_on=due_on, dry_run=dry_run)
