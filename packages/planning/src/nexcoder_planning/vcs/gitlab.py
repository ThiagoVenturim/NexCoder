"""GitLab provider for projects, issues, merge requests, and CI pipelines."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import httpx

from nexcoder_planning.vcs.audit import VCSAuditLogger
from nexcoder_planning.vcs.base import RepoManagementProvider
from nexcoder_planning.vcs.models import (
    IssueItem,
    PipelineItem,
    PullRequestItem,
    RepoItem,
)

logger = logging.getLogger(__name__)


class GitLabProvider(RepoManagementProvider):
    """Integrates with GitLab REST API for projects, issues, MRs, and CI."""

    name: str = "gitlab"
    capabilities: set[str] = {"repositories", "issues", "pull_requests", "pipelines"}

    def __init__(
        self,
        project_id: str | int,
        token: str | None = None,
        api_url: str = "https://gitlab.com/api/v4",
        client: httpx.Client | None = None,
        audit_logger: VCSAuditLogger | None = None,
    ) -> None:
        super().__init__(audit_logger=audit_logger)
        self.raw_project_id = str(project_id)
        self.project_id = urllib.parse.quote(str(project_id), safe="")
        self.token = token or self.load_secret_from_env("GITLAB_TOKEN", "GITLAB_API_TOKEN", "CI_JOB_TOKEN")
        self.api_url = api_url.rstrip("/")
        self._custom_client = client
        self._owned_client: httpx.Client | None = None

    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": "nexcoder-vcs",
            "Content-Type": "application/json",
        }
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token
        return headers

    def _get_client(self) -> httpx.Client:
        if self._custom_client is not None:
            return self._custom_client
        if self._owned_client is None or self._owned_client.is_closed:
            self._owned_client = httpx.Client(headers=self._headers(), timeout=30.0)
        return self._owned_client

    def close(self) -> None:
        """Close managed HTTP client."""
        if self._owned_client is not None and not self._owned_client.is_closed:
            self._owned_client.close()
        self._owned_client = None

    def __enter__(self) -> GitLabProvider:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # Repositories / Projects
    def list_repositories(self) -> list[RepoItem]:
        self.check_capability("repositories")
        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}"
        try:
            res = client.get(url, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            repo = RepoItem(
                id=str(item.get("id")),
                name=item.get("name", ""),
                description=item.get("description", "") or "",
                default_branch=item.get("default_branch", "main"),
                web_url=item.get("web_url", ""),
                clone_url_http=item.get("http_url_to_repo", ""),
                clone_url_ssh=item.get("ssh_url_to_repo", ""),
                is_private=item.get("visibility") == "private",
            )
            self._audit("list_repositories", "repositories", success=True, details={"count": 1})
            return [repo]
        except Exception as exc:
            self._audit("list_repositories", "repositories", success=False, error_message=str(exc))
            raise

    def get_repository(self, repo_id: str) -> RepoItem:
        self.check_capability("repositories")
        client = self._get_client()
        target_id = urllib.parse.quote(str(repo_id), safe="")
        url = f"{self.api_url}/projects/{target_id}"
        try:
            res = client.get(url, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            repo = RepoItem(
                id=str(item.get("id")),
                name=item.get("name", ""),
                description=item.get("description", "") or "",
                default_branch=item.get("default_branch", "main"),
                web_url=item.get("web_url", ""),
                clone_url_http=item.get("http_url_to_repo", ""),
                clone_url_ssh=item.get("ssh_url_to_repo", ""),
                is_private=item.get("visibility") == "private",
            )
            self._audit("get_repository", "repositories", resource_id=repo_id, success=True)
            return repo
        except Exception as exc:
            self._audit("get_repository", "repositories", resource_id=repo_id, success=False, error_message=str(exc))
            raise

    def create_repository(self, name: str, description: str = "", private: bool = True) -> RepoItem:
        self.check_capability("repositories")
        client = self._get_client()
        url = f"{self.api_url}/projects"
        payload = {
            "name": name,
            "description": description,
            "visibility": "private" if private else "public",
        }
        try:
            res = client.post(url, json=payload, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            repo = RepoItem(
                id=str(item.get("id")),
                name=item.get("name", ""),
                description=item.get("description", "") or "",
                default_branch=item.get("default_branch", "main"),
                web_url=item.get("web_url", ""),
                clone_url_http=item.get("http_url_to_repo", ""),
                clone_url_ssh=item.get("ssh_url_to_repo", ""),
                is_private=item.get("visibility") == "private",
            )
            self._audit("create_repository", "repositories", resource_id=repo.id, success=True)
            return repo
        except Exception as exc:
            self._audit("create_repository", "repositories", success=False, error_message=str(exc))
            raise

    # Issues
    def list_issues(self, state: str = "open") -> list[IssueItem]:
        self.check_capability("issues")
        client = self._get_client()
        state_param = "opened" if state.lower() == "open" else state.lower()
        url = f"{self.api_url}/projects/{self.project_id}/issues"
        params = {"state": state_param, "per_page": 100}
        try:
            res = client.get(url, params=params, headers=self._headers())
            res.raise_for_status()
            items = res.json()
            issues: list[IssueItem] = []
            for item in items:
                issues.append(
                    IssueItem(
                        id=str(item.get("id")),
                        number=item.get("iid"),
                        title=item.get("title", ""),
                        body=item.get("description", "") or "",
                        state="closed" if item.get("state") == "closed" else "open",
                        author=item.get("author", {}).get("name", ""),
                        url=item.get("web_url", ""),
                        labels=item.get("labels", []),
                        created_at=item.get("created_at", ""),
                        updated_at=item.get("updated_at", ""),
                    )
                )
            self._audit("list_issues", "issues", success=True, details={"count": len(issues)})
            return issues
        except Exception as exc:
            self._audit("list_issues", "issues", success=False, error_message=str(exc))
            raise

    def get_issue(self, issue_id: str) -> IssueItem:
        self.check_capability("issues")
        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}/issues/{issue_id}"
        try:
            res = client.get(url, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            issue = IssueItem(
                id=str(item.get("id")),
                number=item.get("iid"),
                title=item.get("title", ""),
                body=item.get("description", "") or "",
                state="closed" if item.get("state") == "closed" else "open",
                author=item.get("author", {}).get("name", ""),
                url=item.get("web_url", ""),
                labels=item.get("labels", []),
                created_at=item.get("created_at", ""),
                updated_at=item.get("updated_at", ""),
            )
            self._audit("get_issue", "issues", resource_id=issue_id, success=True)
            return issue
        except Exception as exc:
            self._audit("get_issue", "issues", resource_id=issue_id, success=False, error_message=str(exc))
            raise

    def create_issue(
        self,
        title: str,
        body: str = "",
        labels: list[str] | None = None,
    ) -> IssueItem:
        self.check_capability("issues")
        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}/issues"
        payload: dict[str, Any] = {
            "title": title,
            "description": body,
        }
        if labels:
            payload["labels"] = ",".join(labels)
        try:
            res = client.post(url, json=payload, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            issue = IssueItem(
                id=str(item.get("id")),
                number=item.get("iid"),
                title=item.get("title", title),
                body=item.get("description", body) or "",
                state="open",
                author=item.get("author", {}).get("name", ""),
                url=item.get("web_url", ""),
                labels=item.get("labels", labels or []),
            )
            self._audit("create_issue", "issues", resource_id=issue.id, success=True)
            return issue
        except Exception as exc:
            self._audit("create_issue", "issues", success=False, error_message=str(exc))
            raise

    def update_issue(
        self,
        issue_id: str,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        labels: list[str] | None = None,
    ) -> IssueItem:
        self.check_capability("issues")
        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}/issues/{issue_id}"
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["description"] = body
        if state is not None:
            payload["state_event"] = "close" if state.lower() == "closed" else "reopen"
        if labels is not None:
            payload["labels"] = ",".join(labels)
        try:
            res = client.put(url, json=payload, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            issue = IssueItem(
                id=str(item.get("id")),
                number=item.get("iid"),
                title=item.get("title", ""),
                body=item.get("description", "") or "",
                state="closed" if item.get("state") == "closed" else "open",
                author=item.get("author", {}).get("name", ""),
                url=item.get("web_url", ""),
                labels=item.get("labels", []),
            )
            self._audit("update_issue", "issues", resource_id=issue_id, success=True)
            return issue
        except Exception as exc:
            self._audit("update_issue", "issues", resource_id=issue_id, success=False, error_message=str(exc))
            raise

    # Merge Requests
    def list_pull_requests(self, state: str = "open") -> list[PullRequestItem]:
        self.check_capability("pull_requests")
        client = self._get_client()
        state_param = "opened" if state.lower() == "open" else state.lower()
        url = f"{self.api_url}/projects/{self.project_id}/merge_requests"
        params = {"state": state_param, "per_page": 100}
        try:
            res = client.get(url, params=params, headers=self._headers())
            res.raise_for_status()
            items = res.json()
            prs: list[PullRequestItem] = []
            for item in items:
                gl_state = item.get("state", "opened")
                mapped_state = "merged" if gl_state == "merged" else "closed" if gl_state == "closed" else "open"
                prs.append(
                    PullRequestItem(
                        id=str(item.get("id")),
                        number=item.get("iid"),
                        title=item.get("title", ""),
                        description=item.get("description", "") or "",
                        source_branch=item.get("source_branch", ""),
                        target_branch=item.get("target_branch", ""),
                        state=mapped_state,
                        author=item.get("author", {}).get("name", ""),
                        url=item.get("web_url", ""),
                        is_draft=bool(item.get("work_in_progress") or item.get("draft")),
                        merge_commit_sha=item.get("merge_commit_sha"),
                    )
                )
            self._audit("list_pull_requests", "pull_requests", success=True, details={"count": len(prs)})
            return prs
        except Exception as exc:
            self._audit("list_pull_requests", "pull_requests", success=False, error_message=str(exc))
            raise

    def get_pull_request(self, pr_id: str) -> PullRequestItem:
        self.check_capability("pull_requests")
        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}/merge_requests/{pr_id}"
        try:
            res = client.get(url, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            gl_state = item.get("state", "opened")
            mapped_state = "merged" if gl_state == "merged" else "closed" if gl_state == "closed" else "open"
            pr = PullRequestItem(
                id=str(item.get("id")),
                number=item.get("iid"),
                title=item.get("title", ""),
                description=item.get("description", "") or "",
                source_branch=item.get("source_branch", ""),
                target_branch=item.get("target_branch", ""),
                state=mapped_state,
                author=item.get("author", {}).get("name", ""),
                url=item.get("web_url", ""),
                is_draft=bool(item.get("work_in_progress") or item.get("draft")),
                merge_commit_sha=item.get("merge_commit_sha"),
            )
            self._audit("get_pull_request", "pull_requests", resource_id=pr_id, success=True)
            return pr
        except Exception as exc:
            self._audit("get_pull_request", "pull_requests", resource_id=pr_id, success=False, error_message=str(exc))
            raise

    def create_pull_request(
        self,
        title: str,
        body: str,
        source_branch: str,
        target_branch: str,
    ) -> PullRequestItem:
        self.check_capability("pull_requests")
        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}/merge_requests"
        payload = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": body,
        }
        try:
            res = client.post(url, json=payload, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            pr = PullRequestItem(
                id=str(item.get("id")),
                number=item.get("iid"),
                title=item.get("title", title),
                description=item.get("description", body) or "",
                source_branch=source_branch,
                target_branch=target_branch,
                state="open",
                author=item.get("author", {}).get("name", ""),
                url=item.get("web_url", ""),
            )
            self._audit("create_pull_request", "pull_requests", resource_id=pr.id, success=True)
            return pr
        except Exception as exc:
            self._audit("create_pull_request", "pull_requests", success=False, error_message=str(exc))
            raise

    def merge_pull_request(self, pr_id: str, commit_message: str = "") -> PullRequestItem:
        self.check_capability("pull_requests")
        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}/merge_requests/{pr_id}/merge"
        payload: dict[str, Any] = {}
        if commit_message:
            payload["merge_commit_message"] = commit_message
        try:
            res = client.put(url, json=payload, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            pr = PullRequestItem(
                id=str(item.get("id")),
                number=item.get("iid"),
                title=item.get("title", ""),
                description=item.get("description", "") or "",
                source_branch=item.get("source_branch", ""),
                target_branch=item.get("target_branch", ""),
                state="merged",
                url=item.get("web_url", ""),
                merge_commit_sha=item.get("merge_commit_sha"),
            )
            self._audit("merge_pull_request", "pull_requests", resource_id=pr_id, success=True)
            return pr
        except Exception as exc:
            self._audit("merge_pull_request", "pull_requests", resource_id=pr_id, success=False, error_message=str(exc))
            raise

    # CI / Pipelines
    def list_pipelines(self) -> list[PipelineItem]:
        self.check_capability("pipelines")
        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}/pipelines"
        try:
            res = client.get(url, params={"per_page": 50}, headers=self._headers())
            res.raise_for_status()
            items = res.json()
            pipes: list[PipelineItem] = []
            for item in items:
                pipes.append(
                    PipelineItem(
                        id=str(item.get("id")),
                        name=f"Pipeline #{item.get('id')}",
                        status=item.get("status", "unknown"),
                        ref=item.get("ref", ""),
                        sha=item.get("sha", ""),
                        url=item.get("web_url", ""),
                        created_at=item.get("created_at", ""),
                    )
                )
            self._audit("list_pipelines", "pipelines", success=True, details={"count": len(pipes)})
            return pipes
        except Exception as exc:
            self._audit("list_pipelines", "pipelines", success=False, error_message=str(exc))
            raise

    def get_pipeline_run(self, pipeline_id: str, run_id: str = "") -> PipelineItem:
        self.check_capability("pipelines")
        client = self._get_client()
        target_id = run_id or pipeline_id
        url = f"{self.api_url}/projects/{self.project_id}/pipelines/{target_id}"
        try:
            res = client.get(url, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            pipe = PipelineItem(
                id=str(item.get("id")),
                name=f"Pipeline #{item.get('id')}",
                status=item.get("status", "unknown"),
                ref=item.get("ref", ""),
                sha=item.get("sha", ""),
                url=item.get("web_url", ""),
                created_at=item.get("created_at", ""),
            )
            self._audit("get_pipeline_run", "pipelines", resource_id=target_id, success=True)
            return pipe
        except Exception as exc:
            self._audit("get_pipeline_run", "pipelines", resource_id=target_id, success=False, error_message=str(exc))
            raise

    def trigger_pipeline(
        self,
        pipeline_id: str = "",
        ref: str = "main",
        variables: dict[str, str] | None = None,
    ) -> PipelineItem:
        self.check_capability("pipelines")
        client = self._get_client()
        url = f"{self.api_url}/projects/{self.project_id}/pipeline"
        payload: dict[str, Any] = {"ref": ref}
        if variables:
            payload["variables"] = [{"key": k, "value": v} for k, v in variables.items()]
        try:
            res = client.post(url, json=payload, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            pipe = PipelineItem(
                id=str(item.get("id")),
                name=f"Pipeline #{item.get('id')}",
                status=item.get("status", "pending"),
                ref=item.get("ref", ref),
                sha=item.get("sha", ""),
                url=item.get("web_url", ""),
                created_at=item.get("created_at", ""),
            )
            self._audit("trigger_pipeline", "pipelines", resource_id=pipe.id, success=True)
            return pipe
        except Exception as exc:
            self._audit("trigger_pipeline", "pipelines", resource_id=pipeline_id, success=False, error_message=str(exc))
            raise
