from __future__ import annotations

from pathlib import Path

from faccoder_interfaces.api.app import create_app
from starlette.testclient import TestClient


def test_api_health_endpoint() -> None:
    app = create_app(enforce_auth=False)
    client = TestClient(app)

    response = client.get("/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert "modules" in data


def test_api_capabilities_endpoint() -> None:
    app = create_app(enforce_auth=False)
    client = TestClient(app)

    response = client.get("/v1/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "modules" in data
    assert "tools" in data
    assert len(data["tools"]) >= 10


def test_api_invoke_tool_success() -> None:
    app = create_app(enforce_auth=False)
    client = TestClient(app)

    response = client.post(
        "/v1/tools/research_idea",
        json={"arguments": {"idea": "Cloud-native IDE", "dry_run": True}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


def test_api_invoke_tool_not_found() -> None:
    app = create_app(enforce_auth=False)
    client = TestClient(app)

    response = client.post(
        "/v1/tools/nonexistent_tool_xyz",
        json={"arguments": {}},
    )
    assert response.status_code == 404


def test_api_specialized_endpoints(tmp_path: Path) -> None:
    app = create_app(enforce_auth=False)
    client = TestClient(app)

    # Ideation judge
    resp_judge = client.post("/v1/ideation/judge", json={"idea": "Smart log analyzer", "dry_run": True})
    assert resp_judge.status_code == 200
    assert resp_judge.json()["status"] == "success"

    # Planning sprints
    sample_prd = "# PRD: Log Pipeline\n# Epic: E1\n## Story: S1\n### Task: T1\n- Layer: backend\n- Estimate: 2h\n"
    resp_plan = client.post("/v1/planning/sprints", json={"prd_text": sample_prd})
    assert resp_plan.status_code == 200
    assert resp_plan.json()["status"] == "success"

    # Security scan
    sample_code = tmp_path / "main.py"
    sample_code.write_text("print('hello')\n", encoding="utf-8")
    resp_sec = client.post("/v1/security/scan", json={"path": str(tmp_path), "force_offline": True})
    assert resp_sec.status_code == 200
    assert resp_sec.json()["status"] == "success"

    # Agents run
    resp_agent = client.post("/v1/agents/run", json={"agent_name": "lead-architect", "task": "Design API"})
    assert resp_agent.status_code == 200
    assert resp_agent.json()["status"] == "success"

    # Pipeline approve
    resp_appr = client.post("/v1/pipelines/approve", json={"action_name": "release", "token": "test-token-xyz"})
    assert resp_appr.status_code == 200
    assert resp_appr.json()["approved"] is True


def test_api_sse_pipeline_stream() -> None:
    app = create_app(enforce_auth=False)
    client = TestClient(app)

    response = client.get("/v1/pipelines/stream?pipeline_name=test_pipeline")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    content = response.text
    assert "event: pipeline_started" in content
    assert "data: " in content


def test_api_authentication_middleware() -> None:
    valid_key = "secret-test-key-12345"
    app = create_app(api_key=valid_key, enforce_auth=True)
    client = TestClient(app)

    # Public endpoint (/health) should not require key
    resp_health = client.get("/health")
    assert resp_health.status_code == 200

    # Protected endpoint without key -> 401
    resp_unauth = client.get("/v1/capabilities")
    assert resp_unauth.status_code == 401

    # Protected endpoint with wrong key -> 401
    resp_wrong = client.get("/v1/capabilities", headers={"X-API-Key": "wrong-key"})
    assert resp_wrong.status_code == 401

    # Protected endpoint with valid X-API-Key -> 200
    resp_valid = client.get("/v1/capabilities", headers={"X-API-Key": valid_key})
    assert resp_valid.status_code == 200

    # Protected endpoint with Bearer token -> 200
    resp_bearer = client.get("/v1/capabilities", headers={"Authorization": f"Bearer {valid_key}"})
    assert resp_bearer.status_code == 200
