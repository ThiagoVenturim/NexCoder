import httpx
from faccoder_planning.adapters.github import GitHubAdapter
from faccoder_planning.models import Task


def test_get_project_v2_graphql():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/graphql" in str(request.url)
        import json

        body = json.loads(request.content.decode())
        variables = body.get("variables", {})

        if variables.get("number") == 9:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "user": {
                            "projectV2": {
                                "id": "PVT_kwDOA123",
                                "number": 9,
                                "title": "Engineering Kanban",
                                "url": "https://github.com/users/alice/projects/9",
                            }
                        }
                    }
                },
            )
        return httpx.Response(200, json={"data": {"user": None}})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GitHubAdapter(repo="alice/repo", token="gh-token", client=mock_client, dry_run=False)

    proj = adapter.get_project_v2("alice", 9)
    assert proj is not None
    assert proj.id == "PVT_kwDOA123"
    assert proj.title == "Engineering Kanban"
    assert proj.number == 9


def test_list_project_items_cursor_pagination():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content.decode())
        cursor = body.get("variables", {}).get("cursor")
        calls.append(cursor)

        if cursor is None:
            # First page: 2 items, hasNextPage = True
            return httpx.Response(
                200,
                json={
                    "data": {
                        "node": {
                            "items": {
                                "pageInfo": {
                                    "hasNextPage": True,
                                    "endCursor": "cursor-page-1",
                                },
                                "nodes": [
                                    {
                                        "id": "ITEM_1",
                                        "content": {
                                            "id": "ISSUE_1",
                                            "number": 1,
                                            "title": "Issue 1",
                                        },
                                        "fieldValueByName": {"name": "Todo"},
                                    },
                                    {
                                        "id": "ITEM_2",
                                        "content": {
                                            "id": "ISSUE_2",
                                            "number": 2,
                                            "title": "Issue 2",
                                        },
                                        "fieldValueByName": {"name": "In Progress"},
                                    },
                                ],
                            }
                        }
                    }
                },
            )
        elif cursor == "cursor-page-1":
            # Second page: 1 item, hasNextPage = False
            return httpx.Response(
                200,
                json={
                    "data": {
                        "node": {
                            "items": {
                                "pageInfo": {
                                    "hasNextPage": False,
                                    "endCursor": None,
                                },
                                "nodes": [
                                    {
                                        "id": "ITEM_3",
                                        "content": {
                                            "id": "ISSUE_3",
                                            "number": 3,
                                            "title": "Issue 3",
                                        },
                                        "fieldValueByName": {"name": "Done"},
                                    }
                                ],
                            }
                        }
                    }
                },
            )

        return httpx.Response(404)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GitHubAdapter(repo="org/repo", token="gh-token", client=mock_client, dry_run=False)

    items = adapter.list_project_items("PVT_kwDOA123")
    assert len(items) == 3
    assert [item.id for item in items] == ["ITEM_1", "ITEM_2", "ITEM_3"]
    assert items[0].status == "Todo"
    assert items[2].status == "Done"
    # Verify pagination queried twice
    assert len(calls) == 2


def test_add_item_to_project_v2_duplicate_prevention():
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content.decode())
        query = body.get("query", "")

        # When list_project_items is called
        if "items(first: 100" in query:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "node": {
                            "items": {
                                "pageInfo": {"hasNextPage": False},
                                "nodes": [
                                    {
                                        "id": "ITEM_1",
                                        "content": {"id": "ALREADY_EXISTS_ID", "number": 1},
                                        "fieldValueByName": None,
                                    }
                                ],
                            }
                        }
                    }
                },
            )
        # When addProjectV2ItemById is called
        if "addProjectV2ItemById" in query:
            return httpx.Response(
                200,
                json={"data": {"addProjectV2ItemById": {"item": {"id": "NEW_ITEM_ID"}}}},
            )
        return httpx.Response(404)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GitHubAdapter(repo="org/repo", token="gh-token", client=mock_client, dry_run=False)

    # 1. Attempt adding existing item -> should be skipped!
    res_skipped = adapter.add_item_to_project_v2("PVT_PROJECT", "ALREADY_EXISTS_ID")
    assert res_skipped.action == "skipped"
    assert "already present" in res_skipped.message

    # 2. Attempt adding new item -> should be added
    res_added = adapter.add_item_to_project_v2("PVT_PROJECT", "BRAND_NEW_ID")
    assert res_added.action == "added"
    assert res_added.item_id == "NEW_ITEM_ID"


def test_milestone_management_and_issue_linking():
    milestones_db = [{"id": 1, "number": 1, "title": "v0.1.0 (layer:planning)", "state": "open"}]
    created_issues = []

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/milestones" in url_str and request.method == "GET":
            return httpx.Response(200, json=milestones_db)
        if "/milestones" in url_str and request.method == "POST":
            import json

            data = json.loads(request.content.decode())
            new_ms = {
                "id": len(milestones_db) + 1,
                "number": len(milestones_db) + 1,
                "title": data["title"],
                "description": data.get("description", ""),
                "state": "open",
            }
            milestones_db.append(new_ms)
            return httpx.Response(201, json=new_ms)
        if "/issues" in url_str and request.method == "POST":
            import json

            data = json.loads(request.content.decode())
            created_issues.append(data)
            return httpx.Response(
                201,
                json={
                    "id": 99,
                    "number": 99,
                    "title": data["title"],
                    "body": data["body"],
                    "state": "open",
                    "html_url": "https://github.com/org/repo/issues/99",
                },
            )
        return httpx.Response(404)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = GitHubAdapter(repo="org/repo", token="gh-token", client=mock_client, dry_run=False)

    # 1. Get or create existing milestone
    ms = adapter.get_or_create_milestone("v0.1.0 (layer:planning)")
    assert ms.number == 1

    # 2. Get or create new milestone
    new_ms = adapter.get_or_create_milestone("v0.2.0")
    assert new_ms.number == 2

    # 3. Create issue linked to milestone
    task = Task(id="TSK-01", title="Task with milestone", estimate_hours=4.0)
    res_issue = adapter.create_issue(task, milestone_number=ms.number)
    assert res_issue.action == "created"
    assert len(created_issues) == 1
    assert created_issues[0]["milestone"] == 1
