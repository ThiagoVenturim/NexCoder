"""GitHub REST API adapter for idempotent issue management."""

from __future__ import annotations

import logging

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


class GitHubAdapter(PlatformAdapter):
    """Idempotent issue synchronization with GitHub repositories."""

    def __init__(
        self,
        repo: str,
        token: str | None = None,
        api_url: str = "https://api.github.com",
        client: httpx.Client | None = None,
        dry_run: bool = True,
    ):
        super().__init__(dry_run=dry_run)
        self.repo = repo
        self.token = token
        self.api_url = api_url.rstrip("/")
        self._custom_client = client
        self._cached_issues: list[RemoteIssue] | None = None

    def _get_client(self) -> httpx.Client:
        if self._custom_client is not None:
            return self._custom_client

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "faccoder-planning",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        return httpx.Client(headers=headers, timeout=30.0)

    def list_issues(self, state: str = "all") -> list[RemoteIssue]:
        """Fetch all issues with full pagination across pages, avoiding 50/100 item limits."""
        if self._cached_issues is not None:
            return self._cached_issues

        # In dry run mode without token or client, return cached or empty
        if self.dry_run and not self.token and self._custom_client is None:
            self._cached_issues = []
            return self._cached_issues

        client = self._get_client()
        remote_issues: list[RemoteIssue] = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.api_url}/repos/{self.repo}/issues"
            params = {"state": state, "page": page, "per_page": per_page}
            response = client.get(url, params=params)
            response.raise_for_status()

            items = response.json()
            if not items:
                break

            for item in items:
                # Ignore pull requests which GitHub includes in issues endpoint
                if "pull_request" in item:
                    continue

                body = item.get("body") or ""
                fid = extract_faccoder_id(body)
                labels = [lbl.get("name", "") if isinstance(lbl, dict) else str(lbl) for lbl in item.get("labels", [])]

                remote_issues.append(
                    RemoteIssue(
                        id=str(item["id"]),
                        number=item.get("number"),
                        title=item.get("title", ""),
                        body=body,
                        faccoder_id=fid,
                        url=item.get("html_url"),
                        status=item.get("state", "open"),
                        labels=labels,
                    )
                )

            if len(items) < per_page:
                break
            page += 1

        self._cached_issues = remote_issues
        return remote_issues

    def create_issue(self, task: Task, dry_run: bool | None = None) -> IssueSyncResult:
        """Create a new GitHub issue with the tracking marker."""
        is_dry = self.dry_run if dry_run is None else dry_run
        body = task.format_markdown_body()
        labels = self._compute_labels(task)

        if is_dry:
            simulated_number = 9999
            simulated_url = f"https://github.com/{self.repo}/issues/{simulated_number}"
            return IssueSyncResult(
                task_id=task.id,
                faccoder_id=task.faccoder_id,
                action="dry_run_create",
                remote_id=f"dry-run-{task.faccoder_id[:8]}",
                remote_number=simulated_number,
                url=simulated_url,
                message=f"[DRY-RUN] Would create GitHub issue '{task.title}' with tracking marker {task.faccoder_id}",
                dry_run=True,
            )

        client = self._get_client()
        url = f"{self.api_url}/repos/{self.repo}/issues"
        payload = {
            "title": task.title,
            "body": body,
            "labels": labels,
        }
        res = client.post(url, json=payload)
        res.raise_for_status()
        data = res.json()

        # Update cache
        created_issue = RemoteIssue(
            id=str(data["id"]),
            number=data.get("number"),
            title=data.get("title", ""),
            body=body,
            faccoder_id=task.faccoder_id,
            url=data.get("html_url"),
            status=data.get("state", "open"),
            labels=labels,
        )
        if self._cached_issues is not None:
            self._cached_issues.append(created_issue)

        return IssueSyncResult(
            task_id=task.id,
            faccoder_id=task.faccoder_id,
            action="created",
            remote_id=str(data["id"]),
            remote_number=data.get("number"),
            url=data.get("html_url"),
            message=f"Created GitHub issue #{data.get('number')} '{task.title}'",
            dry_run=False,
        )

    def update_issue(self, remote: RemoteIssue, task: Task, dry_run: bool | None = None) -> IssueSyncResult:
        """Update an existing GitHub issue while preserving marker and identity."""
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
                message=f"[DRY-RUN] Would update GitHub issue #{remote.number} for task {task.id}",
                dry_run=True,
            )

        client = self._get_client()
        url = f"{self.api_url}/repos/{self.repo}/issues/{remote.number}"
        payload = {
            "title": task.title,
            "body": body,
            "labels": labels,
        }
        res = client.patch(url, json=payload)
        res.raise_for_status()
        data = res.json()

        # Update cache
        remote.title = task.title
        remote.body = body
        remote.labels = labels

        return IssueSyncResult(
            task_id=task.id,
            faccoder_id=task.faccoder_id,
            action="updated",
            remote_id=str(data["id"]),
            remote_number=data.get("number"),
            url=data.get("html_url"),
            message=f"Updated GitHub issue #{remote.number} '{task.title}'",
            dry_run=False,
        )

    def _compute_labels(self, task: Task) -> list[str]:
        labels = list(task.labels)
        if task.layer and f"layer:{task.layer}" not in labels:
            labels.append(f"layer:{task.layer}")
        if task.recommended_agent and f"agent:{task.recommended_agent}" not in labels:
            labels.append(f"agent:{task.recommended_agent}")
        return labels
