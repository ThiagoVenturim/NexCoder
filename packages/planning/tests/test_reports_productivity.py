from __future__ import annotations

import json

import httpx
from nexcoder_core.reports import (
    LocalNexDashEngine,
    NexDashClient,
    create_nexdash_mock_transport,
)
from nexcoder_planning.adapters.redmine import RedmineAdapter
from nexcoder_planning.models import Task
from nexcoder_planning.reports import (
    build_synthetic_productivity_data,
    collect_azure_devops_productivity,
    collect_github_productivity,
    collect_redmine_productivity,
    compute_productivity_metrics,
    generate_productivity_dashboard,
)


def test_redmine_adapter_dry_run_and_mock_http() -> None:
    adapter_dry = RedmineAdapter(project_id="nexcoder", api_key="secret-redmine-key", dry_run=True)
    assert "***" in repr(adapter_dry)
    assert "secret-redmine-key" not in repr(adapter_dry)

    task = Task(id="TSK-10", title="Add Redmine connector", estimate_hours=4.0)
    res_dry = adapter_dry.create_issue(task)
    assert res_dry.action == "dry_run_create"
    assert res_dry.dry_run is True

    stored_issues: list[dict] = [
        {
            "id": 401,
            "subject": "Existing task",
            "description": f"Initial body\n\n<!-- nexcoder-id: {task.nexcoder_id} -->",
            "status": {"name": "In Progress", "is_closed": False},
            "tracker": {"name": "Feature"},
        }
    ]

    def _mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/issues.json":
            return httpx.Response(
                status_code=200,
                json={"issues": stored_issues, "total_count": len(stored_issues), "offset": 0, "limit": 100},
            )
        if request.method == "PUT" and request.url.path == "/issues/401.json":
            return httpx.Response(status_code=204)
        if request.method == "POST" and request.url.path == "/issues.json":
            body = json.loads(request.content.decode("utf-8"))
            new_id = 402
            stored_issues.append(
                {
                    "id": new_id,
                    "subject": body["issue"]["subject"],
                    "description": body["issue"]["description"],
                    "status": {"name": "New", "is_closed": False},
                }
            )
            return httpx.Response(status_code=201, json={"issue": {"id": new_id}})
        return httpx.Response(status_code=404)

    with httpx.Client(transport=httpx.MockTransport(_mock_handler)) as client:
        adapter = RedmineAdapter(
            project_id="nexcoder",
            api_key="rm-key",
            base_url="https://redmine.example.local",
            client=client,
            dry_run=False,
        )
        issues = adapter.list_issues()
        assert len(issues) == 1
        assert issues[0].nexcoder_id == task.nexcoder_id

        sync_res = adapter.sync_task(task, dry_run=False)
        assert sync_res.action == "updated"
        assert sync_res.remote_number == 401

        task2 = Task(id="TSK-11", title="New Redmine task", estimate_hours=2.0)
        sync_res2 = adapter.sync_task(task2, dry_run=False)
        assert sync_res2.action == "created"
        assert sync_res2.remote_number == 402


def test_collectors_normalize_mock_http_responses() -> None:
    def _gh_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pulls"):
            return httpx.Response(
                200,
                json=[
                    {
                        "number": 10,
                        "title": "feat: add reports",
                        "state": "closed",
                        "created_at": "2026-10-20T08:00:00Z",
                        "first_review_at": "2026-10-20T10:30:00Z",
                        "merged_at": "2026-10-20T20:00:00Z",
                        "user": {"login": "ana"},
                        "comments": 3,
                    }
                ],
            )
        if request.url.path.endswith("/issues"):
            return httpx.Response(
                200,
                json=[
                    {
                        "number": 77,
                        "title": "Productivity reports",
                        "state": "closed",
                        "created_at": "2026-10-19T08:00:00Z",
                        "closed_at": "2026-10-20T20:00:00Z",
                        "assignee": {"login": "ana"},
                    }
                ],
            )
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(_gh_handler)) as gh_client:
        gh_prs, gh_issues = collect_github_productivity("ThiagoVenturim/NexCoder", client=gh_client, dry_run=False)
        assert len(gh_prs) == 1
        assert gh_prs[0].review_time_hours == 2.5
        assert gh_prs[0].lead_time_hours == 12.0
        assert len(gh_issues) == 1
        assert gh_issues[0].cycle_time_hours == 36.0

    def _ado_handler(request: httpx.Request) -> httpx.Response:
        if "pullrequests" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "pullRequestId": 50,
                            "title": "fix: ado sync",
                            "status": "completed",
                            "creationDate": "2026-10-21T09:00:00Z",
                            "firstReviewDate": "2026-10-21T12:00:00Z",
                            "closedDate": "2026-10-21T21:00:00Z",
                            "createdBy": {"uniqueName": "bruno"},
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": 60,
                        "fields": {
                            "System.Title": "ADO work item",
                            "System.State": "Closed",
                            "System.CreatedDate": "2026-10-21T08:00:00Z",
                            "Microsoft.VSTS.Common.ClosedDate": "2026-10-22T08:00:00Z",
                            "System.AssignedTo": {"uniqueName": "bruno"},
                        },
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(_ado_handler)) as ado_client:
        ado_prs, ado_issues = collect_azure_devops_productivity(
            "org", "proj", client=ado_client, dry_run=False
        )
        assert len(ado_prs) == 1
        assert ado_prs[0].review_time_hours == 3.0
        assert ado_prs[0].lead_time_hours == 12.0
        assert len(ado_issues) == 1
        assert ado_issues[0].state == "closed"

    def _rm_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "issues": [
                    {
                        "id": 91,
                        "subject": "Redmine issue",
                        "created_on": "2026-10-22T10:00:00Z",
                        "closed_on": "2026-10-23T02:00:00Z",
                        "status": {"name": "Closed", "is_closed": True},
                        "tracker": {"name": "Bug"},
                        "assigned_to": {"name": "carla"},
                        "estimated_hours": 4.0,
                    },
                    {
                        "id": 92,
                        "subject": "Redmine merge request",
                        "created_on": "2026-10-22T10:00:00Z",
                        "closed_on": "2026-10-22T20:00:00Z",
                        "status": {"name": "Merged", "is_closed": True},
                        "tracker": {"name": "Merge Request"},
                        "assigned_to": {"name": "carla"},
                    },
                ],
                "total_count": 2,
                "offset": 0,
                "limit": 100,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(_rm_handler)) as rm_client:
        rm_prs, rm_issues = collect_redmine_productivity("legacy-core", client=rm_client, dry_run=False)
        assert len(rm_prs) == 1
        assert rm_prs[0].lead_time_hours == 10.0
        assert len(rm_issues) == 1
        assert rm_issues[0].cycle_time_hours == 16.0


def test_generate_productivity_dashboard_offline_mcp_and_rest() -> None:
    prs, issues = build_synthetic_productivity_data(project="nexcoder", team="platform-squad")
    metrics = compute_productivity_metrics(prs, issues, project="nexcoder", team="platform-squad")
    assert metrics.prs_opened == 8
    assert metrics.prs_merged == 7
    assert metrics.issues_opened == 8
    assert metrics.issues_closed == 7
    assert len(metrics.throughput_by_author) == 4
    assert metrics.throughput_by_author[0].author == "ana.silva"

    # Offline generation
    _m_off, bundle_off = generate_productivity_dashboard(
        project="nexcoder",
        team="platform-squad",
        period="2026-Q4",
        transport="offline",
    )
    assert bundle_off.status == "success"
    assert bundle_off.model_id == "dev_productivity"
    assert len(bundle_off.kpis) == 4
    assert len(bundle_off.charts) == 3
    assert "window.NEXDASH_DATA=" in bundle_off.html

    # MCP generation
    engine = LocalNexDashEngine()
    mcp_client = NexDashClient(transport="mcp", engine=engine)
    _m_mcp, bundle_mcp = generate_productivity_dashboard(
        project="nexcoder",
        team="platform-squad",
        period="2026-Q4",
        nexdash_client=mcp_client,
    )
    assert bundle_mcp.transport == "mcp"
    assert bundle_mcp.total_rows == 4

    # REST generation
    mock_transport = create_nexdash_mock_transport(engine=engine, api_token="tok-prod")
    with httpx.Client(transport=mock_transport, base_url="http://nexdash.local") as http_client:
        rest_client = NexDashClient(
            transport="rest",
            base_url="http://nexdash.local",
            api_token="tok-prod",
            http_client=http_client,
        )
        _m_rest, bundle_rest = generate_productivity_dashboard(
            project="nexcoder",
            team="platform-squad",
            period="2026-Q4",
            nexdash_client=rest_client,
        )
        assert bundle_rest.transport == "rest"
        assert "throughput_by_author" in [c.id for c in bundle_rest.charts]
