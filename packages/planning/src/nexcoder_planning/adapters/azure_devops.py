"""Azure DevOps REST API adapter for idempotent work item management."""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

import httpx

from nexcoder_planning.adapters.base import (
    IssueSyncResult,
    PlatformAdapter,
    RemoteIssue,
    embed_nexcoder_id,
    extract_nexcoder_id,
)
from nexcoder_planning.models import Task

logger = logging.getLogger(__name__)

TAG_MARKER_REGEX = re.compile(r"\bnexcoder-id:([a-zA-Z0-9_\-]+)\b")


class AzureDevOpsAdapter(PlatformAdapter):
    """Idempotent work item synchronization with Azure DevOps boards."""

    def __init__(
        self,
        organization: str,
        project: str,
        pat: str | None = None,
        work_item_type: str = "Task",
        api_url: str = "https://dev.azure.com",
        client: httpx.Client | None = None,
        dry_run: bool = True,
    ):
        super().__init__(dry_run=dry_run)
        self.organization = organization
        self.project = project
        self.pat = pat
        self.work_item_type = work_item_type
        self.api_url = api_url.rstrip("/")
        self._custom_client = client
        self._client: httpx.Client | None = None
        self._cached_issues: list[RemoteIssue] | None = None

    def _get_client(self) -> httpx.Client:
        if self._custom_client is not None:
            return self._custom_client

        if self._client is None:
            headers = {
                "Content-Type": "application/json-patch+json",
                "User-Agent": "nexcoder-planning",
            }
            if self.pat:
                encoded_pat = base64.b64encode(f":{self.pat}".encode()).decode()
                headers["Authorization"] = f"Basic {encoded_pat}"
            self._client = httpx.Client(headers=headers, timeout=30.0)

        return self._client

    def close(self) -> None:
        """Close the underlying HTTP client if owned."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> AzureDevOpsAdapter:
        self._get_client()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def list_issues(self) -> list[RemoteIssue]:
        """Query and return work items from Azure DevOps."""
        if self._cached_issues is not None:
            return self._cached_issues

        if self.dry_run and not self.pat and self._custom_client is None:
            self._cached_issues = []
            return self._cached_issues

        client = self._get_client()
        # Query Wiql
        wiql_url = f"{self.api_url}/{self.organization}/{self.project}/_apis/wit/wiql?api-version=7.0"
        wiql_query_text = (
            "SELECT [System.Id], [System.Title], [System.Description], [System.State], [System.Tags] "  # noqa: S608
            f"FROM WorkItems WHERE [System.TeamProject] = '{self.project}' "
            f"AND [System.WorkItemType] = '{self.work_item_type}'"
        )
        wiql_query = {"query": wiql_query_text}
        res = client.post(wiql_url, json=wiql_query, headers={"Content-Type": "application/json"})
        res.raise_for_status()
        data = res.json()

        work_items_refs = data.get("workItems", [])
        if not work_items_refs:
            self._cached_issues = []
            return self._cached_issues

        ids = [str(item["id"]) for item in work_items_refs]
        # Batch fetch details in chunks of 200
        remote_issues: list[RemoteIssue] = []
        batch_size = 200
        for i in range(0, len(ids), batch_size):
            chunk = ids[i : i + batch_size]
            ids_param = ",".join(chunk)
            details_url = (
                f"{self.api_url}/{self.organization}/{self.project}/_apis/wit/workitems?ids={ids_param}&api-version=7.0"
            )
            details_res = client.get(details_url, headers={"Content-Type": "application/json"})
            details_res.raise_for_status()
            for wi in details_res.json().get("value", []):
                fields = wi.get("fields", {})
                body = fields.get("System.Description", "")
                tags_str = fields.get("System.Tags", "")

                # Check System.Tags first to protect against HTML stripping comments
                fid = None
                if tags_str:
                    tag_match = TAG_MARKER_REGEX.search(tags_str)
                    if tag_match:
                        fid = tag_match.group(1)
                if not fid:
                    fid = extract_nexcoder_id(body)

                labels = [t.strip() for t in tags_str.split(";") if t.strip()] if tags_str else []

                remote_issues.append(
                    RemoteIssue(
                        id=str(wi["id"]),
                        number=wi.get("id"),
                        title=fields.get("System.Title", ""),
                        body=body,
                        nexcoder_id=fid,
                        url=wi.get("url"),
                        status=fields.get("System.State", "To Do"),
                        labels=labels,
                    )
                )

        self._cached_issues = remote_issues
        return remote_issues

    def create_issue(self, task: Task, dry_run: bool | None = None) -> IssueSyncResult:
        """Create a new work item in Azure DevOps storing tracking id in both tags and body."""
        is_dry = self.dry_run if dry_run is None else dry_run
        body = task.format_markdown_body()
        tag_marker = f"nexcoder-id:{task.nexcoder_id}"

        if is_dry:
            simulated_id = 7777
            return IssueSyncResult(
                task_id=task.id,
                nexcoder_id=task.nexcoder_id,
                action="dry_run_create",
                remote_id=f"dry-run-{task.nexcoder_id[:8]}",
                remote_number=simulated_id,
                url=f"{self.api_url}/{self.organization}/{self.project}/_workitems/edit/{simulated_id}",
                message=f"[DRY-RUN] Would create Azure DevOps work item '{task.title}'",
                dry_run=True,
            )

        client = self._get_client()
        url = (
            f"{self.api_url}/{self.organization}/{self.project}"
            f"/_apis/wit/workitems/${self.work_item_type}?api-version=7.0"
        )
        patch_doc = [
            {"op": "add", "path": "/fields/System.Title", "value": task.title},
            {"op": "add", "path": "/fields/System.Description", "value": body},
            {"op": "add", "path": "/fields/System.Tags", "value": tag_marker},
        ]
        res = client.post(url, json=patch_doc)
        res.raise_for_status()
        data = res.json()

        return IssueSyncResult(
            task_id=task.id,
            nexcoder_id=task.nexcoder_id,
            action="created",
            remote_id=str(data["id"]),
            remote_number=data.get("id"),
            url=data.get("url"),
            message=f"Created Azure DevOps work item #{data.get('id')} '{task.title}'",
            dry_run=False,
        )

    def update_issue(self, remote: RemoteIssue, task: Task, dry_run: bool | None = None) -> IssueSyncResult:
        """Update an existing work item in Azure DevOps preserving marker in tags and body."""
        is_dry = self.dry_run if dry_run is None else dry_run
        body = embed_nexcoder_id(task.format_markdown_body(), task.nexcoder_id)
        tag_marker = f"nexcoder-id:{task.nexcoder_id}"

        if is_dry:
            return IssueSyncResult(
                task_id=task.id,
                nexcoder_id=task.nexcoder_id,
                action="dry_run_update",
                remote_id=remote.id,
                remote_number=remote.number,
                url=remote.url,
                message=f"[DRY-RUN] Would update Azure DevOps work item #{remote.number} for task {task.id}",
                dry_run=True,
            )

        client = self._get_client()
        url = f"{self.api_url}/{self.organization}/{self.project}/_apis/wit/workitems/{remote.id}?api-version=7.0"

        # Combine existing labels with tag_marker
        existing_tags = [lbl for lbl in remote.labels if not lbl.startswith("nexcoder-id:")]
        combined_tags = "; ".join(existing_tags + [tag_marker])

        patch_doc = [
            {"op": "replace", "path": "/fields/System.Title", "value": task.title},
            {"op": "replace", "path": "/fields/System.Description", "value": body},
            {"op": "add", "path": "/fields/System.Tags", "value": combined_tags},
        ]
        res = client.patch(url, json=patch_doc)
        res.raise_for_status()
        data = res.json()

        return IssueSyncResult(
            task_id=task.id,
            nexcoder_id=task.nexcoder_id,
            action="updated",
            remote_id=str(data["id"]),
            remote_number=data.get("id"),
            url=data.get("url"),
            message=f"Updated Azure DevOps work item #{remote.number} '{task.title}'",
            dry_run=False,
        )
