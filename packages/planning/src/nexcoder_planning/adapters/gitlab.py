"""GitLab API adapter for idempotent issue management, milestones, labels, and board sync."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import httpx

from faccoder_planning.adapters.base import (
    IssueSyncResult,
    PlatformAdapter,
    ProjectV2Item,
    ProjectV2ItemResult,
    RemoteIssue,
    RemoteMilestone,
    embed_faccoder_id,
    extract_faccoder_id,
)
from faccoder_planning.models import Task

logger = logging.getLogger(__name__)


class GitLabAdapter(PlatformAdapter):
    """Idempotent issue, milestone, and board synchronization with GitLab projects."""

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
        self._client: httpx.Client | None = None
        self._cached_issues: list[RemoteIssue] | None = None

    def _get_client(self) -> httpx.Client:
        if self._custom_client is not None:
            return self._custom_client

        if self._client is None or self._client.is_closed:
            headers = {
                "User-Agent": "faccoder-planning",
            }
            if self.token:
                headers["PRIVATE-TOKEN"] = self.token

            self._client = httpx.Client(headers=headers, timeout=30.0)
        return self._client

    def close(self) -> None:
        """Close managed HTTP client session."""
        if self._client is not None and not self._client.is_closed:
            self._client.close()
        self._client = None

    def __enter__(self) -> GitLabAdapter:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

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
                        node_id=str(item.get("id")),
                        title=item.get("title", ""),
                        body=body,
                        faccoder_id=fid,
                        url=item.get("web_url"),
                        status="closed" if item.get("state") == "closed" else "open",
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
        issue_ref = remote.number if remote.number is not None else remote.id
        url = f"{self.api_url}/projects/{self.project_id}/issues/{issue_ref}"
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

    def list_milestones(self) -> list[RemoteMilestone]:
        """Fetch all milestones in the GitLab project with pagination."""
        if self.dry_run and not self.token and self._custom_client is None:
            return []

        client = self._get_client()
        milestones: list[RemoteMilestone] = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.api_url}/projects/{self.project_id}/milestones"
            params = {"page": page, "per_page": per_page}
            response = client.get(url, params=params)
            response.raise_for_status()

            items = response.json()
            if not items:
                break

            for item in items:
                milestones.append(
                    RemoteMilestone(
                        id=str(item["id"]),
                        number=item.get("iid", item["id"]),
                        title=item.get("title", ""),
                        description=item.get("description") or "",
                        state=item.get("state", "active"),
                        due_on=item.get("due_date"),
                    )
                )

            if len(items) < per_page:
                break
            page += 1

        return milestones

    def create_milestone(
        self,
        title: str,
        description: str = "",
        due_on: str | None = None,
        dry_run: bool | None = None,
    ) -> RemoteMilestone:
        """Create a new milestone in the GitLab project."""
        is_dry = self.dry_run if dry_run is None else dry_run
        if is_dry:
            return RemoteMilestone(
                id=f"dry-run-milestone-{title}",
                number=999,
                title=title,
                description=description,
                state="active",
                due_on=due_on,
            )

        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}/milestones"
        payload = {
            "title": title,
            "description": description,
        }
        if due_on:
            payload["due_date"] = due_on

        res = client.post(url, json=payload)
        res.raise_for_status()
        data = res.json()

        return RemoteMilestone(
            id=str(data["id"]),
            number=data.get("iid", data["id"]),
            title=data.get("title", title),
            description=data.get("description") or "",
            state=data.get("state", "active"),
            due_on=data.get("due_date"),
        )

    def list_labels(self) -> list[str]:
        """Fetch all label names in the GitLab project with pagination."""
        if self.dry_run and not self.token and self._custom_client is None:
            return []

        client = self._get_client()
        labels: list[str] = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.api_url}/projects/{self.project_id}/labels"
            params = {"page": page, "per_page": per_page}
            res = client.get(url, params=params)
            res.raise_for_status()
            items = res.json()
            if not items:
                break
            for item in items:
                if "name" in item:
                    labels.append(item["name"])
            if len(items) < per_page:
                break
            page += 1
        return labels

    def create_label(
        self,
        name: str,
        color: str = "#428BCA",
        description: str = "",
        dry_run: bool | None = None,
    ) -> bool:
        """Create a label in GitLab if it does not already exist."""
        is_dry = self.dry_run if dry_run is None else dry_run
        if is_dry:
            return True

        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}/labels"
        payload = {"name": name, "color": color, "description": description}
        res = client.post(url, json=payload)
        # 409 Conflict indicates the label already exists
        if res.status_code in (200, 201, 409):
            return True
        res.raise_for_status()
        return True

    def list_project_items(self, project_id: str | int | None = None) -> list[ProjectV2Item]:
        """Fetch issues mapped as board items with their resolved column status."""
        issues = self.list_issues()
        items: list[ProjectV2Item] = []
        for issue in issues:
            col_status = "Backlog"
            if issue.status.lower() in ("closed", "done"):
                col_status = "Done"
            else:
                for lbl in issue.labels:
                    lower = lbl.lower()
                    if "review" in lower:
                        col_status = "In Review"
                        break
                    elif "progress" in lower or "doing" in lower:
                        col_status = "In Progress"
                        break
                    elif "todo" in lower:
                        col_status = "Todo"
                        break

            items.append(
                ProjectV2Item(
                    id=str(issue.id),
                    content_id=str(issue.id),
                    content_number=issue.number,
                    content_type="Issue",
                    title=issue.title,
                    status=col_status,
                )
            )
        return items

    def update_project_item_status(
        self,
        project_id: str | int,
        item_id: str,
        field_id: str = "",
        single_select_option_id: str = "",
        content_id: str | None = None,
        dry_run: bool | None = None,
    ) -> ProjectV2ItemResult:
        """Update GitLab issue status (close if target is Done, reopen if open, add target status label)."""
        is_dry = self.dry_run if dry_run is None else dry_run
        target_status = single_select_option_id or field_id

        if is_dry:
            return ProjectV2ItemResult(
                project_id=str(project_id),
                item_id=item_id,
                content_id=content_id or item_id,
                action="dry_run_update",
                message=f"[DRY-RUN] Would update GitLab issue '{item_id}' status to '{target_status}'",
                dry_run=True,
            )

        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}/issues/{item_id}"
        payload: dict[str, Any] = {}
        if target_status.lower() in ("done", "closed"):
            payload["state_event"] = "close"
        else:
            payload["state_event"] = "reopen"
            if target_status:
                payload["add_labels"] = target_status

        res = client.put(url, json=payload)
        res.raise_for_status()

        return ProjectV2ItemResult(
            project_id=str(project_id),
            item_id=item_id,
            content_id=content_id or item_id,
            action="updated",
            message=f"Updated GitLab issue '{item_id}' status to '{target_status}'",
            dry_run=False,
        )

    def _compute_labels(self, task: Task) -> list[str]:
        labels = list(task.labels)
        if task.layer and f"layer:{task.layer}" not in labels:
            labels.append(f"layer:{task.layer}")
        if task.recommended_agent and f"agent:{task.recommended_agent}" not in labels:
            labels.append(f"agent:{task.recommended_agent}")
        return labels
