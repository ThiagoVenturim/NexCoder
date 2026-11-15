"""Tests for Azure DevOps provider with offline HTTP mock transport."""

import json

import httpx
import pytest
from nexcoder_planning.vcs import AzureDevOpsProvider


def mock_azure_devops_handler(request: httpx.Request) -> httpx.Response:
    url_str = str(request.url)

    # Authorization header check
    auth_header = request.headers.get("Authorization", "")
    assert auth_header.startswith("Basic "), "Expected Basic auth with PAT"

    # Repositories
    if "/_apis/git/repositories?" in url_str or url_str.endswith("/_apis/git/repositories"):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "repo-uuid-1",
                            "name": "BackendService",
                            "description": "Core service",
                            "defaultBranch": "refs/heads/main",
                            "webUrl": "https://dev.azure.com/myorg/myproj/_git/BackendService",
                            "remoteUrl": "https://dev.azure.com/myorg/myproj/_git/BackendService",
                            "sshUrl": "git@ssh.dev.azure.com:v3/myorg/myproj/BackendService",
                        }
                    ]
                },
            )
        elif request.method == "POST":
            data = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": "repo-uuid-2",
                    "name": data.get("name"),
                    "webUrl": f"https://dev.azure.com/myorg/myproj/_git/{data.get('name')}",
                    "remoteUrl": f"https://dev.azure.com/myorg/myproj/_git/{data.get('name')}",
                },
            )

    # Single Repo
    if "/_apis/git/repositories/repo-uuid-1?" in url_str or url_str.endswith("/repo-uuid-1"):
        return httpx.Response(
            200,
            json={
                "id": "repo-uuid-1",
                "name": "BackendService",
                "description": "Core service",
                "defaultBranch": "refs/heads/main",
                "webUrl": "https://dev.azure.com/myorg/myproj/_git/BackendService",
                "remoteUrl": "https://dev.azure.com/myorg/myproj/_git/BackendService",
                "sshUrl": "git@ssh.dev.azure.com:v3/myorg/myproj/BackendService",
            },
        )

    # WIQL query
    if "/_apis/wit/wiql" in url_str:
        return httpx.Response(
            200,
            json={"workItems": [{"id": 401, "url": "https://dev.azure.com/myorg/myproj/_apis/wit/workitems/401"}]},
        )

    # Batch work items
    if "/_apis/wit/workitems?" in url_str and "ids=" in url_str:
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": 401,
                        "url": "https://dev.azure.com/myorg/myproj/_apis/wit/workitems/401",
                        "fields": {
                            "System.Title": "Add payment gateway",
                            "System.Description": "Implement Stripe checkout",
                            "System.State": "Active",
                            "System.Tags": "backend; payment",
                            "System.CreatedBy": {"displayName": "Lead Engineer"},
                        },
                    }
                ]
            },
        )

    # Single work item GET
    if "/_apis/wit/workitems/401?" in url_str and request.method == "GET":
        return httpx.Response(
            200,
            json={
                "id": 401,
                "url": "https://dev.azure.com/myorg/myproj/_apis/wit/workitems/401",
                "fields": {
                    "System.Title": "Add payment gateway",
                    "System.Description": "Implement Stripe checkout",
                    "System.State": "Active",
                    "System.Tags": "backend; payment",
                    "System.CreatedBy": {"displayName": "Lead Engineer"},
                },
            },
        )

    # Create work item POST
    if "/_apis/wit/workitems/$Task" in url_str:
        patch_ops = json.loads(request.content)
        title = next((op["value"] for op in patch_ops if op.get("path") == "/fields/System.Title"), "New Task")
        body = next((op["value"] for op in patch_ops if op.get("path") == "/fields/System.Description"), "")
        return httpx.Response(
            200,
            json={
                "id": 402,
                "url": "https://dev.azure.com/myorg/myproj/_apis/wit/workitems/402",
                "fields": {
                    "System.Title": title,
                    "System.Description": body,
                    "System.State": "New",
                },
            },
        )

    # Update work item PATCH
    if "/_apis/wit/workitems/401" in url_str and request.method == "PATCH":
        return httpx.Response(
            200,
            json={
                "id": 401,
                "url": "https://dev.azure.com/myorg/myproj/_apis/wit/workitems/401",
                "fields": {
                    "System.Title": "Updated title",
                    "System.Description": "Updated body",
                    "System.State": "Closed",
                },
            },
        )

    # Pull Requests GET & POST
    if "/pullrequests" in url_str:
        if request.method == "GET" and not url_str.endswith("/pr-101") and "/pullrequests/101" not in url_str:
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "pullRequestId": 101,
                            "title": "feat: add payment gateway",
                            "description": "Closes 401",
                            "sourceRefName": "refs/heads/feature/payment",
                            "targetRefName": "refs/heads/main",
                            "status": "active",
                            "createdBy": {"displayName": "Lead Engineer"},
                            "url": "https://dev.azure.com/myorg/myproj/_git/repo-uuid-1/pullrequest/101",
                        }
                    ]
                },
            )
        elif request.method == "POST":
            data = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "pullRequestId": 102,
                    "title": data.get("title"),
                    "description": data.get("description"),
                    "sourceRefName": data.get("sourceRefName"),
                    "targetRefName": data.get("targetRefName"),
                    "status": "active",
                    "url": "https://dev.azure.com/myorg/myproj/_git/repo-uuid-1/pullrequest/102",
                },
            )
        elif request.method == "PATCH":
            # Merge PR
            return httpx.Response(
                200,
                json={
                    "pullRequestId": 101,
                    "title": "feat: add payment gateway",
                    "status": "completed",
                    "sourceRefName": "refs/heads/feature/payment",
                    "targetRefName": "refs/heads/main",
                    "url": "https://dev.azure.com/myorg/myproj/_git/repo-uuid-1/pullrequest/101",
                },
            )
        elif request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "pullRequestId": 101,
                    "title": "feat: add payment gateway",
                    "description": "Closes 401",
                    "sourceRefName": "refs/heads/feature/payment",
                    "targetRefName": "refs/heads/main",
                    "status": "active",
                    "createdBy": {"displayName": "Lead Engineer"},
                    "url": "https://dev.azure.com/myorg/myproj/_git/repo-uuid-1/pullrequest/101",
                },
            )

    # Pipelines GET & POST
    if "/_apis/pipelines" in url_str:
        if "/runs" in url_str:
            if request.method == "POST":
                return httpx.Response(
                    200,
                    json={
                        "id": 8801,
                        "state": "inProgress",
                        "createdDate": "2026-11-15T12:00:00Z",
                        "url": "https://dev.azure.com/myorg/myproj/_apis/pipelines/1/runs/8801",
                    },
                )
            else:
                return httpx.Response(
                    200,
                    json={
                        "id": 8801,
                        "state": "completed",
                        "result": "succeeded",
                        "createdDate": "2026-11-15T12:00:00Z",
                        "url": "https://dev.azure.com/myorg/myproj/_apis/pipelines/1/runs/8801",
                    },
                )
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": 1,
                        "name": "CI-Build",
                        "url": "https://dev.azure.com/myorg/myproj/_apis/pipelines/1",
                    }
                ]
            },
        )

    return httpx.Response(404, json={"message": f"Route not found: {url_str}"})


@pytest.fixture
def ado_provider():
    transport = httpx.MockTransport(mock_azure_devops_handler)
    client = httpx.Client(transport=transport)
    return AzureDevOpsProvider(
        organization="myorg",
        project="myproj",
        pat="mock-ado-pat-xyz",
        repository_id="repo-uuid-1",
        client=client,
    )


def test_azure_devops_repos(ado_provider):
    repos = ado_provider.list_repositories()
    assert len(repos) == 1
    assert repos[0].name == "BackendService"
    assert repos[0].default_branch == "main"

    single = ado_provider.get_repository("repo-uuid-1")
    assert single.id == "repo-uuid-1"

    created = ado_provider.create_repository("NewService", "Microservice")
    assert created.name == "NewService"


def test_azure_devops_work_items(ado_provider):
    # List issues
    issues = ado_provider.list_issues(state="open")
    assert len(issues) == 1
    assert issues[0].title == "Add payment gateway"
    assert "payment" in issues[0].labels

    # Get single issue
    issue = ado_provider.get_issue("401")
    assert issue.id == "401"
    assert issue.state == "open"

    # Create issue
    new_issue = ado_provider.create_issue(
        title="New task title",
        body="Description content",
        labels=["feature", "p1"],
    )
    assert new_issue.id == "402"
    assert new_issue.title == "New task title"

    # Update issue
    updated = ado_provider.update_issue("401", title="Updated title", state="closed")
    assert updated.state == "closed"


def test_azure_devops_pull_requests(ado_provider):
    # List PRs
    prs = ado_provider.list_pull_requests()
    assert len(prs) == 1
    assert prs[0].source_branch == "feature/payment"

    # Get PR
    pr = ado_provider.get_pull_request("101")
    assert pr.id == "101"

    # Create PR
    created = ado_provider.create_pull_request(
        title="feat: checkout logic",
        body="Closes #402",
        source_branch="feature/checkout",
        target_branch="main",
    )
    assert created.id == "102"
    assert created.title == "feat: checkout logic"

    # Merge PR
    merged = ado_provider.merge_pull_request("101", commit_message="Merge PR 101")
    assert merged.state == "merged"


def test_azure_devops_pipelines(ado_provider):
    pipelines = ado_provider.list_pipelines()
    assert len(pipelines) == 1
    assert pipelines[0].name == "CI-Build"

    run = ado_provider.trigger_pipeline("1", ref="main", variables={"DEPLOY_ENV": "staging"})
    assert run.id == "8801"
    assert run.status == "inProgress"

    status = ado_provider.get_pipeline_run("1", "8801")
    assert status.status == "success"
