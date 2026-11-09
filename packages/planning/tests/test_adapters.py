import httpx
from nexcoder_planning.adapters.azure_devops import AzureDevOpsAdapter
from nexcoder_planning.adapters.base import (
    embed_nexcoder_id,
    extract_nexcoder_id,
)
from nexcoder_planning.adapters.github import GitHubAdapter
from nexcoder_planning.adapters.gitlab import GitLabAdapter
from nexcoder_planning.models import Epic, Plan, Story, Task


def test_marker_embedding_and_extraction():
    uuid_str = "12345678-1234-5678-1234-567812345678"
    body = "This is a feature task description."

    embedded = embed_nexcoder_id(body, uuid_str)
    assert f"<!-- nexcoder-id: {uuid_str} -->" in embedded

    extracted = extract_nexcoder_id(embedded)
    assert extracted == uuid_str

    # Calling embed again should be idempotent
    re_embedded = embed_nexcoder_id(embedded, uuid_str)
    assert re_embedded == embedded


def test_github_adapter_dry_run_by_default():
    adapter = GitHubAdapter(repo="org/repo")
    assert adapter.dry_run is True

    task = Task(id="TSK-01", title="Setup Database", estimate_hours=4.0)
    result = adapter.create_issue(task)

    assert result.action == "dry_run_create"
    assert result.dry_run is True
    assert "Would create GitHub issue" in result.message
    assert task.nexcoder_id in result.message


def test_github_adapter_pagination_and_idempotence():
    # Setup mock transport for pagination and issues
    task = Task(
        id="TSK-10",
        nexcoder_id="test-uuid-42",
        title="Existing Task Title",
        description="Task description",
        estimate_hours=5.0,
    )
    existing_issue_body = task.format_markdown_body()

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "issues" in url_str and request.method == "GET":
            params = request.url.params
            page = int(params.get("page", 1))
            if page == 1:
                # Return 100 dummy issues
                items = [
                    {
                        "id": i,
                        "number": i,
                        "title": f"Issue {i}",
                        "body": f"Description {i}",
                        "state": "open",
                        "labels": [],
                        "html_url": f"https://github.com/org/repo/issues/{i}",
                    }
                    for i in range(1, 101)
                ]
                return httpx.Response(200, json=items)
            elif page == 2:
                # Return 1 issue which matches our task tracking marker
                items = [
                    {
                        "id": 101,
                        "number": 101,
                        "title": "Existing Task Title",
                        "body": existing_issue_body,
                        "state": "open",
                        "labels": [{"name": "layer:general"}],
                        "html_url": "https://github.com/org/repo/issues/101",
                    }
                ]
                return httpx.Response(200, json=items)
            else:
                return httpx.Response(200, json=[])

        return httpx.Response(404)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GitHubAdapter(repo="org/repo", token="dummy-token", client=mock_client, dry_run=False)

    # 1. Test pagination: should collect 101 issues across pages
    issues = adapter.list_issues()
    assert len(issues) == 101

    # 2. Test idempotence: sync_task should detect the existing issue and skip
    sync_res = adapter.sync_task(task)
    assert sync_res.action == "skipped"
    assert sync_res.remote_number == 101


def test_github_adapter_sync_plan_with_updates():
    task1 = Task(id="T1", nexcoder_id="id-1", title="Title 1", description="Body 1")
    task2 = Task(id="T2", nexcoder_id="id-2", title="New Task", description="Body 2")

    existing_task1_body = "Old Body\n\n<!-- nexcoder-id: id-1 -->"

    created_calls = []
    updated_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "issues" in url_str and request.method == "GET":
            # Remote has issue 1 with old body
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 10,
                        "number": 10,
                        "title": "Title 1",
                        "body": existing_task1_body,
                        "state": "open",
                        "labels": [],
                        "html_url": "https://github.com/org/repo/issues/10",
                    }
                ],
            )
        elif request.method == "POST":
            import json

            data = json.loads(request.content.decode())
            created_calls.append(data)
            return httpx.Response(
                201,
                json={
                    "id": 11,
                    "number": 11,
                    "title": data["title"],
                    "body": data["body"],
                    "state": "open",
                    "html_url": "https://github.com/org/repo/issues/11",
                },
            )
        elif request.method == "PATCH":
            import json

            data = json.loads(request.content.decode())
            updated_calls.append(data)
            return httpx.Response(
                200,
                json={
                    "id": 10,
                    "number": 10,
                    "title": data["title"],
                    "body": data["body"],
                    "state": "open",
                    "html_url": "https://github.com/org/repo/issues/10",
                },
            )
        return httpx.Response(404)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GitHubAdapter(repo="org/repo", token="dummy-token", client=mock_client, dry_run=False)

    plan = Plan(
        title="Sync Plan",
        epics=[
            Epic(
                id="EP-1",
                title="Epic 1",
                stories=[Story(id="US-1", title="Story 1", tasks=[task1, task2])],
            )
        ],
    )

    summary = adapter.sync_plan(plan)

    assert summary.total == 2
    assert summary.updated == 1  # task1 was updated
    assert summary.created == 1  # task2 was created
    assert len(updated_calls) == 1
    assert len(created_calls) == 1


def test_gitlab_and_azure_adapters_dry_run():
    task = Task(id="TSK-01", title="Setup Infrastructure", estimate_hours=8.0)

    gitlab = GitLabAdapter(project_id="12345")
    assert gitlab.dry_run is True
    res_gl = gitlab.sync_task(task)
    assert res_gl.action == "dry_run_create"
    assert res_gl.dry_run is True

    azure = AzureDevOpsAdapter(organization="myorg", project="myproject")
    assert azure.dry_run is True
    res_az = azure.sync_task(task)
    assert res_az.action == "dry_run_create"
    assert res_az.dry_run is True


def test_azure_devops_tag_persistence_and_lifecycle():
    task = Task(
        id="TSK-02",
        nexcoder_id="azure-tag-uuid-99",
        title="Deploy Pipeline",
        description="Task for CI/CD",
        estimate_hours=3.0,
    )

    created_patch_ops = []

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "_apis/wit/workitems/$Task" in url_str and request.method == "POST":
            import json

            patch_ops = json.loads(request.content.decode())
            created_patch_ops.extend(patch_ops)
            return httpx.Response(
                200,
                json={
                    "id": 501,
                    "fields": {
                        "System.Title": "Deploy Pipeline",
                        "System.Description": "HTML desc without comment",  # simulation of HTML normalization
                        "System.Tags": "nexcoder-id:azure-tag-uuid-99; backend",
                    },
                    "_links": {"html": {"href": "https://dev.azure.com/org/proj/_workitems/edit/501"}},
                },
            )
        return httpx.Response(404)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    with AzureDevOpsAdapter(
        organization="org", project="proj", pat="pat-token", client=mock_client, dry_run=False
    ) as adapter:
        res = adapter.create_issue(task)
        assert res.action == "created"
        assert res.remote_id == "501"

    # Verify that tags patch op included the tag nexcoder-id:azure-tag-uuid-99
    tag_op = next((op for op in created_patch_ops if op.get("path") == "/fields/System.Tags"), None)
    assert tag_op is not None
    assert "nexcoder-id:azure-tag-uuid-99" in tag_op["value"]


def test_client_context_manager_lifecycle():
    adapter_gh = GitHubAdapter(repo="org/repo", token="dummy")
    with adapter_gh as a:
        client_gh = a._client
        assert client_gh is not None
        assert not client_gh.is_closed
    assert client_gh.is_closed
    assert adapter_gh._client is None

    adapter_az = AzureDevOpsAdapter(organization="org", project="proj", pat="dummy")
    with adapter_az as a:
        client_az = a._client
        assert client_az is not None
        assert not client_az.is_closed
    assert client_az.is_closed
    assert adapter_az._client is None
