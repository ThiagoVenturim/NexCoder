"""Tests for GitLab provider with offline HTTP mock transport."""

import json

import httpx
import pytest
from nexcoder_planning.vcs import GitLabProvider


def mock_gitlab_handler(request: httpx.Request) -> httpx.Response:
    url_str = str(request.url)

    # Auth check
    token = request.headers.get("PRIVATE-TOKEN")
    assert token == "mock-gl-token-123", "Expected correct PRIVATE-TOKEN header"

    # Project GET
    if url_str.endswith("/projects/999"):
        return httpx.Response(
            200,
            json={
                "id": 999,
                "name": "api-gateway",
                "description": "Public API Gateway",
                "default_branch": "develop",
                "web_url": "https://gitlab.com/group/api-gateway",
                "http_url_to_repo": "https://gitlab.com/group/api-gateway.git",
                "ssh_url_to_repo": "git@gitlab.com:group/api-gateway.git",
                "visibility": "private",
            },
        )

    # Projects POST (create)
    if url_str.endswith("/projects") and request.method == "POST":
        data = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": 1001,
                "name": data.get("name"),
                "description": data.get("description"),
                "default_branch": "main",
                "web_url": f"https://gitlab.com/group/{data.get('name')}",
                "http_url_to_repo": f"https://gitlab.com/group/{data.get('name')}.git",
                "ssh_url_to_repo": f"git@gitlab.com:group/{data.get('name')}.git",
                "visibility": data.get("visibility"),
            },
        )

    # Issues GET & POST
    if "/issues" in url_str:
        if request.method == "GET" and not url_str.endswith("/issues/10"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 501,
                        "iid": 10,
                        "title": "OAuth2 Token Expiry Bug",
                        "description": "Fix token refresh",
                        "state": "opened",
                        "author": {"name": "Security Specialist"},
                        "web_url": "https://gitlab.com/group/api-gateway/-/issues/10",
                        "labels": ["security", "auth"],
                        "created_at": "2026-11-15T10:00:00Z",
                        "updated_at": "2026-11-15T11:00:00Z",
                    }
                ],
            )
        elif request.method == "POST":
            data = json.loads(request.content)
            labels = [lbl.strip() for lbl in data.get("labels", "").split(",") if lbl.strip()]
            return httpx.Response(
                201,
                json={
                    "id": 502,
                    "iid": 11,
                    "title": data.get("title"),
                    "description": data.get("description"),
                    "state": "opened",
                    "author": {"name": "Agent Builder"},
                    "web_url": "https://gitlab.com/group/api-gateway/-/issues/11",
                    "labels": labels,
                },
            )
        elif request.method == "GET" and url_str.endswith("/issues/10"):
            return httpx.Response(
                200,
                json={
                    "id": 501,
                    "iid": 10,
                    "title": "OAuth2 Token Expiry Bug",
                    "description": "Fix token refresh",
                    "state": "opened",
                    "author": {"name": "Security Specialist"},
                    "web_url": "https://gitlab.com/group/api-gateway/-/issues/10",
                    "labels": ["security", "auth"],
                },
            )
        elif request.method == "PUT":
            data = json.loads(request.content)
            state = "closed" if data.get("state_event") == "close" else "opened"
            return httpx.Response(
                200,
                json={
                    "id": 501,
                    "iid": 10,
                    "title": data.get("title", "OAuth2 Token Expiry Bug"),
                    "description": data.get("description", "Fix token refresh"),
                    "state": state,
                    "author": {"name": "Security Specialist"},
                    "web_url": "https://gitlab.com/group/api-gateway/-/issues/10",
                    "labels": ["security", "auth"],
                },
            )

    # Merge Requests GET & POST & PUT
    if "/merge_requests" in url_str:
        if "/merge" in url_str and request.method == "PUT":
            return httpx.Response(
                200,
                json={
                    "id": 801,
                    "iid": 25,
                    "title": "Resolve OAuth2 bug",
                    "state": "merged",
                    "source_branch": "fix/token-expiry",
                    "target_branch": "develop",
                    "web_url": "https://gitlab.com/group/api-gateway/-/merge_requests/25",
                    "merge_commit_sha": "d4e5f6a1b2c3",
                },
            )
        elif request.method == "GET" and not url_str.endswith("/merge_requests/25"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 801,
                        "iid": 25,
                        "title": "Resolve OAuth2 bug",
                        "description": "Closes #10",
                        "state": "opened",
                        "source_branch": "fix/token-expiry",
                        "target_branch": "develop",
                        "author": {"name": "Security Specialist"},
                        "web_url": "https://gitlab.com/group/api-gateway/-/merge_requests/25",
                        "work_in_progress": False,
                    }
                ],
            )
        elif request.method == "POST":
            data = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 802,
                    "iid": 26,
                    "title": data.get("title"),
                    "description": data.get("description"),
                    "state": "opened",
                    "source_branch": data.get("source_branch"),
                    "target_branch": data.get("target_branch"),
                    "author": {"name": "Agent Builder"},
                    "web_url": "https://gitlab.com/group/api-gateway/-/merge_requests/26",
                },
            )
        elif request.method == "GET" and url_str.endswith("/merge_requests/25"):
            return httpx.Response(
                200,
                json={
                    "id": 801,
                    "iid": 25,
                    "title": "Resolve OAuth2 bug",
                    "description": "Closes #10",
                    "state": "opened",
                    "source_branch": "fix/token-expiry",
                    "target_branch": "develop",
                    "author": {"name": "Security Specialist"},
                    "web_url": "https://gitlab.com/group/api-gateway/-/merge_requests/25",
                },
            )

    # Pipelines GET & POST
    if "/pipeline" in url_str:
        if request.method == "POST":
            data = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 7711,
                    "status": "pending",
                    "ref": data.get("ref"),
                    "sha": "a1b2c3d4e5",
                    "web_url": "https://gitlab.com/group/api-gateway/-/pipelines/7711",
                    "created_at": "2026-11-15T13:00:00Z",
                },
            )
        elif url_str.endswith("/pipelines/7711"):
            return httpx.Response(
                200,
                json={
                    "id": 7711,
                    "status": "success",
                    "ref": "develop",
                    "sha": "a1b2c3d4e5",
                    "web_url": "https://gitlab.com/group/api-gateway/-/pipelines/7711",
                    "created_at": "2026-11-15T13:00:00Z",
                },
            )
        elif "/pipelines" in url_str:
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 7711,
                        "status": "success",
                        "ref": "develop",
                        "sha": "a1b2c3d4e5",
                        "web_url": "https://gitlab.com/group/api-gateway/-/pipelines/7711",
                    }
                ],
            )

    return httpx.Response(404, json={"message": f"Route not found: {url_str}"})


@pytest.fixture
def gitlab_provider():
    transport = httpx.MockTransport(mock_gitlab_handler)
    client = httpx.Client(transport=transport)
    return GitLabProvider(
        project_id=999,
        token="mock-gl-token-123",
        client=client,
    )


def test_gitlab_repositories(gitlab_provider):
    repos = gitlab_provider.list_repositories()
    assert len(repos) == 1
    assert repos[0].name == "api-gateway"
    assert repos[0].default_branch == "develop"

    single = gitlab_provider.get_repository("999")
    assert single.name == "api-gateway"

    created = gitlab_provider.create_repository(name="new-service", description="New Microservice")
    assert created.id == "1001"
    assert created.name == "new-service"


def test_gitlab_issues(gitlab_provider):
    issues = gitlab_provider.list_issues()
    assert len(issues) == 1
    assert issues[0].number == 10
    assert "security" in issues[0].labels

    single = gitlab_provider.get_issue("10")
    assert single.number == 10

    created = gitlab_provider.create_issue(
        title="Add rate limiting",
        body="Throttle requests",
        labels=["security", "p1"],
    )
    assert created.number == 11
    assert "security" in created.labels

    updated = gitlab_provider.update_issue("10", state="closed")
    assert updated.state == "closed"


def test_gitlab_merge_requests(gitlab_provider):
    mrs = gitlab_provider.list_pull_requests()
    assert len(mrs) == 1
    assert mrs[0].source_branch == "fix/token-expiry"

    single = gitlab_provider.get_pull_request("25")
    assert single.number == 25

    created = gitlab_provider.create_pull_request(
        title="feat: throttle middleware",
        body="Closes #11",
        source_branch="feat/throttle",
        target_branch="develop",
    )
    assert created.number == 26

    merged = gitlab_provider.merge_pull_request("25", commit_message="Merge MR 25")
    assert merged.state == "merged"
    assert merged.merge_commit_sha == "d4e5f6a1b2c3"


def test_gitlab_pipelines(gitlab_provider):
    pipelines = gitlab_provider.list_pipelines()
    assert len(pipelines) == 1

    triggered = gitlab_provider.trigger_pipeline(ref="develop", variables={"ENV": "staging"})
    assert triggered.id == "7711"
    assert triggered.status == "pending"

    status = gitlab_provider.get_pipeline_run("7711")
    assert status.status == "success"
