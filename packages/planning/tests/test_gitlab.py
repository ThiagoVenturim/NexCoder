import json

import httpx
from faccoder_planning.adapters.base import RemoteIssue
from faccoder_planning.adapters.gitlab import GitLabAdapter
from faccoder_planning.models import Task


def test_gitlab_client_lifecycle():
    adapter = GitLabAdapter(project_id="my-group/my-project", token="glpat-dummy")
    with adapter as a:
        client = a._get_client()
        assert client is not None
        assert not client.is_closed
    assert a._client is None


def test_gitlab_list_issues_pagination_and_marker():
    task = Task(
        id="TSK-GL-1",
        faccoder_id="gitlab-uuid-1234",
        title="GitLab Task Title",
        description="GitLab Task Body",
        estimate_hours=4.0,
    )
    body_with_marker = task.format_markdown_body()

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "issues" in url_str and request.method == "GET":
            page = int(request.url.params.get("page", 1))
            if page == 1:
                # 100 dummy issues
                items = [
                    {
                        "id": i,
                        "iid": i,
                        "title": f"Issue {i}",
                        "description": f"Desc {i}",
                        "state": "opened",
                        "labels": ["backend"],
                        "web_url": f"https://gitlab.com/group/proj/-/issues/{i}",
                    }
                    for i in range(1, 101)
                ]
                return httpx.Response(200, json=items)
            elif page == 2:
                # Issue with tracking marker
                items = [
                    {
                        "id": 101,
                        "iid": 101,
                        "title": "GitLab Task Title",
                        "description": body_with_marker,
                        "state": "opened",
                        "labels": ["layer:planning"],
                        "web_url": "https://gitlab.com/group/proj/-/issues/101",
                    }
                ]
                return httpx.Response(200, json=items)
            else:
                return httpx.Response(200, json=[])
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GitLabAdapter(project_id="group/proj", token="dummy-token", client=client, dry_run=False)

    issues = adapter.list_issues()
    assert len(issues) == 101
    matched = adapter.find_issue_by_marker("gitlab-uuid-1234")
    assert matched is not None
    assert matched.id == "101"
    assert matched.number == 101


def test_gitlab_create_and_update_issue_live():
    task = Task(
        id="TSK-GL-2",
        faccoder_id="gitlab-uuid-5678",
        title="Implement Pipeline",
        description="Set up CI in GitLab",
        estimate_hours=6.0,
        layer="devops",
        recommended_agent="ci-builder",
    )

    created_payloads = []
    updated_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "issues" in url_str:
            if request.method == "POST":
                data = json.loads(request.content.decode())
                created_payloads.append(data)
                return httpx.Response(
                    201,
                    json={
                        "id": 201,
                        "iid": 42,
                        "title": data["title"],
                        "description": data["description"],
                        "web_url": "https://gitlab.com/group/proj/-/issues/42",
                    },
                )
            elif request.method == "PUT":
                data = json.loads(request.content.decode())
                updated_payloads.append(data)
                return httpx.Response(
                    200,
                    json={
                        "id": 201,
                        "iid": 42,
                        "title": data["title"],
                        "description": data["description"],
                        "web_url": "https://gitlab.com/group/proj/-/issues/42",
                    },
                )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GitLabAdapter(project_id="group/proj", token="token", client=client, dry_run=False)

    # 1. Create issue
    res_create = adapter.create_issue(task)
    assert res_create.action == "created"
    assert res_create.remote_id == "201"
    assert res_create.remote_number == 42
    assert len(created_payloads) == 1
    assert "layer:devops" in created_payloads[0]["labels"]
    assert "agent:ci-builder" in created_payloads[0]["labels"]

    # 2. Update issue
    remote = RemoteIssue(
        id="201",
        number=42,
        title="Old Title",
        body="Old Body",
        faccoder_id=task.faccoder_id,
        url="https://gitlab.com/group/proj/-/issues/42",
    )
    res_update = adapter.update_issue(remote, task)
    assert res_update.action == "updated"
    assert res_update.remote_number == 42
    assert len(updated_payloads) == 1


def test_gitlab_milestones_and_labels():
    milestones_created = []
    labels_created = []

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "milestones" in url_str:
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": 10,
                            "iid": 1,
                            "title": "v1.0.0",
                            "description": "First release",
                            "state": "active",
                            "due_date": "2027-02-12",
                        }
                    ],
                )
            elif request.method == "POST":
                data = json.loads(request.content.decode())
                milestones_created.append(data)
                return httpx.Response(
                    201,
                    json={
                        "id": 11,
                        "iid": 2,
                        "title": data["title"],
                        "description": data["description"],
                        "state": "active",
                        "due_date": data.get("due_date"),
                    },
                )
        elif "labels" in url_str:
            if request.method == "GET":
                return httpx.Response(200, json=[{"name": "backend"}, {"name": "frontend"}])
            elif request.method == "POST":
                data = json.loads(request.content.decode())
                labels_created.append(data)
                return httpx.Response(201, json={"name": data["name"], "color": data["color"]})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GitLabAdapter(project_id="group/proj", token="token", client=client, dry_run=False)

    # 1. Milestones
    existing_ms = adapter.list_milestones()
    assert len(existing_ms) == 1
    assert existing_ms[0].title == "v1.0.0"

    new_ms = adapter.create_milestone("v1.1.0", description="Sprint 2", due_on="2027-03-01")
    assert new_ms.id == "11"
    assert new_ms.title == "v1.1.0"
    assert len(milestones_created) == 1

    # 2. Labels
    existing_labels = adapter.list_labels()
    assert "backend" in existing_labels
    assert "frontend" in existing_labels

    created = adapter.create_label("security", color="#E11D48")
    assert created is True
    assert len(labels_created) == 1
    assert labels_created[0]["name"] == "security"


def test_gitlab_board_items_and_status_update():
    status_updates = []

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "issues" in url_str:
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": 301,
                            "iid": 1,
                            "title": "Task 1",
                            "description": "Desc",
                            "state": "opened",
                            "labels": ["todo"],
                            "web_url": "https://gitlab.com/group/proj/-/issues/1",
                        },
                        {
                            "id": 302,
                            "iid": 2,
                            "title": "Task 2",
                            "description": "Desc",
                            "state": "closed",
                            "labels": [],
                            "web_url": "https://gitlab.com/group/proj/-/issues/2",
                        },
                    ],
                )
            elif request.method == "PUT":
                data = json.loads(request.content.decode())
                status_updates.append(data)
                return httpx.Response(200, json={"id": 301, "iid": 1, "state": "closed"})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GitLabAdapter(project_id="group/proj", token="token", client=client, dry_run=False)

    # 1. list_project_items
    items = adapter.list_project_items()
    assert len(items) == 2
    assert items[0].status == "Todo"
    assert items[1].status == "Done"

    # 2. update_project_item_status (dry run)
    res_dry = adapter.update_project_item_status(project_id="group/proj", item_id="301", field_id="Done", dry_run=True)
    assert res_dry.dry_run is True
    assert res_dry.action == "dry_run_update"
    assert len(status_updates) == 0

    # 3. update_project_item_status (live)
    res_live = adapter.update_project_item_status(
        project_id="group/proj", item_id="301", single_select_option_id="Done", dry_run=False
    )
    assert res_live.dry_run is False
    assert res_live.action == "updated"
    assert len(status_updates) == 1
    assert status_updates[0]["state_event"] == "close"
