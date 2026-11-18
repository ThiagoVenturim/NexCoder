"""Azure DevOps provider for repositories, work items, pull requests, and pipelines."""

from __future__ import annotations

import base64
import logging
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


class AzureDevOpsProvider(RepoManagementProvider):
    """Integrates with Azure DevOps REST API for Git repos, boards, PRs, and pipelines."""

    name: str = "azure_devops"
    capabilities: set[str] = {"repositories", "issues", "pull_requests", "pipelines"}

    def __init__(
        self,
        organization: str,
        project: str,
        pat: str | None = None,
        repository_id: str | None = None,
        api_url: str = "https://dev.azure.com",
        client: httpx.Client | None = None,
        audit_logger: VCSAuditLogger | None = None,
    ) -> None:
        super().__init__(audit_logger=audit_logger)
        self.organization = organization
        self.project = project
        self.pat = pat or self.load_secret_from_env("AZURE_DEVOPS_PAT", "AZURE_DEVOPS_TOKEN", "ADO_PAT")
        self.repository_id = repository_id
        self.api_url = api_url.rstrip("/")
        self._custom_client = client
        self._owned_client: httpx.Client | None = None

    def _headers(self, patch: bool = False) -> dict[str, str]:
        ct = "application/json-patch+json" if patch else "application/json"
        headers = {
            "User-Agent": "nexcoder-vcs",
            "Content-Type": ct,
        }
        if self.pat:
            encoded = base64.b64encode(f":{self.pat}".encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
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

    def __enter__(self) -> AzureDevOpsProvider:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # Repositories
    def list_repositories(self) -> list[RepoItem]:
        self.check_capability("repositories")
        client = self._get_client()
        url = f"{self.api_url}/{self.organization}/{self.project}/_apis/git/repositories?api-version=7.0"
        try:
            res = client.get(url, headers=self._headers())
            res.raise_for_status()
            data = res.json().get("value", [])
            repos: list[RepoItem] = []
            for item in data:
                repos.append(
                    RepoItem(
                        id=str(item.get("id", "")),
                        name=item.get("name", ""),
                        description=item.get("description", "") or "",
                        default_branch=item.get("defaultBranch", "refs/heads/main").replace("refs/heads/", ""),
                        web_url=item.get("webUrl", ""),
                        clone_url_http=item.get("remoteUrl", ""),
                        clone_url_ssh=item.get("sshUrl", ""),
                        is_private=True,
                    )
                )
            self._audit("list_repositories", "repositories", success=True, details={"count": len(repos)})
            return repos
        except Exception as exc:
            self._audit("list_repositories", "repositories", success=False, error_message=str(exc))
            raise

    def get_repository(self, repo_id: str) -> RepoItem:
        self.check_capability("repositories")
        client = self._get_client()
        url = f"{self.api_url}/{self.organization}/{self.project}/_apis/git/repositories/{repo_id}?api-version=7.0"
        try:
            res = client.get(url, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            repo = RepoItem(
                id=str(item.get("id", "")),
                name=item.get("name", ""),
                description=item.get("description", "") or "",
                default_branch=item.get("defaultBranch", "refs/heads/main").replace("refs/heads/", ""),
                web_url=item.get("webUrl", ""),
                clone_url_http=item.get("remoteUrl", ""),
                clone_url_ssh=item.get("sshUrl", ""),
                is_private=True,
            )
            self._audit("get_repository", "repositories", resource_id=repo_id, success=True)
            return repo
        except Exception as exc:
            self._audit("get_repository", "repositories", resource_id=repo_id, success=False, error_message=str(exc))
            raise

    def create_repository(self, name: str, description: str = "", private: bool = True) -> RepoItem:
        self.check_capability("repositories")
        client = self._get_client()
        url = f"{self.api_url}/{self.organization}/{self.project}/_apis/git/repositories?api-version=7.0"
        payload = {"name": name, "project": {"name": self.project}}
        try:
            res = client.post(url, json=payload, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            repo = RepoItem(
                id=str(item.get("id", "")),
                name=item.get("name", ""),
                description=description,
                default_branch="main",
                web_url=item.get("webUrl", ""),
                clone_url_http=item.get("remoteUrl", ""),
                clone_url_ssh=item.get("sshUrl", ""),
                is_private=private,
            )
            self._audit("create_repository", "repositories", resource_id=repo.id, success=True)
            return repo
        except Exception as exc:
            self._audit("create_repository", "repositories", success=False, error_message=str(exc))
            raise

    # Work Items / Issues
    def list_issues(self, state: str = "open") -> list[IssueItem]:
        self.check_capability("issues")
        client = self._get_client()
        wiql_url = f"{self.api_url}/{self.organization}/{self.project}/_apis/wit/wiql?api-version=7.0"
        wiql_open = (
            "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = @project "
            "AND [System.State] <> 'Closed' ORDER BY [System.Id] DESC"
        )
        wiql_all = (
            "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = @project "
            "ORDER BY [System.Id] DESC"
        )
        query_str = wiql_open if state == "open" else wiql_all
        try:
            res = client.post(wiql_url, json={"query": query_str}, headers=self._headers())
            res.raise_for_status()
            work_items_refs = res.json().get("workItems", [])
            if not work_items_refs:
                self._audit("list_issues", "issues", success=True, details={"count": 0})
                return []

            ids = [str(w["id"]) for w in work_items_refs[:100]]
            ids_str = ",".join(ids)
            batch_url = (
                f"{self.api_url}/{self.organization}/{self.project}"
                f"/_apis/wit/workitems?ids={ids_str}&api-version=7.0"
            )
            details_res = client.get(batch_url, headers=self._headers())
            details_res.raise_for_status()
            items_raw = details_res.json().get("value", [])

            issues: list[IssueItem] = []
            for item in items_raw:
                fields = item.get("fields", {})
                tag_str = fields.get("System.Tags", "")
                labels = [t.strip() for t in tag_str.split(";") if t.strip()] if tag_str else []
                issues.append(
                    IssueItem(
                        id=str(item.get("id")),
                        number=item.get("id"),
                        title=fields.get("System.Title", ""),
                        body=fields.get("System.Description", "") or "",
                        state="closed" if fields.get("System.State") in ("Closed", "Resolved", "Done") else "open",
                        author=fields.get("System.CreatedBy", {}).get("displayName", "")
                        if isinstance(fields.get("System.CreatedBy"), dict)
                        else str(fields.get("System.CreatedBy", "")),
                        url=item.get("url", ""),
                        labels=labels,
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
        url = f"{self.api_url}/{self.organization}/{self.project}/_apis/wit/workitems/{issue_id}?api-version=7.0"
        try:
            res = client.get(url, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            fields = item.get("fields", {})
            tag_str = fields.get("System.Tags", "")
            labels = [t.strip() for t in tag_str.split(";") if t.strip()] if tag_str else []
            issue = IssueItem(
                id=str(item.get("id")),
                number=item.get("id"),
                title=fields.get("System.Title", ""),
                body=fields.get("System.Description", "") or "",
                state="closed" if fields.get("System.State") in ("Closed", "Resolved", "Done") else "open",
                author=fields.get("System.CreatedBy", {}).get("displayName", "")
                if isinstance(fields.get("System.CreatedBy"), dict)
                else str(fields.get("System.CreatedBy", "")),
                url=item.get("url", ""),
                labels=labels,
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
        work_item_type: str = "Task",
    ) -> IssueItem:
        self.check_capability("issues")
        client = self._get_client()
        url = (
            f"{self.api_url}/{self.organization}/{self.project}/_apis/wit/workitems/${work_item_type}?api-version=7.0"
        )
        patch_ops: list[dict[str, Any]] = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/System.Description", "value": body},
        ]
        if labels:
            patch_ops.append({"op": "add", "path": "/fields/System.Tags", "value": "; ".join(labels)})

        try:
            res = client.post(
                url,
                json=patch_ops,
                headers=self._headers(patch=True),
            )
            res.raise_for_status()
            item = res.json()
            fields = item.get("fields", {})
            issue = IssueItem(
                id=str(item.get("id")),
                number=item.get("id"),
                title=fields.get("System.Title", title),
                body=fields.get("System.Description", body) or "",
                state="open",
                url=item.get("url", ""),
                labels=labels or [],
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
        url = f"{self.api_url}/{self.organization}/{self.project}/_apis/wit/workitems/{issue_id}?api-version=7.0"
        patch_ops: list[dict[str, Any]] = []
        if title is not None:
            patch_ops.append({"op": "add", "path": "/fields/System.Title", "value": title})
        if body is not None:
            patch_ops.append({"op": "add", "path": "/fields/System.Description", "value": body})
        if state is not None:
            ado_state = "Closed" if state.lower() == "closed" else "Active"
            patch_ops.append({"op": "add", "path": "/fields/System.State", "value": ado_state})
        if labels is not None:
            patch_ops.append({"op": "add", "path": "/fields/System.Tags", "value": "; ".join(labels)})

        try:
            res = client.patch(
                url,
                json=patch_ops,
                headers=self._headers(patch=True),
            )
            res.raise_for_status()
            item = res.json()
            fields = item.get("fields", {})
            issue = IssueItem(
                id=str(item.get("id")),
                number=item.get("id"),
                title=fields.get("System.Title", ""),
                body=fields.get("System.Description", "") or "",
                state="closed" if fields.get("System.State") in ("Closed", "Resolved", "Done") else "open",
                url=item.get("url", ""),
                labels=labels or [],
            )
            self._audit("update_issue", "issues", resource_id=issue_id, success=True)
            return issue
        except Exception as exc:
            self._audit("update_issue", "issues", resource_id=issue_id, success=False, error_message=str(exc))
            raise

    # Pull Requests
    def _resolve_repo_id(self) -> str:
        if self.repository_id:
            return self.repository_id
        repos = self.list_repositories()
        if not repos:
            raise ValueError(f"No git repositories found in Azure DevOps project '{self.project}'.")
        self.repository_id = repos[0].id
        return self.repository_id

    def list_pull_requests(self, state: str = "open") -> list[PullRequestItem]:
        self.check_capability("pull_requests")
        repo_id = self._resolve_repo_id()
        client = self._get_client()
        status_map = {"open": "active", "merged": "completed", "closed": "abandoned", "all": "all"}
        search_status = status_map.get(state.lower(), "active")
        url = (
            f"{self.api_url}/{self.organization}/{self.project}"
            f"/_apis/git/repositories/{repo_id}/pullrequests?searchCriteria.status={search_status}&api-version=7.0"
        )
        try:
            res = client.get(url, headers=self._headers())
            res.raise_for_status()
            items = res.json().get("value", [])
            prs: list[PullRequestItem] = []
            for item in items:
                ado_status = item.get("status", "")
                if ado_status == "completed":
                    mapped_state = "merged"
                elif ado_status == "abandoned":
                    mapped_state = "closed"
                else:
                    mapped_state = "open"
                prs.append(
                    PullRequestItem(
                        id=str(item.get("pullRequestId")),
                        number=item.get("pullRequestId"),
                        title=item.get("title", ""),
                        description=item.get("description", "") or "",
                        source_branch=item.get("sourceRefName", "").replace("refs/heads/", ""),
                        target_branch=item.get("targetRefName", "").replace("refs/heads/", ""),
                        state=mapped_state,
                        author=item.get("createdBy", {}).get("displayName", ""),
                        url=item.get("url", ""),
                        is_draft=bool(item.get("isDraft")),
                        merge_commit_sha=item.get("lastMergeCommit", {}).get("commitId"),
                    )
                )
            self._audit("list_pull_requests", "pull_requests", success=True, details={"count": len(prs)})
            return prs
        except Exception as exc:
            self._audit("list_pull_requests", "pull_requests", success=False, error_message=str(exc))
            raise

    def get_pull_request(self, pr_id: str) -> PullRequestItem:
        self.check_capability("pull_requests")
        repo_id = self._resolve_repo_id()
        client = self._get_client()
        url = (
            f"{self.api_url}/{self.organization}/{self.project}"
            f"/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}?api-version=7.0"
        )
        try:
            res = client.get(url, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            ado_status = item.get("status", "")
            mapped_state = "merged" if ado_status == "completed" else "closed" if ado_status == "abandoned" else "open"
            pr = PullRequestItem(
                id=str(item.get("pullRequestId")),
                number=item.get("pullRequestId"),
                title=item.get("title", ""),
                description=item.get("description", "") or "",
                source_branch=item.get("sourceRefName", "").replace("refs/heads/", ""),
                target_branch=item.get("targetRefName", "").replace("refs/heads/", ""),
                state=mapped_state,
                author=item.get("createdBy", {}).get("displayName", ""),
                url=item.get("url", ""),
                is_draft=bool(item.get("isDraft")),
                merge_commit_sha=item.get("lastMergeCommit", {}).get("commitId"),
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
        repo_id = self._resolve_repo_id()
        client = self._get_client()
        url = (
            f"{self.api_url}/{self.organization}/{self.project}"
            f"/_apis/git/repositories/{repo_id}/pullrequests?api-version=7.0"
        )
        src_ref = source_branch if source_branch.startswith("refs/") else f"refs/heads/{source_branch}"
        tgt_ref = target_branch if target_branch.startswith("refs/") else f"refs/heads/{target_branch}"
        payload = {
            "sourceRefName": src_ref,
            "targetRefName": tgt_ref,
            "title": title,
            "description": body,
        }
        try:
            res = client.post(url, json=payload, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            pr = PullRequestItem(
                id=str(item.get("pullRequestId")),
                number=item.get("pullRequestId"),
                title=item.get("title", title),
                description=item.get("description", body) or "",
                source_branch=source_branch,
                target_branch=target_branch,
                state="open",
                url=item.get("url", ""),
            )
            self._audit("create_pull_request", "pull_requests", resource_id=pr.id, success=True)
            return pr
        except Exception as exc:
            self._audit("create_pull_request", "pull_requests", success=False, error_message=str(exc))
            raise

    def merge_pull_request(self, pr_id: str, commit_message: str = "") -> PullRequestItem:
        self.check_capability("pull_requests")
        repo_id = self._resolve_repo_id()
        client = self._get_client()
        url = (
            f"{self.api_url}/{self.organization}/{self.project}"
            f"/_apis/git/repositories/{repo_id}/pullrequests/{pr_id}?api-version=7.0"
        )
        payload = {
            "status": "completed",
            "completionOptions": {
                "mergeCommitMessage": commit_message or f"Merged PR {pr_id}",
                "deleteSourceRef": False,
            },
        }
        try:
            res = client.patch(url, json=payload, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            pr = PullRequestItem(
                id=str(item.get("pullRequestId")),
                number=item.get("pullRequestId"),
                title=item.get("title", ""),
                description=item.get("description", "") or "",
                source_branch=item.get("sourceRefName", "").replace("refs/heads/", ""),
                target_branch=item.get("targetRefName", "").replace("refs/heads/", ""),
                state="merged",
                url=item.get("url", ""),
            )
            self._audit("merge_pull_request", "pull_requests", resource_id=pr_id, success=True)
            return pr
        except Exception as exc:
            self._audit("merge_pull_request", "pull_requests", resource_id=pr_id, success=False, error_message=str(exc))
            raise

    # Pipelines
    def list_pipelines(self) -> list[PipelineItem]:
        self.check_capability("pipelines")
        client = self._get_client()
        url = f"{self.api_url}/{self.organization}/{self.project}/_apis/pipelines?api-version=7.0"
        try:
            res = client.get(url, headers=self._headers())
            res.raise_for_status()
            items = res.json().get("value", [])
            pipelines: list[PipelineItem] = []
            for item in items:
                pipelines.append(
                    PipelineItem(
                        id=str(item.get("id")),
                        name=item.get("name", ""),
                        status="ready",
                        url=item.get("url", ""),
                    )
                )
            self._audit("list_pipelines", "pipelines", success=True, details={"count": len(pipelines)})
            return pipelines
        except Exception as exc:
            self._audit("list_pipelines", "pipelines", success=False, error_message=str(exc))
            raise

    def get_pipeline_run(self, pipeline_id: str, run_id: str) -> PipelineItem:
        self.check_capability("pipelines")
        client = self._get_client()
        url = (
            f"{self.api_url}/{self.organization}/{self.project}"
            f"/_apis/pipelines/{pipeline_id}/runs/{run_id}?api-version=7.0"
        )
        try:
            res = client.get(url, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            state = item.get("state", "inProgress")
            result = item.get("result", "")
            status = "success" if result == "succeeded" else "failed" if result == "failed" else state
            pipe = PipelineItem(
                id=str(item.get("id")),
                name=f"Run {run_id}",
                status=status,
                url=item.get("url", ""),
                created_at=item.get("createdDate", ""),
            )
            self._audit(
                "get_pipeline_run",
                "pipelines",
                resource_id=f"{pipeline_id}/{run_id}",
                success=True,
            )
            return pipe
        except Exception as exc:
            self._audit(
                "get_pipeline_run",
                "pipelines",
                resource_id=f"{pipeline_id}/{run_id}",
                success=False,
                error_message=str(exc),
            )
            raise

    def trigger_pipeline(
        self,
        pipeline_id: str,
        ref: str = "main",
        variables: dict[str, str] | None = None,
    ) -> PipelineItem:
        self.check_capability("pipelines")
        client = self._get_client()
        url = f"{self.api_url}/{self.organization}/{self.project}/_apis/pipelines/{pipeline_id}/runs?api-version=7.0"
        ref_name = ref if ref.startswith("refs/") else f"refs/heads/{ref}"
        payload: dict[str, Any] = {
            "resources": {
                "repositories": {
                    "self": {
                        "refName": ref_name,
                    }
                }
            }
        }
        if variables:
            payload["variables"] = {k: {"value": v} for k, v in variables.items()}
        try:
            res = client.post(url, json=payload, headers=self._headers())
            res.raise_for_status()
            item = res.json()
            pipe = PipelineItem(
                id=str(item.get("id")),
                name=f"Run {item.get('id')}",
                status=item.get("state", "inProgress"),
                ref=ref,
                url=item.get("url", ""),
                created_at=item.get("createdDate", ""),
            )
            self._audit("trigger_pipeline", "pipelines", resource_id=f"{pipeline_id}/{pipe.id}", success=True)
            return pipe
        except Exception as exc:
            self._audit("trigger_pipeline", "pipelines", resource_id=pipeline_id, success=False, error_message=str(exc))
            raise
