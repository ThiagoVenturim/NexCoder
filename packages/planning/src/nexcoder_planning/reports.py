"""Developer productivity connectors (GitHub, Azure DevOps, Redmine) and NexDash dashboard builder.

Pulls pull request, code review, lead time, and issue completion data from
engineering management platforms, normalizes records into the ``dev_productivity``
semantic cube, and requests a rendered dashboard from NexDash via MCP, REST, or
offline mode.
"""

from __future__ import annotations

import base64
import datetime as dt
import statistics
from typing import Any

import httpx
from nexcoder_core.reports import (
    NexDashClient,
    NexDashComputedChart,
    NexDashComputedKPI,
    NexDashCubeSpec,
    NexDashDashboardBundle,
    NexDashDimensionSpec,
    NexDashMetricSpec,
    NexDashPlanFilter,
    NexDashQueryPlan,
    TransportKind,
)
from pydantic import BaseModel, Field


def _parse_iso(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    cleaned = ts.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(cleaned)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=dt.UTC)
    except ValueError:
        return None


def _hours_between(start_iso: str | None, end_iso: str | None) -> float | None:
    start_dt = _parse_iso(start_iso)
    end_dt = _parse_iso(end_iso)
    if start_dt is None or end_dt is None:
        return None
    diff_hours = (end_dt - start_dt).total_seconds() / 3600.0
    return round(max(0.0, diff_hours), 2)


def _iso_week_label(ts: str | None, default: str = "2026-W44") -> str:
    parsed = _parse_iso(ts)
    if parsed is None:
        return default
    iso_year, iso_week, _ = parsed.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


class PullRequestRecord(BaseModel):
    """Normalized pull request / merge request metric record."""

    id: str
    platform: str  # github, azure_devops, redmine, gitlab
    repo: str
    author: str
    team: str = "core-engineering"
    title: str
    state: str = "merged"  # open, merged, closed
    created_at: str
    first_review_at: str | None = None
    merged_at: str | None = None
    review_time_hours: float = 0.0
    lead_time_hours: float = 0.0
    comments_count: int = 0
    week: str = "2026-W44"


class IssueMetricRecord(BaseModel):
    """Normalized issue / work item metric record."""

    id: str
    platform: str  # github, azure_devops, redmine, gitlab
    project: str
    assignee: str
    team: str = "core-engineering"
    title: str
    state: str = "closed"  # open, closed
    created_at: str
    closed_at: str | None = None
    cycle_time_hours: float = 0.0
    estimate_hours: float = 0.0
    week: str = "2026-W44"


class AuthorThroughput(BaseModel):
    """Aggregated productivity metrics per team contributor."""

    author: str
    team: str
    prs_merged: int = 0
    issues_closed: int = 0
    avg_review_time_hours: float = 0.0
    avg_lead_time_hours: float = 0.0
    total_items_completed: int = 0


class WeeklyProductivityPoint(BaseModel):
    """Weekly time-series point for PRs, issues, review time, and lead time."""

    week: str
    prs_opened: int = 0
    prs_merged: int = 0
    issues_closed: int = 0
    avg_review_time_hours: float = 0.0
    avg_lead_time_hours: float = 0.0


class PlatformProductivityBreakdown(BaseModel):
    """Productivity metrics grouped by source platform (GitHub, Azure DevOps, Redmine)."""

    platform: str
    prs_opened: int = 0
    prs_merged: int = 0
    issues_opened: int = 0
    issues_closed: int = 0
    avg_review_time_hours: float = 0.0
    avg_lead_time_hours: float = 0.0


class ProductivityReportMetrics(BaseModel):
    """Consolidated team productivity metrics ready for NexDash visualization."""

    project: str
    team: str
    period: str
    platforms: list[str] = Field(default_factory=list)
    prs_opened: int = 0
    prs_merged: int = 0
    pr_merge_rate_pct: float = 0.0
    avg_review_time_hours: float = 0.0
    median_review_time_hours: float = 0.0
    avg_lead_time_hours: float = 0.0
    median_lead_time_hours: float = 0.0
    issues_opened: int = 0
    issues_closed: int = 0
    issue_resolution_rate_pct: float = 0.0
    throughput_by_author: list[AuthorThroughput] = Field(default_factory=list)
    weekly_trend: list[WeeklyProductivityPoint] = Field(default_factory=list)
    platform_breakdown: list[PlatformProductivityBreakdown] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Synthetic Offline Data Generator
# ---------------------------------------------------------------------------


def build_synthetic_productivity_data(
    project: str = "nexcoder-platform",
    team: str = "core-engineering",
    platforms: list[str] | None = None,
) -> tuple[list[PullRequestRecord], list[IssueMetricRecord]]:
    """Build deterministic multi-week productivity records across GitHub, Azure DevOps, and Redmine."""
    selected = [p.lower() for p in (platforms or ["github", "azure_devops", "redmine"])]

    all_prs = [
        PullRequestRecord(
            id="gh-pr-101",
            platform="github",
            repo=f"ThiagoVenturim/{project}",
            author="ana.silva",
            team=team,
            title="feat(core): add hybrid retrieval fusion",
            state="merged",
            created_at="2026-10-12T09:00:00Z",
            first_review_at="2026-10-12T12:30:00Z",
            merged_at="2026-10-13T03:00:00Z",
            review_time_hours=3.5,
            lead_time_hours=18.0,
            comments_count=4,
            week="2026-W42",
        ),
        PullRequestRecord(
            id="gh-pr-102",
            platform="github",
            repo=f"ThiagoVenturim/{project}",
            author="bruno.costa",
            team=team,
            title="fix(planning): handle cursor pagination on boards",
            state="merged",
            created_at="2026-10-19T10:00:00Z",
            first_review_at="2026-10-19T14:00:00Z",
            merged_at="2026-10-20T00:00:00Z",
            review_time_hours=4.0,
            lead_time_hours=14.0,
            comments_count=3,
            week="2026-W43",
        ),
        PullRequestRecord(
            id="gh-pr-103",
            platform="github",
            repo=f"ThiagoVenturim/{project}",
            author="ana.silva",
            team=team,
            title="feat(security): add multi-scanner release gate",
            state="merged",
            created_at="2026-10-26T08:00:00Z",
            first_review_at="2026-10-26T10:30:00Z",
            merged_at="2026-10-26T20:00:00Z",
            review_time_hours=2.5,
            lead_time_hours=12.0,
            comments_count=5,
            week="2026-W44",
        ),
        PullRequestRecord(
            id="gh-pr-104",
            platform="github",
            repo=f"ThiagoVenturim/{project}",
            author="carla.mendes",
            team=team,
            title="docs(interfaces): document MCP SSE transport",
            state="open",
            created_at="2026-11-02T11:00:00Z",
            first_review_at="2026-11-02T13:00:00Z",
            merged_at=None,
            review_time_hours=2.0,
            lead_time_hours=9.5,
            comments_count=2,
            week="2026-W45",
        ),
        PullRequestRecord(
            id="ado-pr-201",
            platform="azure_devops",
            repo=f"{project}-services",
            author="bruno.costa",
            team=team,
            title="feat(control): add constant-time API key verification",
            state="merged",
            created_at="2026-10-14T09:00:00Z",
            first_review_at="2026-10-14T14:00:00Z",
            merged_at="2026-10-15T01:00:00Z",
            review_time_hours=5.0,
            lead_time_hours=16.0,
            comments_count=6,
            week="2026-W42",
        ),
        PullRequestRecord(
            id="ado-pr-202",
            platform="azure_devops",
            repo=f"{project}-services",
            author="carla.mendes",
            team=team,
            title="refactor(agents): add committee approval gate",
            state="merged",
            created_at="2026-10-21T09:00:00Z",
            first_review_at="2026-10-21T12:00:00Z",
            merged_at="2026-10-21T21:00:00Z",
            review_time_hours=3.0,
            lead_time_hours=12.0,
            comments_count=2,
            week="2026-W43",
        ),
        PullRequestRecord(
            id="ado-pr-203",
            platform="azure_devops",
            repo=f"{project}-services",
            author="ana.silva",
            team=team,
            title="feat(serving): add vLLM compose profile and RAFT builder",
            state="merged",
            created_at="2026-11-03T08:00:00Z",
            first_review_at="2026-11-03T10:00:00Z",
            merged_at="2026-11-03T17:00:00Z",
            review_time_hours=2.0,
            lead_time_hours=9.0,
            comments_count=3,
            week="2026-W45",
        ),
        PullRequestRecord(
            id="rm-chg-301",
            platform="redmine",
            repo=f"{project}-legacy",
            author="diego.rocha",
            team=team,
            title="fix(parsers): support Delphi interface declarations",
            state="merged",
            created_at="2026-10-27T10:00:00Z",
            first_review_at="2026-10-27T13:30:00Z",
            merged_at="2026-10-27T21:00:00Z",
            review_time_hours=3.5,
            lead_time_hours=11.0,
            comments_count=1,
            week="2026-W44",
        ),
    ]

    all_issues = [
        IssueMetricRecord(
            id="gh-iss-11",
            platform="github",
            project=project,
            assignee="ana.silva",
            team=team,
            title="Implement hybrid store SQLite FTS5",
            state="closed",
            created_at="2026-10-10T09:00:00Z",
            closed_at="2026-10-13T15:00:00Z",
            cycle_time_hours=30.0,
            estimate_hours=8.0,
            week="2026-W42",
        ),
        IssueMetricRecord(
            id="gh-iss-12",
            platform="github",
            project=project,
            assignee="bruno.costa",
            team=team,
            title="Add GitHub Projects v2 status sync",
            state="closed",
            created_at="2026-10-18T10:00:00Z",
            closed_at="2026-10-20T16:00:00Z",
            cycle_time_hours=22.0,
            estimate_hours=6.0,
            week="2026-W43",
        ),
        IssueMetricRecord(
            id="gh-iss-13",
            platform="github",
            project=project,
            assignee="ana.silva",
            team=team,
            title="Enforce fail-closed security release gate",
            state="closed",
            created_at="2026-10-25T08:00:00Z",
            closed_at="2026-10-26T20:00:00Z",
            cycle_time_hours=18.0,
            estimate_hours=5.0,
            week="2026-W44",
        ),
        IssueMetricRecord(
            id="ado-wi-21",
            platform="azure_devops",
            project=project,
            assignee="carla.mendes",
            team=team,
            title="Configure OIDC and local auth provider",
            state="closed",
            created_at="2026-10-20T09:00:00Z",
            closed_at="2026-10-22T12:00:00Z",
            cycle_time_hours=27.0,
            estimate_hours=8.0,
            week="2026-W43",
        ),
        IssueMetricRecord(
            id="ado-wi-22",
            platform="azure_devops",
            project=project,
            assignee="bruno.costa",
            team=team,
            title="Add rate limiter and budget cap enforcement",
            state="closed",
            created_at="2026-10-26T09:00:00Z",
            closed_at="2026-10-28T11:00:00Z",
            cycle_time_hours=20.0,
            estimate_hours=6.0,
            week="2026-W44",
        ),
        IssueMetricRecord(
            id="rm-iss-31",
            platform="redmine",
            project=project,
            assignee="diego.rocha",
            team=team,
            title="Index legacy Delphi and COBOL modules",
            state="closed",
            created_at="2026-10-27T08:00:00Z",
            closed_at="2026-10-28T14:00:00Z",
            cycle_time_hours=16.0,
            estimate_hours=4.0,
            week="2026-W44",
        ),
        IssueMetricRecord(
            id="rm-iss-32",
            platform="redmine",
            project=project,
            assignee="carla.mendes",
            team=team,
            title="Publish NexDash productivity and security reports",
            state="closed",
            created_at="2026-11-02T09:00:00Z",
            closed_at="2026-11-03T18:00:00Z",
            cycle_time_hours=14.0,
            estimate_hours=5.0,
            week="2026-W45",
        ),
        IssueMetricRecord(
            id="rm-iss-33",
            platform="redmine",
            project=project,
            assignee="diego.rocha",
            team=team,
            title="Add Redmine custom field mapping",
            state="open",
            created_at="2026-11-04T10:00:00Z",
            closed_at=None,
            cycle_time_hours=0.0,
            estimate_hours=3.0,
            week="2026-W45",
        ),
    ]

    prs = [p for p in all_prs if p.platform in selected]
    issues = [i for i in all_issues if i.platform in selected]
    return prs, issues


# ---------------------------------------------------------------------------
# Platform Collectors (GitHub, Azure DevOps, Redmine)
# ---------------------------------------------------------------------------


def collect_github_productivity(
    repo: str,
    *,
    token: str | None = None,
    api_url: str = "https://api.github.com",
    client: httpx.Client | None = None,
    team: str = "core-engineering",
    dry_run: bool = True,
) -> tuple[list[PullRequestRecord], list[IssueMetricRecord]]:
    """Fetch PRs and issues from GitHub REST API and normalize into productivity records."""
    if dry_run and client is None and not token:
        return build_synthetic_productivity_data(project=repo.split("/")[-1], team=team, platforms=["github"])

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "nexcoder-planning"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    owned_client = client is None
    http = client or httpx.Client(headers=headers, timeout=30.0)
    base = api_url.rstrip("/")

    prs: list[PullRequestRecord] = []
    issues: list[IssueMetricRecord] = []

    try:
        # Fetch Pull Requests with pagination
        page = 1
        while True:
            resp = http.get(f"{base}/repos/{repo}/pulls", params={"state": "all", "per_page": 100, "page": page})
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            for item in items:
                created_at = item.get("created_at") or "2026-11-01T00:00:00Z"
                merged_at = item.get("merged_at")
                closed_at = item.get("closed_at")
                first_review = item.get("first_review_at") or item.get("updated_at") or merged_at
                state = "merged" if merged_at else str(item.get("state", "open")).lower()
                rev_hours = _hours_between(created_at, first_review) or 0.0
                lead_hours = _hours_between(created_at, merged_at or closed_at) or rev_hours
                user_obj = item.get("user") or {}
                author = str(user_obj.get("login") or "developer")

                prs.append(
                    PullRequestRecord(
                        id=f"gh-pr-{item.get('number', item.get('id'))}",
                        platform="github",
                        repo=repo,
                        author=author,
                        team=team,
                        title=str(item.get("title", "")),
                        state=state,
                        created_at=created_at,
                        first_review_at=first_review,
                        merged_at=merged_at,
                        review_time_hours=rev_hours,
                        lead_time_hours=lead_hours,
                        comments_count=int(item.get("comments", 0)),
                        week=_iso_week_label(merged_at or created_at),
                    )
                )
            if len(items) < 100:
                break
            page += 1

        # Fetch Issues with pagination
        page = 1
        while True:
            resp = http.get(f"{base}/repos/{repo}/issues", params={"state": "all", "per_page": 100, "page": page})
            resp.raise_for_status()
            items = resp.json()
            if not items:
                break
            for item in items:
                if "pull_request" in item:
                    continue
                created_at = item.get("created_at") or "2026-11-01T00:00:00Z"
                closed_at = item.get("closed_at")
                state = "closed" if str(item.get("state", "open")).lower() == "closed" else "open"
                assignee_obj = item.get("assignee") or item.get("user") or {}
                assignee = str(assignee_obj.get("login") or "unassigned")
                cycle = _hours_between(created_at, closed_at) or 0.0

                issues.append(
                    IssueMetricRecord(
                        id=f"gh-iss-{item.get('number', item.get('id'))}",
                        platform="github",
                        project=repo,
                        assignee=assignee,
                        team=team,
                        title=str(item.get("title", "")),
                        state=state,
                        created_at=created_at,
                        closed_at=closed_at,
                        cycle_time_hours=cycle,
                        week=_iso_week_label(closed_at or created_at),
                    )
                )
            if len(items) < 100:
                break
            page += 1
    finally:
        if owned_client:
            http.close()

    return prs, issues


def collect_azure_devops_productivity(
    organization: str,
    project: str,
    *,
    repository: str | None = None,
    pat: str | None = None,
    api_url: str = "https://dev.azure.com",
    client: httpx.Client | None = None,
    team: str = "core-engineering",
    dry_run: bool = True,
) -> tuple[list[PullRequestRecord], list[IssueMetricRecord]]:
    """Fetch pull requests and work items from Azure DevOps REST API."""
    if dry_run and client is None and not pat:
        return build_synthetic_productivity_data(project=project, team=team, platforms=["azure_devops"])

    headers = {"Accept": "application/json", "User-Agent": "nexcoder-planning"}
    if pat:
        encoded = base64.b64encode(f":{pat}".encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"

    owned_client = client is None
    http = client or httpx.Client(headers=headers, timeout=30.0)
    base = api_url.rstrip("/")
    repo_name = repository or project

    prs: list[PullRequestRecord] = []
    issues: list[IssueMetricRecord] = []

    try:
        pr_url = (
            f"{base}/{organization}/{project}/_apis/git/repositories/{repo_name}/pullrequests"
            "?searchCriteria.status=all&api-version=7.0"
        )
        pr_resp = http.get(pr_url)
        pr_resp.raise_for_status()
        for item in pr_resp.json().get("value", []):
            created_at = item.get("creationDate") or "2026-11-01T00:00:00Z"
            closed_at = item.get("closedDate")
            first_review = item.get("firstReviewDate") or closed_at
            raw_status = str(item.get("status", "active")).lower()
            state = "merged" if raw_status == "completed" else ("closed" if raw_status == "abandoned" else "open")
            rev_hours = _hours_between(created_at, first_review) or 0.0
            lead_hours = _hours_between(created_at, closed_at) or rev_hours
            created_by = item.get("createdBy") or {}
            author = str(created_by.get("uniqueName") or created_by.get("displayName") or "developer")

            prs.append(
                PullRequestRecord(
                    id=f"ado-pr-{item.get('pullRequestId', 0)}",
                    platform="azure_devops",
                    repo=repo_name,
                    author=author,
                    team=team,
                    title=str(item.get("title", "")),
                    state=state,
                    created_at=created_at,
                    first_review_at=first_review,
                    merged_at=closed_at if state == "merged" else None,
                    review_time_hours=rev_hours,
                    lead_time_hours=lead_hours,
                    week=_iso_week_label(closed_at or created_at),
                )
            )

        wi_url = f"{base}/{organization}/{project}/_apis/wit/workitems?api-version=7.0"
        wi_resp = http.get(wi_url)
        if wi_resp.status_code == 200:
            for wi in wi_resp.json().get("value", []):
                fields = wi.get("fields") or {}
                created_at = fields.get("System.CreatedDate") or "2026-11-01T00:00:00Z"
                closed_at = fields.get("Microsoft.VSTS.Common.ClosedDate")
                raw_state = str(fields.get("System.State", "Active")).lower()
                state = "closed" if raw_state in ("closed", "done", "resolved", "completed") else "open"
                assigned = fields.get("System.AssignedTo")
                if isinstance(assigned, dict):
                    assignee = str(assigned.get("uniqueName") or assigned.get("displayName") or "unassigned")
                else:
                    assignee = str(assigned or "unassigned")
                cycle = _hours_between(created_at, closed_at) or 0.0

                issues.append(
                    IssueMetricRecord(
                        id=f"ado-wi-{wi.get('id', 0)}",
                        platform="azure_devops",
                        project=project,
                        assignee=assignee,
                        team=team,
                        title=str(fields.get("System.Title", "")),
                        state=state,
                        created_at=created_at,
                        closed_at=closed_at,
                        cycle_time_hours=cycle,
                        week=_iso_week_label(closed_at or created_at),
                    )
                )
    finally:
        if owned_client:
            http.close()

    return prs, issues


def collect_redmine_productivity(
    project_id: str,
    *,
    api_key: str | None = None,
    base_url: str = "https://redmine.example.local",
    client: httpx.Client | None = None,
    team: str = "core-engineering",
    dry_run: bool = True,
) -> tuple[list[PullRequestRecord], list[IssueMetricRecord]]:
    """Fetch issues and merge changesets from Redmine REST API with pagination."""
    if dry_run and client is None and not api_key:
        return build_synthetic_productivity_data(project=project_id, team=team, platforms=["redmine"])

    headers = {"Accept": "application/json", "User-Agent": "nexcoder-planning"}
    if api_key:
        headers["X-Redmine-API-Key"] = api_key

    owned_client = client is None
    http = client or httpx.Client(headers=headers, timeout=30.0)
    base = base_url.rstrip("/")

    prs: list[PullRequestRecord] = []
    issues: list[IssueMetricRecord] = []

    try:
        offset = 0
        limit = 100
        while True:
            resp = http.get(
                f"{base}/issues.json",
                params={"project_id": project_id, "status_id": "*", "offset": offset, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            raw_issues = data.get("issues", [])
            if not raw_issues:
                break

            for item in raw_issues:
                iid = item.get("id", 0)
                created_at = item.get("created_on") or "2026-11-01T00:00:00Z"
                closed_at = item.get("closed_on") or item.get("updated_on")
                status_obj = item.get("status") or {}
                status_name = str(status_obj.get("name", "open")).lower()
                is_closed = bool(status_obj.get("is_closed")) or status_name in ("closed", "resolved", "merged")
                assigned_obj = item.get("assigned_to") or item.get("author") or {}
                assignee = str(assigned_obj.get("name") or assigned_obj.get("login") or "developer")
                tracker_name = str((item.get("tracker") or {}).get("name", "Issue")).lower()

                cycle = _hours_between(created_at, closed_at if is_closed else None) or 0.0
                if tracker_name in ("pull request", "merge request", "patch"):
                    rev_hours = round(cycle * 0.3, 2) if cycle > 0 else 2.0
                    prs.append(
                        PullRequestRecord(
                            id=f"rm-pr-{iid}",
                            platform="redmine",
                            repo=project_id,
                            author=assignee,
                            team=team,
                            title=str(item.get("subject", "")),
                            state="merged" if is_closed else "open",
                            created_at=created_at,
                            first_review_at=closed_at,
                            merged_at=closed_at if is_closed else None,
                            review_time_hours=rev_hours,
                            lead_time_hours=cycle,
                            week=_iso_week_label(closed_at or created_at),
                        )
                    )
                else:
                    issues.append(
                        IssueMetricRecord(
                            id=f"rm-iss-{iid}",
                            platform="redmine",
                            project=project_id,
                            assignee=assignee,
                            team=team,
                            title=str(item.get("subject", "")),
                            state="closed" if is_closed else "open",
                            created_at=created_at,
                            closed_at=closed_at if is_closed else None,
                            cycle_time_hours=cycle,
                            estimate_hours=float(item.get("estimated_hours") or 0.0),
                            week=_iso_week_label(closed_at or created_at),
                        )
                    )

            total_count = int(data.get("total_count", len(raw_issues)))
            offset += len(raw_issues)
            if offset >= total_count or len(raw_issues) < limit:
                break
    finally:
        if owned_client:
            http.close()

    return prs, issues


# ---------------------------------------------------------------------------
# Metrics Calculation & NexDash Dataset Builder
# ---------------------------------------------------------------------------


def compute_productivity_metrics(
    prs: list[PullRequestRecord],
    issues: list[IssueMetricRecord],
    *,
    project: str = "nexcoder-platform",
    team: str = "core-engineering",
    period: str = "2026-Q4",
    platforms: list[str] | None = None,
) -> ProductivityReportMetrics:
    """Aggregate PR and issue records into team productivity metrics."""
    merged_prs = [p for p in prs if p.state == "merged"]
    closed_issues = [i for i in issues if i.state == "closed"]

    prs_opened = len(prs)
    prs_merged = len(merged_prs)
    pr_merge_rate = round((prs_merged / prs_opened) * 100.0, 1) if prs_opened > 0 else 0.0

    review_times = [p.review_time_hours for p in prs if p.review_time_hours > 0]
    lead_times = [p.lead_time_hours for p in merged_prs if p.lead_time_hours > 0]

    avg_review = round(statistics.mean(review_times), 2) if review_times else 0.0
    med_review = round(statistics.median(review_times), 2) if review_times else 0.0
    avg_lead = round(statistics.mean(lead_times), 2) if lead_times else 0.0
    med_lead = round(statistics.median(lead_times), 2) if lead_times else 0.0

    issues_opened = len(issues)
    issues_closed_count = len(closed_issues)
    issue_res_rate = round((issues_closed_count / issues_opened) * 100.0, 1) if issues_opened > 0 else 0.0

    # Group by author/assignee
    authors: set[str] = {p.author for p in prs} | {i.assignee for i in issues}
    author_list: list[AuthorThroughput] = []
    for person in sorted(authors):
        p_merged = [p for p in merged_prs if p.author == person]
        i_closed = [i for i in closed_issues if i.assignee == person]
        p_rev = [p.review_time_hours for p in prs if p.author == person and p.review_time_hours > 0]
        p_lead = [p.lead_time_hours for p in p_merged if p.lead_time_hours > 0]
        total_done = len(p_merged) + len(i_closed)
        author_list.append(
            AuthorThroughput(
                author=person,
                team=team,
                prs_merged=len(p_merged),
                issues_closed=len(i_closed),
                avg_review_time_hours=round(statistics.mean(p_rev), 2) if p_rev else 0.0,
                avg_lead_time_hours=round(statistics.mean(p_lead), 2) if p_lead else 0.0,
                total_items_completed=total_done,
            )
        )
    author_list.sort(key=lambda a: (-a.total_items_completed, a.author))

    # Group by week
    weeks = sorted({p.week for p in prs} | {i.week for i in issues})
    weekly_points: list[WeeklyProductivityPoint] = []
    for wk in weeks:
        w_prs = [p for p in prs if p.week == wk]
        w_merged = [p for p in merged_prs if p.week == wk]
        w_issues = [i for i in closed_issues if i.week == wk]
        w_rev = [p.review_time_hours for p in w_prs if p.review_time_hours > 0]
        w_lead = [p.lead_time_hours for p in w_merged if p.lead_time_hours > 0]
        weekly_points.append(
            WeeklyProductivityPoint(
                week=wk,
                prs_opened=len(w_prs),
                prs_merged=len(w_merged),
                issues_closed=len(w_issues),
                avg_review_time_hours=round(statistics.mean(w_rev), 2) if w_rev else 0.0,
                avg_lead_time_hours=round(statistics.mean(w_lead), 2) if w_lead else 0.0,
            )
        )

    # Group by platform
    active_platforms = platforms or sorted({p.platform for p in prs} | {i.platform for i in issues})
    platform_items: list[PlatformProductivityBreakdown] = []
    for plat in active_platforms:
        pl_prs = [p for p in prs if p.platform == plat]
        pl_merged = [p for p in merged_prs if p.platform == plat]
        pl_iss = [i for i in issues if i.platform == plat]
        pl_closed = [i for i in closed_issues if i.platform == plat]
        pl_rev = [p.review_time_hours for p in pl_prs if p.review_time_hours > 0]
        pl_lead = [p.lead_time_hours for p in pl_merged if p.lead_time_hours > 0]
        platform_items.append(
            PlatformProductivityBreakdown(
                platform=plat,
                prs_opened=len(pl_prs),
                prs_merged=len(pl_merged),
                issues_opened=len(pl_iss),
                issues_closed=len(pl_closed),
                avg_review_time_hours=round(statistics.mean(pl_rev), 2) if pl_rev else 0.0,
                avg_lead_time_hours=round(statistics.mean(pl_lead), 2) if pl_lead else 0.0,
            )
        )

    return ProductivityReportMetrics(
        project=project,
        team=team,
        period=period,
        platforms=list(active_platforms),
        prs_opened=prs_opened,
        prs_merged=prs_merged,
        pr_merge_rate_pct=pr_merge_rate,
        avg_review_time_hours=avg_review,
        median_review_time_hours=med_review,
        avg_lead_time_hours=avg_lead,
        median_lead_time_hours=med_lead,
        issues_opened=issues_opened,
        issues_closed=issues_closed_count,
        issue_resolution_rate_pct=issue_res_rate,
        throughput_by_author=author_list,
        weekly_trend=weekly_points,
        platform_breakdown=platform_items,
    )


def build_productivity_nexdash_dataset(metrics: ProductivityReportMetrics) -> dict[str, Any]:
    """Build semantic cube, query plan, KPIs, and rule-compliant charts for NexDash."""
    cube = NexDashCubeSpec(
        name="dev_productivity",
        table="fact_dev_productivity",
        description="Metricas de produtividade de engenharia coletadas de GitHub, Azure DevOps e Redmine.",
        dimensions=[
            NexDashDimensionSpec(name="project", type="string", description="Projeto monitorado"),
            NexDashDimensionSpec(name="team", type="string", description="Time de engenharia"),
            NexDashDimensionSpec(name="platform", type="string", description="Ferramenta de origem"),
            NexDashDimensionSpec(name="author", type="string", description="Pessoa desenvolvedora"),
            NexDashDimensionSpec(name="week", type="string", description="Semana ISO"),
        ],
        metrics=[
            NexDashMetricSpec(name="prs_merged", aggregation="sum", column="prs_merged"),
            NexDashMetricSpec(name="issues_closed", aggregation="sum", column="issues_closed"),
            NexDashMetricSpec(name="avg_review_time_hours", aggregation="avg", column="review_time_hours"),
            NexDashMetricSpec(name="avg_lead_time_hours", aggregation="avg", column="lead_time_hours"),
        ],
        allowed_filters=["project", "team", "platform", "week"],
    )

    plan = NexDashQueryPlan(
        cube="dev_productivity",
        metrics=["prs_merged", "issues_closed", "avg_review_time_hours", "avg_lead_time_hours"],
        dimensions=["author", "platform", "week"],
        filters=[
            NexDashPlanFilter(field="project", operator="eq", value=metrics.project),
            NexDashPlanFilter(field="team", operator="eq", value=metrics.team),
        ],
        limit=100,
    )

    lead_delta = ""
    if len(metrics.weekly_trend) >= 2:
        first_lt = metrics.weekly_trend[0].avg_lead_time_hours
        last_lt = metrics.weekly_trend[-1].avg_lead_time_hours
        if first_lt > 0:
            pct_change = round(((last_lt - first_lt) / first_lt) * 100.0)
            sign = "+" if pct_change > 0 else ""
            lead_delta = f"{sign}{pct_change}%"

    kpis = [
        NexDashComputedKPI(
            id="prs_merged",
            label="PRs Mesclados",
            value=metrics.prs_merged,
            formatted_value=f"{metrics.prs_merged} / {metrics.prs_opened}",
            unit="PRs",
            delta=f"{metrics.pr_merge_rate_pct:.1f}%",
            comparison_label="taxa de merge no periodo",
            status="good" if metrics.pr_merge_rate_pct >= 75.0 else "neutral",
        ),
        NexDashComputedKPI(
            id="avg_review_time",
            label="Tempo Medio de Review",
            value=metrics.avg_review_time_hours,
            formatted_value=f"{metrics.avg_review_time_hours:.1f} h".replace(".", ","),
            unit="h",
            delta=f"mediana {metrics.median_review_time_hours:.1f} h".replace(".", ","),
            comparison_label="meta < 4,0 h",
            status="good" if metrics.avg_review_time_hours <= 4.0 else "warning",
        ),
        NexDashComputedKPI(
            id="avg_lead_time",
            label="Lead Time ate Merge",
            value=metrics.avg_lead_time_hours,
            formatted_value=f"{metrics.avg_lead_time_hours:.1f} h".replace(".", ","),
            unit="h",
            delta=lead_delta or f"mediana {metrics.median_lead_time_hours:.1f} h".replace(".", ","),
            comparison_label="entre primeira e ultima semana",
            status="good" if metrics.avg_lead_time_hours <= 16.0 else "warning",
        ),
        NexDashComputedKPI(
            id="issues_closed",
            label="Issues Fechadas",
            value=metrics.issues_closed,
            formatted_value=f"{metrics.issues_closed} / {metrics.issues_opened}",
            unit="issues",
            delta=f"{metrics.issue_resolution_rate_pct:.1f}%",
            comparison_label="taxa de resolucao",
            status="good" if metrics.issue_resolution_rate_pct >= 80.0 else "neutral",
        ),
    ]

    top_author = metrics.throughput_by_author[0].author if metrics.throughput_by_author else None
    top_author_count = metrics.throughput_by_author[0].total_items_completed if metrics.throughput_by_author else 0

    best_week = (
        min(metrics.weekly_trend, key=lambda w: w.avg_lead_time_hours if w.avg_lead_time_hours > 0 else 9999.0).week
        if metrics.weekly_trend
        else None
    )

    sorted_platforms = sorted(metrics.platform_breakdown, key=lambda p: -p.avg_review_time_hours)
    slowest_platform = sorted_platforms[0].platform if sorted_platforms else None

    charts = [
        NexDashComputedChart(
            id="throughput_by_author",
            type="bar",
            title=f"{top_author or 'Time'} liderou as entregas com {top_author_count} itens concluidos",
            subtitle=f"Total de PRs mesclados + issues fechadas por pessoa, {metrics.period} (itens)",
            question="Quem entregou mais itens concluidos no periodo?",
            x="Pessoa",
            y="Itens concluidos",
            unit="itens",
            labels=[a.author for a in metrics.throughput_by_author],
            values=[float(a.total_items_completed) for a in metrics.throughput_by_author],
            highlight_label=top_author,
            annotation="Inclui PRs mesclados e issues encerradas nas fontes conectadas.",
            alt_text=(
                f"Ranking de entregas por pessoa no periodo {metrics.period}: "
                + ", ".join(f"{a.author} ({a.total_items_completed})" for a in metrics.throughput_by_author)
            ),
        ),
        NexDashComputedChart(
            id="lead_time_by_week",
            type="line",
            title=(
                f"Lead time caiu {lead_delta} ao longo do periodo"
                if lead_delta.startswith("-")
                else f"Evolucao semanal do lead time medio ({metrics.avg_lead_time_hours:.1f} h)"
            ),
            subtitle=f"Tempo medio da abertura ate o merge por semana, {metrics.period} (horas)",
            question="Como o lead time de entrega mudou ao longo das semanas?",
            x="Semana",
            y="Lead time medio (h)",
            unit="h",
            labels=[w.week for w in metrics.weekly_trend],
            values=[w.avg_lead_time_hours for w in metrics.weekly_trend],
            highlight_label=best_week,
            annotation=f"Menor lead time registrado na semana {best_week}." if best_week else "",
            alt_text=(
                "Evolucao semanal do lead time em horas: "
                + ", ".join(f"{w.week} ({w.avg_lead_time_hours}h)" for w in metrics.weekly_trend)
            ),
        ),
        NexDashComputedChart(
            id="review_time_by_platform",
            type="bar",
            title=f"Tempo medio de code review por plataforma (pico em {slowest_platform or 'n/a'})",
            subtitle=f"Horas ate o primeiro review por ferramenta de gestao, {metrics.period} (horas)",
            question="Em qual plataforma os reviews demoram mais?",
            x="Plataforma",
            y="Tempo de review (h)",
            unit="h",
            labels=[p.platform for p in sorted_platforms],
            values=[p.avg_review_time_hours for p in sorted_platforms],
            highlight_label=slowest_platform,
            annotation="Meta do time: primeiro review em ate 4,0 horas uteis.",
            alt_text=(
                "Tempo medio de review por plataforma: "
                + ", ".join(f"{p.platform} ({p.avg_review_time_hours}h)" for p in sorted_platforms)
            ),
        ),
    ]

    rows = [a.model_dump() for a in metrics.throughput_by_author]
    platforms_str = ", ".join(metrics.platforms)

    return {
        "title": (
            f"Produtividade do time {metrics.team}: {metrics.prs_merged} PRs mesclados "
            f"e {metrics.issues_closed} issues fechadas"
        ),
        "subtitle": f"Projeto {metrics.project} no periodo {metrics.period} (fontes: {platforms_str})",
        "cube": cube.model_dump(),
        "plan": plan.model_dump(),
        "kpis": [k.model_dump() for k in kpis],
        "charts": [c.model_dump() for c in charts],
        "rows": rows,
        "source_summary": f"Conectores nexcoder-planning ({platforms_str}) -> motor nexdash",
    }


def generate_productivity_dashboard(
    *,
    project: str = "nexcoder-platform",
    team: str = "core-engineering",
    period: str = "2026-Q4",
    platforms: list[str] | None = None,
    prs: list[PullRequestRecord] | None = None,
    issues: list[IssueMetricRecord] | None = None,
    nexdash_client: NexDashClient | None = None,
    transport: TransportKind = "offline",
    nexdash_url: str = "http://127.0.0.1:8080",
    api_token: str | None = None,
) -> tuple[ProductivityReportMetrics, NexDashDashboardBundle]:
    """Collect or use supplied productivity data, compute metrics, and build a NexDash dashboard."""
    selected_platforms = platforms or ["github", "azure_devops", "redmine"]
    if prs is None or issues is None:
        syn_prs, syn_issues = build_synthetic_productivity_data(
            project=project,
            team=team,
            platforms=selected_platforms,
        )
        active_prs = prs if prs is not None else syn_prs
        active_issues = issues if issues is not None else syn_issues
    else:
        active_prs = prs
        active_issues = issues

    metrics = compute_productivity_metrics(
        active_prs,
        active_issues,
        project=project,
        team=team,
        period=period,
        platforms=selected_platforms,
    )
    dataset = build_productivity_nexdash_dataset(metrics)

    client = nexdash_client or NexDashClient(
        transport=transport,
        base_url=nexdash_url,
        api_token=api_token,
    )
    parameters = {
        "project": project,
        "team": team,
        "period": period,
        "platforms": selected_platforms,
    }
    bundle = client.generate_dashboard(
        model_id="dev_productivity",
        parameters=parameters,
        dataset=dataset,
    )
    return metrics, bundle
