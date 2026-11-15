"""Redmine REST API adapter for idempotent issue and version (milestone) synchronization."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from nexcoder_planning.adapters.base import (
    IssueSyncResult,
    PlatformAdapter,
    RemoteIssue,
    RemoteMilestone,
    embed_nexcoder_id,
    extract_nexcoder_id,
)
from nexcoder_planning.models import Task

logger = logging.getLogger(__name__)


class RedmineAdapter(PlatformAdapter):
    """Idempotent issue synchronization with Redmine project trackers."""

    def __init__(
        self,
        project_id: str,
        api_key: str | None = None,
        base_url: str = "https://redmine.example.local",
        tracker_id: int = 1,
        client: httpx.Client | None = None,
        dry_run: bool = True,
    ) -> None:
        super().__init__(dry_run=dry_run)
        self.project_id = project_id
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.tracker_id = tracker_id
        self._custom_client = client
        self._client: httpx.Client | None = None
        self._cached_issues: list[RemoteIssue] | None = None
        self._cached_milestones: list[RemoteMilestone] | None = None

    def __repr__(self) -> str:
        masked = "***" if self.api_key else "None"
        return (
            f"RedmineAdapter(project_id={self.project_id!r}, base_url={self.base_url!r}, "
            f"api_key={masked}, dry_run={self.dry_run})"
        )

    def _get_client(self) -> httpx.Client:
        if self._custom_client is not None:
            return self._custom_client

        if self._client is None:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "nexcoder-planning",
            }
            if self.api_key:
                headers["X-Redmine-API-Key"] = self.api_key
            self._client = httpx.Client(headers=headers, timeout=30.0)

        return self._client

    def close(self) -> None:
        """Close the underlying HTTP client if owned."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> RedmineAdapter:
        self._get_client()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def list_issues(self, status_id: str = "*") -> list[RemoteIssue]:
        """Fetch all issues for the Redmine project with offset/limit pagination."""
        if self._cached_issues is not None:
            return self._cached_issues

        if self.dry_run and not self.api_key and self._custom_client is None:
            self._cached_issues = []
            return self._cached_issues

        client = self._get_client()
        remote_issues: list[RemoteIssue] = []
        offset = 0
        limit = 100

        while True:
            url = f"{self.base_url}/issues.json"
            params: dict[str, Any] = {
                "project_id": self.project_id,
                "status_id": status_id,
                "offset": offset,
                "limit": limit,
            }
            res = client.get(url, params=params)
            res.raise_for_status()
            data = res.json()

            issues = data.get("issues", [])
            if not issues:
                break

            for item in issues:
                issue_id = item["id"]
                description = item.get("description") or ""
                fid = extract_nexcoder_id(description)
                status_obj = item.get("status") or {}
                status_name = str(status_obj.get("name", "open")).lower()
                is_closed = bool(status_obj.get("is_closed")) or status_name in ("closed", "resolved", "rejected")
                normalized_status = "closed" if is_closed else "open"

                tracker_obj = item.get("tracker") or {}
                labels = [str(tracker_obj.get("name"))] if tracker_obj.get("name") else []

                remote_issues.append(
                    RemoteIssue(
                        id=str(issue_id),
                        number=int(issue_id),
                        title=item.get("subject", ""),
                        body=description,
                        nexcoder_id=fid,
                        url=f"{self.base_url}/issues/{issue_id}",
                        status=normalized_status,
                        labels=labels,
                    )
                )

            total_count = int(data.get("total_count", len(remote_issues)))
            offset += len(issues)
            if offset >= total_count or len(issues) < limit:
                break

        self._cached_issues = remote_issues
        return remote_issues

    def create_issue(self, task: Task, dry_run: bool | None = None) -> IssueSyncResult:
        """Create a new Redmine issue with the hidden nexcoder tracking marker."""
        is_dry = self.dry_run if dry_run is None else dry_run
        body = task.format_markdown_body()

        if is_dry:
            simulated_id = 5555
            return IssueSyncResult(
                task_id=task.id,
                nexcoder_id=task.nexcoder_id,
                action="dry_run_create",
                remote_id=f"dry-run-{task.nexcoder_id[:8]}",
                remote_number=simulated_id,
                url=f"{self.base_url}/issues/{simulated_id}",
                message=f"[DRY-RUN] Would create Redmine issue '{task.title}'",
                dry_run=True,
            )

        client = self._get_client()
        url = f"{self.base_url}/issues.json"
        payload = {
            "issue": {
                "project_id": self.project_id,
                "tracker_id": self.tracker_id,
                "subject": task.title,
                "description": body,
                "estimated_hours": task.estimate_hours,
            }
        }
        res = client.post(url, json=payload)
        res.raise_for_status()
        issue_data = res.json().get("issue", {})
        issue_id = issue_data.get("id", 0)

        created = RemoteIssue(
            id=str(issue_id),
            number=int(issue_id),
            title=task.title,
            body=body,
            nexcoder_id=task.nexcoder_id,
            url=f"{self.base_url}/issues/{issue_id}",
            status="open",
            labels=list(task.labels),
        )
        if self._cached_issues is not None:
            self._cached_issues.append(created)

        return IssueSyncResult(
            task_id=task.id,
            nexcoder_id=task.nexcoder_id,
            action="created",
            remote_id=str(issue_id),
            remote_number=int(issue_id),
            url=f"{self.base_url}/issues/{issue_id}",
            message=f"Created Redmine issue #{issue_id} '{task.title}'",
            dry_run=False,
        )

    def update_issue(self, remote: RemoteIssue, task: Task, dry_run: bool | None = None) -> IssueSyncResult:
        """Update an existing Redmine issue preserving the tracking marker."""
        is_dry = self.dry_run if dry_run is None else dry_run
        body = embed_nexcoder_id(task.format_markdown_body(), task.nexcoder_id)

        if is_dry:
            return IssueSyncResult(
                task_id=task.id,
                nexcoder_id=task.nexcoder_id,
                action="dry_run_update",
                remote_id=remote.id,
                remote_number=remote.number,
                url=remote.url,
                message=f"[DRY-RUN] Would update Redmine issue #{remote.number} for task {task.id}",
                dry_run=True,
            )

        client = self._get_client()
        url = f"{self.base_url}/issues/{remote.id}.json"
        payload = {
            "issue": {
                "subject": task.title,
                "description": body,
                "estimated_hours": task.estimate_hours,
            }
        }
        res = client.put(url, json=payload)
        res.raise_for_status()

        remote.title = task.title
        remote.body = body

        return IssueSyncResult(
            task_id=task.id,
            nexcoder_id=task.nexcoder_id,
            action="updated",
            remote_id=remote.id,
            remote_number=remote.number,
            url=remote.url,
            message=f"Updated Redmine issue #{remote.number} '{task.title}'",
            dry_run=False,
        )

    def list_milestones(self) -> list[RemoteMilestone]:
        """List Redmine project versions (milestones)."""
        if self._cached_milestones is not None:
            return self._cached_milestones

        if self.dry_run and not self.api_key and self._custom_client is None:
            self._cached_milestones = []
            return self._cached_milestones

        client = self._get_client()
        url = f"{self.base_url}/projects/{self.project_id}/versions.json"
        res = client.get(url)
        res.raise_for_status()
        versions = res.json().get("versions", [])

        milestones: list[RemoteMilestone] = []
        for v in versions:
            vid = int(v["id"])
            milestones.append(
                RemoteMilestone(
                    id=str(vid),
                    number=vid,
                    title=v.get("name", ""),
                    description=v.get("description") or "",
                    state=v.get("status", "open"),
                    due_on=v.get("due_date"),
                    url=f"{self.base_url}/versions/{vid}",
                )
            )
        self._cached_milestones = milestones
        return milestones
