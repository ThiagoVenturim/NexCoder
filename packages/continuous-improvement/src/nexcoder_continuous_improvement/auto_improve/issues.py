"""Issue management for auto-improvement findings: deduplication, Given/When/Then formatting, and platform adapters."""

from __future__ import annotations

import hashlib
import json
import subprocess
from abc import ABC, abstractmethod

from nexcoder_continuous_improvement.auto_improve.models import AutoIssue
from nexcoder_continuous_improvement.issues.planning_bridge import ImprovementFinding


class IssuePlatformAdapter(ABC):
    """Abstract interface for platform issue tracking systems."""

    @abstractmethod
    def create_issue(self, title: str, body: str, labels: list[str]) -> AutoIssue:
        """Create a new issue on the tracker."""

    @abstractmethod
    def list_issues(self, labels: list[str] | None = None) -> list[AutoIssue]:
        """List open issues, optionally filtered by labels."""

    @abstractmethod
    def close_issue(self, issue_id: str | int, comment: str | None = None) -> None:
        """Close an existing issue."""


class InMemoryIssueAdapter(IssuePlatformAdapter):
    """Deterministic in-memory issue adapter for fast offline testing and simulations."""

    def __init__(self) -> None:
        self.issues: dict[str | int, AutoIssue] = {}
        self._next_id = 1

    def create_issue(self, title: str, body: str, labels: list[str]) -> AutoIssue:
        issue_id = self._next_id
        self._next_id += 1
        issue = AutoIssue(
            issue_id=issue_id,
            title=title,
            body=body,
            labels=labels,
            url=f"mock://tracker/issues/{issue_id}",
            status="open",
        )
        self.issues[issue_id] = issue
        return issue

    def list_issues(self, labels: list[str] | None = None) -> list[AutoIssue]:
        matching: list[AutoIssue] = []
        for issue in self.issues.values():
            if issue.status != "open":
                continue
            if labels:
                if all(label in issue.labels for label in labels):
                    matching.append(issue)
            else:
                matching.append(issue)
        return matching

    def close_issue(self, issue_id: str | int, comment: str | None = None) -> None:
        if issue_id in self.issues:
            self.issues[issue_id].status = "closed"
            if comment:
                self.issues[issue_id].metadata["close_comment"] = comment


class GitHubCliIssueAdapter(IssuePlatformAdapter):
    """GitHub CLI adapter calling gh.exe with sanitized environment."""

    def __init__(
        self,
        repo: str = "ThiagoVenturim/NexCoder",
        gh_path: str = "C:/Program Files/GitHub CLI/gh.exe",
    ) -> None:
        self.repo = repo
        self.gh_path = gh_path

    def create_issue(self, title: str, body: str, labels: list[str]) -> AutoIssue:
        cmd = [self.gh_path, "issue", "create", "--repo", self.repo, "--title", title, "--body", body]
        for label in labels:
            cmd.extend(["--label", label])

        env = {"GITHUB_TOKEN": "", "GH_TOKEN": ""}
        out = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env).stdout.strip()  # noqa: S603
        url = out
        issue_num = url.rstrip("/").split("/")[-1] if "/" in url else url
        return AutoIssue(
            issue_id=issue_num,
            title=title,
            body=body,
            labels=labels,
            url=url,
            status="open",
        )

    def list_issues(self, labels: list[str] | None = None) -> list[AutoIssue]:
        cmd = [self.gh_path, "issue", "list", "--repo", self.repo, "--json", "number,title,body,labels,url"]
        if labels:
            for label in labels:
                cmd.extend(["--label", label])

        env = {"GITHUB_TOKEN": "", "GH_TOKEN": ""}
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)  # noqa: S603
        if proc.returncode != 0:
            return []

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return []

        results: list[AutoIssue] = []
        for item in data:
            item_labels = [lb.get("name", "") if isinstance(lb, dict) else str(lb) for lb in item.get("labels", [])]
            results.append(
                AutoIssue(
                    issue_id=item.get("number", 0),
                    title=item.get("title", ""),
                    body=item.get("body", ""),
                    labels=item_labels,
                    url=item.get("url", ""),
                    status="open",
                )
            )
        return results

    def close_issue(self, issue_id: str | int, comment: str | None = None) -> None:
        cmd = [self.gh_path, "issue", "close", str(issue_id), "--repo", self.repo]
        if comment:
            cmd.extend(["--comment", comment])
        env = {"GITHUB_TOKEN": "", "GH_TOKEN": ""}
        subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)  # noqa: S603


class AutoIssueManager:
    """Coordinates automated issue creation and deduplication from findings."""

    def __init__(self, adapter: IssuePlatformAdapter | None = None) -> None:
        self.adapter = adapter or InMemoryIssueAdapter()

    def compute_fingerprint(self, finding: ImprovementFinding) -> str:
        """Compute stable fingerprint for deduplicating findings."""
        raw = f"{finding.category.value}|{finding.layer}|{finding.file_path or ''}|{finding.title}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def format_issue_body(self, finding: ImprovementFinding, fingerprint: str) -> str:
        """Generate standardized issue body with Given/When/Then acceptance criteria and tracking marker."""
        return (
            f"## Problem Description\n\n"
            f"{finding.description}\n\n"
            f"**Category**: `{finding.category.value}`\n"
            f"**Layer**: `{finding.layer}`\n"
            f"**Recommended Agent**: `{finding.recommended_agent}`\n"
            f"**Priority**: `{finding.priority}`\n"
            f"**Estimate**: `{finding.estimate_points} points`\n\n"
            f"## Acceptance Criteria\n\n"
            f"- **Given** {finding.acceptance_given}\n"
            f"- **When** {finding.acceptance_when}\n"
            f"- **Then** {finding.acceptance_then}\n\n"
            f"<!-- nexcoder-auto-fingerprint: {fingerprint} -->"
        )

    def sync_finding_to_issue(self, finding: ImprovementFinding) -> AutoIssue:
        """Create or return existing open issue for finding."""
        fingerprint = self.compute_fingerprint(finding)
        marker = f"<!-- nexcoder-auto-fingerprint: {fingerprint} -->"

        # Check existing open issues for deduplication
        existing = self.adapter.list_issues(labels=["auto"])
        for issue in existing:
            if marker in issue.body or issue.fingerprint == fingerprint:
                return issue

        title = f"[AUTO] {finding.title}"
        body = self.format_issue_body(finding, fingerprint)
        labels = [
            "auto",
            f"layer:{finding.layer}",
            f"type:{finding.category.value}",
            f"priority:{finding.priority}",
        ]

        created = self.adapter.create_issue(title=title, body=body, labels=labels)
        created.fingerprint = fingerprint
        created.category = finding.category
        created.layer = finding.layer
        created.priority = finding.priority
        return created
