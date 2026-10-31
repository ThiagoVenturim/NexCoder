"""GitLab API adapter for idempotent issue management."""

from __future__ import annotations

import logging
import urllib.parse

import httpx

from faccoder_planning.adapters.base import (
    IssueSyncResult,
    PlatformAdapter,
    RemoteIssue,
    embed_faccoder_id,
    extract_faccoder_id,
)
from faccoder_planning.models import Task

logger = logging.getLogger(__name__)


class GitLabAdapter(PlatformAdapter):
    """Idempotent issue synchronization with GitLab projects."""

    def __init__(
        self,
        project_id: str | int,
        token: str | None = None,
        api_url: str = "https://gitlab.com/api/v4",
        client: httpx.Client | None = None,
        dry_run: bool = True,
    ):
        super().__init__(dry_run=dry_run)
        self.project_id = urllib.parse.quote(str(project_id), safe="")
        self.token = token
        self.api_url = api_url.rstrip("/")
        self._custom_client = client
        self._cached_issues: list[RemoteIssue] | None = None

    def _get_client(self) -> httpx.Client:
        if self._custom_client is not None:
            return self._custom_client

        headers = {
            "User-Agent": "faccoder-planning",
        }
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token

        return httpx.Client(headers=headers, timeout=30.0)

    def list_issues(self) -> list[RemoteIssue]:
        """Fetch all GitLab issues with pagination."""
        if self._cached_issues is not None:
            return self._cached_issues

        if self.dry_run and not self.token and self._custom_client is None:
            self._cached_issues = []
            return self._cached_issues

        client = self._get_client()
        remote_issues: list[RemoteIssue] = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.api_url}/projects/{self.project_id}/issues"
            params = {"page": page, "per_page": per_page}
            response = client.get(url, params=params)
            response.raise_for_status()

            items = response.json()
            if not items:
                break

            for item in items:
                body = item.get("description") or ""
                fid = extract_faccoder_id(body)
                labels = item.get("labels", [])

                remote_issues.append(
                    RemoteIssue(
                        id=str(item["id"]),
                        number=item.get("iid"),
                        title=item.get("title", ""),
                        body=body,
                        faccoder_id=fid,
                        url=item.get("web_url"),
                        status=item.get("state", "opened"),
                        labels=labels,
                    )
                )

            if len(items) < per_page:
                break
            page += 1

        self._cached_issues = remote_issues
        return remote_issues

    def create_issue(self, task: Task, dry_run: bool | None = None) -> IssueSyncResult:
        """Create a new GitLab issue with embedded tracking marker."""
        is_dry = self.dry_run if dry_run is None else dry_run
        body = task.format_markdown_body()
        labels = self._compute_labels(task)

        if is_dry:
            simulated_iid = 8888
            return IssueSyncResult(
                task_id=task.id,
                faccoder_id=task.faccoder_id,
                action="dry_run_create",
                remote_id=f"dry-run-{task.faccoder_id[:8]}",
                remote_number=simulated_iid,
                url=f"{self.api_url}/projects/{self.project_id}/issues/{simulated_iid}",
                message=f"[DRY-RUN] Would create GitLab issue '{task.title}'",
                dry_run=True,
            )

        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}/issues"
        payload = {
            "title": task.title,
            "description": body,
            "labels": ",".join(labels),
        }
        res = client.post(url, json=payload)
        res.raise_for_status()
        data = res.json()

        return IssueSyncResult(
            task_id=task.id,
            faccoder_id=task.faccoder_id,
            action="created",
            remote_id=str(data["id"]),
            remote_number=data.get("iid"),
            url=data.get("web_url"),
            message=f"Created GitLab issue #{data.get('iid')} '{task.title}'",
            dry_run=False,
        )

    def update_issue(self, remote: RemoteIssue, task: Task, dry_run: bool | None = None) -> IssueSyncResult:
        """Update an existing GitLab issue."""
        is_dry = self.dry_run if dry_run is None else dry_run
        body = embed_faccoder_id(task.format_markdown_body(), task.faccoder_id)
        labels = self._compute_labels(task)

        if is_dry:
            return IssueSyncResult(
                task_id=task.id,
                faccoder_id=task.faccoder_id,
                action="dry_run_update",
                remote_id=remote.id,
                remote_number=remote.number,
                url=remote.url,
                message=f"[DRY-RUN] Would update GitLab issue #{remote.number} for task {task.id}",
                dry_run=True,
            )

        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}/issues/{remote.number}"
        payload = {
            "title": task.title,
            "description": body,
            "labels": ",".join(labels),
        }
        res = client.put(url, json=payload)
        res.raise_for_status()
        data = res.json()

        return IssueSyncResult(
            task_id=task.id,
            faccoder_id=task.faccoder_id,
            action="updated",
            remote_id=str(data["id"]),
            remote_number=data.get("iid"),
            url=data.get("web_url"),
            message=f"Updated GitLab issue #{remote.number} '{task.title}'",
            dry_run=False,
        )

    def _compute_labels(self, task: Task) -> list[str]:
        labels = list(task.labels)
        if task.layer and f"layer:{task.layer}" not in labels:
            labels.append(f"layer:{task.layer}")
        if task.recommended_agent and f"agent:{task.recommended_agent}" not in labels:
            labels.append(f"agent:{task.recommended_agent}")
        return labels
