"""GitHub REST & GraphQL API adapter for idempotent issue, milestone, and Projects v2 management."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from faccoder_planning.adapters.base import (
    IssueSyncResult,
    PlatformAdapter,
    ProjectV2Info,
    ProjectV2Item,
    ProjectV2ItemResult,
    RemoteIssue,
    RemoteMilestone,
    embed_faccoder_id,
    extract_faccoder_id,
)
from faccoder_planning.models import Task

logger = logging.getLogger(__name__)


class GitHubAdapter(PlatformAdapter):
    """Idempotent issue synchronization with GitHub repositories, Milestones, and Projects v2."""

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
        self._cached_milestones: list[RemoteMilestone] | None = None
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._custom_client is not None:
            return self._custom_client

        if self._client is None:
            headers = {
                "Accept": "application/vnd.github+json",
                "User-Agent": "faccoder-planning",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._client = httpx.Client(headers=headers, timeout=30.0)

        return self._client

    def close(self) -> None:
        """Close the underlying HTTP client if owned."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> GitHubAdapter:
        self._get_client()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def execute_graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL query against the GitHub API endpoint, raising on errors."""
        client = self._get_client()
        graphql_url = f"{self.api_url}/graphql"
        payload = {"query": query, "variables": variables or {}}
        res = client.post(graphql_url, json=payload)
        res.raise_for_status()
        data = res.json()
        if isinstance(data, dict) and data.get("errors"):
            err_details = "; ".join(e.get("message", str(e)) for e in data["errors"])
            raise RuntimeError(f"GitHub GraphQL query failed: {err_details}")
        return data

    # -------------------------------------------------------------------------
    # Issue Management (REST API)
    # -------------------------------------------------------------------------

    def list_issues(self, state: str = "all") -> list[RemoteIssue]:
        """Fetch all issues with full pagination across pages, avoiding 50/100 item limits."""
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
            url = f"{self.api_url}/repos/{self.repo}/issues"
            params = {"state": state, "page": page, "per_page": per_page}
            response = client.get(url, params=params)
            response.raise_for_status()

            items = response.json()
            if not items:
                break

            for item in items:
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

    def create_issue(
        self,
        task: Task,
        milestone_number: int | None = None,
        dry_run: bool | None = None,
    ) -> IssueSyncResult:
        """Create a new GitHub issue with the tracking marker and optional milestone."""
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
        payload: dict[str, Any] = {
            "title": task.title,
            "body": body,
            "labels": labels,
        }
        if milestone_number:
            payload["milestone"] = milestone_number

        res = client.post(url, json=payload)
        res.raise_for_status()
        data = res.json()

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

    def update_issue(
        self,
        remote: RemoteIssue,
        task: Task,
        milestone_number: int | None = None,
        dry_run: bool | None = None,
    ) -> IssueSyncResult:
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
        payload: dict[str, Any] = {
            "title": task.title,
            "body": body,
            "labels": labels,
        }
        if milestone_number:
            payload["milestone"] = milestone_number

        res = client.patch(url, json=payload)
        res.raise_for_status()
        data = res.json()

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

    # -------------------------------------------------------------------------
    # Milestone Management (REST API)
    # -------------------------------------------------------------------------

    def list_milestones(self, state: str = "open") -> list[RemoteMilestone]:
        """Fetch all milestones for the repository with full pagination."""
        if self._cached_milestones is not None:
            return self._cached_milestones

        if self.dry_run and not self.token and self._custom_client is None:
            self._cached_milestones = []
            return self._cached_milestones

        client = self._get_client()
        milestones: list[RemoteMilestone] = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.api_url}/repos/{self.repo}/milestones"
            params = {"state": state, "page": page, "per_page": per_page}
            response = client.get(url, params=params)
            response.raise_for_status()

            items = response.json()
            if not items:
                break

            for item in items:
                milestones.append(
                    RemoteMilestone(
                        id=str(item["id"]),
                        number=item["number"],
                        title=item.get("title", ""),
                        description=item.get("description") or "",
                        state=item.get("state", "open"),
                        due_on=item.get("due_on"),
                        url=item.get("html_url"),
                    )
                )

            if len(items) < per_page:
                break
            page += 1

        self._cached_milestones = milestones
        return milestones

    def create_milestone(
        self,
        title: str,
        description: str = "",
        due_on: str | None = None,
        dry_run: bool | None = None,
    ) -> RemoteMilestone:
        """Create a new milestone on GitHub."""
        is_dry = self.dry_run if dry_run is None else dry_run

        if is_dry:
            return RemoteMilestone(
                id=f"dry-run-ms-{abs(hash(title)) % 10000}",
                number=999,
                title=title,
                description=description,
                state="open",
                due_on=due_on,
                url=f"https://github.com/{self.repo}/milestone/999",
            )

        client = self._get_client()
        url = f"{self.api_url}/repos/{self.repo}/milestones"
        payload: dict[str, Any] = {"title": title, "description": description}
        if due_on:
            payload["due_on"] = due_on

        res = client.post(url, json=payload)
        res.raise_for_status()
        data = res.json()

        ms = RemoteMilestone(
            id=str(data["id"]),
            number=data["number"],
            title=data.get("title", title),
            description=data.get("description", description),
            state=data.get("state", "open"),
            due_on=data.get("due_on"),
            url=data.get("html_url"),
        )
        if self._cached_milestones is not None:
            self._cached_milestones.append(ms)

        return ms

    def get_or_create_milestone(
        self,
        title: str,
        description: str = "",
        due_on: str | None = None,
        dry_run: bool | None = None,
    ) -> RemoteMilestone:
        """Find an existing milestone by title or create it if missing."""
        for m in self.list_milestones(state="all"):
            if m.title.strip().lower() == title.strip().lower():
                return m
        return self.create_milestone(title, description=description, due_on=due_on, dry_run=dry_run)

    # -------------------------------------------------------------------------
    # Projects v2 Management (GraphQL API)
    # -------------------------------------------------------------------------

    def get_project_v2(self, owner: str, project_number: int, is_org: bool = False) -> ProjectV2Info | None:
        """Retrieve Project v2 details by number and owner login via GraphQL."""
        if self.dry_run and not self.token and self._custom_client is None:
            return ProjectV2Info(
                id="dry-run-project-id",
                number=project_number,
                title=f"Project #{project_number}",
                url=f"https://github.com/users/{owner}/projects/{project_number}",
                owner=owner,
            )

        owner_field = "organization" if is_org else "user"
        query = f"""
        query($owner: String!, $number: Int!) {{
          {owner_field}(login: $owner) {{
            projectV2(number: $number) {{
              id
              number
              title
              url
            }}
          }}
        }}
        """
        data = self.execute_graphql(query, {"owner": owner, "number": project_number})
        owner_data = data.get("data", {}).get(owner_field)
        if not owner_data or not owner_data.get("projectV2"):
            # Try alternate (user if org, org if user)
            alt_field = "user" if is_org else "organization"
            alt_query = f"""
            query($owner: String!, $number: Int!) {{
              {alt_field}(login: $owner) {{
                projectV2(number: $number) {{
                  id
                  number
                  title
                  url
                }}
              }}
            }}
            """
            alt_data = self.execute_graphql(alt_query, {"owner": owner, "number": project_number})
            alt_owner = alt_data.get("data", {}).get(alt_field)
            if not alt_owner or not alt_owner.get("projectV2"):
                return None
            proj = alt_owner["projectV2"]
            return ProjectV2Info(
                id=proj["id"],
                number=proj["number"],
                title=proj["title"],
                url=proj.get("url"),
                owner=owner,
            )

        proj = owner_data["projectV2"]
        return ProjectV2Info(
            id=proj["id"],
            number=proj["number"],
            title=proj["title"],
            url=proj.get("url"),
            owner=owner,
        )

    def list_project_items(self, project_id: str) -> list[ProjectV2Item]:
        """Fetch all items in a Projects v2 board with full cursor-based pagination."""
        if self.dry_run and not self.token and self._custom_client is None:
            return []

        items: list[ProjectV2Item] = []
        has_next_page = True
        cursor: str | None = None

        query = """
        query($projectId: ID!, $cursor: String) {
          node(id: $projectId) {
            ... on ProjectV2 {
              items(first: 100, after: $cursor) {
                pageInfo {
                  hasNextPage
                  endCursor
                }
                nodes {
                  id
                  content {
                    __typename
                    ... on Issue {
                      id
                      number
                      title
                    }
                    ... on PullRequest {
                      id
                      number
                      title
                    }
                    ... on DraftIssue {
                      id
                      title
                    }
                  }
                  fieldValueByName(name: "Status") {
                    ... on ProjectV2ItemFieldSingleSelectValue {
                      name
                    }
                  }
                }
              }
            }
          }
        }
        """

        while has_next_page:
            data = self.execute_graphql(query, {"projectId": project_id, "cursor": cursor})
            project_node = data.get("data", {}).get("node", {})
            if not project_node:
                break

            items_data = project_node.get("items", {})
            page_info = items_data.get("pageInfo", {})
            has_next_page = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

            for node in items_data.get("nodes", []):
                content = node.get("content") or {}
                status_field = node.get("fieldValueByName") or {}
                raw_type = content.get("__typename")
                content_type = raw_type if raw_type in ("Issue", "PullRequest", "DraftIssue") else "Issue"
                content_id = str(content.get("id") or node["id"])
                items.append(
                    ProjectV2Item(
                        id=str(node["id"]),
                        content_id=content_id,
                        content_type=content_type,
                        title=content.get("title", ""),
                        status=status_field.get("name"),
                    )
                )

        return items

    def update_project_item_status(
        self,
        project_id: str,
        item_id: str,
        field_id: str,
        single_select_option_id: str,
        dry_run: bool | None = None,
    ) -> ProjectV2ItemResult:
        """Update single-select Status field of a Projects v2 item."""
        is_dry = self.dry_run if dry_run is None else dry_run
        if is_dry:
            return ProjectV2ItemResult(
                project_id=project_id,
                item_id=item_id,
                content_id=item_id,
                action="dry_run_update",
                message=f"[DRY-RUN] Would update status for item '{item_id}'",
                dry_run=True,
            )

        mutation = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optId: String!) {
          updateProjectV2ItemFieldValue(
            input: {
              projectId: $projectId
              itemId: $itemId
              fieldId: $fieldId
              value: { singleSelectOptionId: $optId }
            }
          ) {
            projectV2Item {
              id
            }
          }
        }
        """
        self.execute_graphql(
            mutation,
            {
                "projectId": project_id,
                "itemId": item_id,
                "fieldId": field_id,
                "optId": single_select_option_id,
            },
        )
        return ProjectV2ItemResult(
            project_id=project_id,
            item_id=item_id,
            content_id=item_id,
            action="updated",
            message=f"Updated status for item '{item_id}'",
            dry_run=False,
        )

    def add_item_to_project_v2(
        self,
        project_id: str,
        content_id: str,
        dry_run: bool | None = None,
    ) -> ProjectV2ItemResult:
        """Add an Issue or Pull Request to a Projects v2 board idempotently."""
        is_dry = self.dry_run if dry_run is None else dry_run

        # Check existing items to prevent duplicates
        existing_items = self.list_project_items(project_id)
        for item in existing_items:
            if item.content_id == content_id:
                return ProjectV2ItemResult(
                    project_id=project_id,
                    item_id=item.id,
                    content_id=content_id,
                    action="skipped",
                    message="Item is already present in Projects v2 board.",
                    dry_run=is_dry,
                )

        if is_dry:
            simulated_item_id = f"dry-run-item-{content_id[:8]}"
            return ProjectV2ItemResult(
                project_id=project_id,
                item_id=simulated_item_id,
                content_id=content_id,
                action="dry_run_add",
                message=f"[DRY-RUN] Would add content '{content_id}' to Projects v2 '{project_id}'",
                dry_run=True,
            )

        mutation = """
        mutation($projectId: ID!, $contentId: ID!) {
          addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
            item {
              id
            }
          }
        }
        """
        data = self.execute_graphql(mutation, {"projectId": project_id, "contentId": content_id})
        item_id = data.get("data", {}).get("addProjectV2ItemById", {}).get("item", {}).get("id")

        return ProjectV2ItemResult(
            project_id=project_id,
            item_id=item_id,
            content_id=content_id,
            action="added",
            message=f"Added item '{content_id}' to Projects v2 board '{project_id}'",
            dry_run=False,
        )

    def _compute_labels(self, task: Task) -> list[str]:
        labels = list(task.labels)
        if task.layer and f"layer:{task.layer}" not in labels:
            labels.append(f"layer:{task.layer}")
        if task.recommended_agent and f"agent:{task.recommended_agent}" not in labels:
            labels.append(f"agent:{task.recommended_agent}")
        return labels
