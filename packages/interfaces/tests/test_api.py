from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from faccoder_control.approval import ApprovalTokenManager
from faccoder_control.auth.local import LocalAuthProvider
from faccoder_control.keys import APIKeyCreate, APIKeyService
from faccoder_interfaces.api.app import create_app
from starlette.testclient import TestClient


def test_api_health_endpoint() -> None:
    app = create_app(insecure_local=True)
    client = TestClient(app)

    response = client.get("/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert "modules" in data


def test_api_capabilities_endpoint() -> None:
    app = create_app(insecure_local=True)
    client = TestClient(app)

    response = client.get("/v1/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "modules" in data
    assert "tools" in data
    assert len(data["tools"]) >= 10


def test_api_invoke_tool_success() -> None:
    app = create_app(insecure_local=True)
    client = TestClient(app)

    response = client.post(
        "/v1/tools/research_idea",
        json={"arguments": {"idea": "Cloud-native IDE", "dry_run": True}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


def test_api_invoke_tool_not_found() -> None:
    app = create_app(insecure_local=True)
    client = TestClient(app)

    response = client.post(
        "/v1/tools/nonexistent_tool_xyz",
        json={"arguments": {}},
    )
    assert response.status_code == 404


def test_api_specialized_endpoints(tmp_path: Path) -> None:
    app = create_app(insecure_local=True)
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

    # Pipeline approve with human approval token from control plane
    atm: ApprovalTokenManager = app.state.approval_token_manager
    _rec, raw_tok = atm.issue_token(action_name="release", target_resource="pipeline", approver="human-tester")
    resp_appr = client.post(
        "/v1/pipelines/approve",
        json={"action_name": "release", "token": raw_tok, "target_resource": "pipeline"},
    )
    assert resp_appr.status_code == 200
    assert resp_appr.json()["approved"] is True


def test_api_sse_pipeline_stream() -> None:
    app = create_app(insecure_local=True)
    client = TestClient(app)

    response = client.get("/v1/pipelines/stream?pipeline_name=test_pipeline")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    content = response.text
    assert "event: pipeline_started" in content
    assert "data: " in content


# =====================================================================
# Security & Auth Requirements Tests (Refs #10, Review Requirements)
# =====================================================================


def test_sem_credencial_retorna_401_todas_as_rotas_exceto_health() -> None:
    """Requirement: sem credencial -> 401 em todas as rotas exceto health."""
    app = create_app()  # Default HTTP server requires auth
    client = TestClient(app)

    # Health endpoints are open
    assert client.get("/health").status_code == 200
    assert client.get("/v1/health").status_code == 200

    # Protected routes must return 401 when no credentials are provided
    endpoints = [
        ("GET", "/v1/capabilities"),
        ("POST", "/v1/tools/research_idea"),
        ("POST", "/v1/ideation/research"),
        ("POST", "/v1/ideation/judge"),
        ("POST", "/v1/planning/sprints"),
        ("POST", "/v1/security/scan"),
        ("POST", "/v1/agents/run"),
        ("POST", "/v1/pipelines/run"),
        ("POST", "/v1/pipelines/approve"),
        ("GET", "/v1/pipelines/stream"),
        ("GET", "/sse"),
        ("POST", "/messages"),
    ]

    for method, url in endpoints:
        if method == "GET":
            resp = client.get(url)
        else:
            resp = client.post(url, json={})
        assert resp.status_code == 401, f"Expected 401 for {method} {url}, got {resp.status_code}"


def test_erro_no_verificador_nao_libera() -> None:
    """Requirement: erro no verificador -> nao libera (retorna 503/401, nunca 200)."""

    class BrokenKeyService:
        def verify_key(self, raw_key: str) -> Any:
            raise RuntimeError("Database connection or cryptographic subsystem failure")

    app = create_app(api_key_service=BrokenKeyService())
    client = TestClient(app)

    resp = client.get("/v1/capabilities", headers={"X-API-Key": "some-key"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Service unavailable: Authentication system error."


def test_origem_externa_sem_cors_configurado_nao_recebe_allow_origin() -> None:
    """Requirement: origem externa sem CORS configurado nao recebe Access-Control-Allow-Origin."""
    app = create_app(insecure_local=True)  # No cors_origins provided
    client = TestClient(app)

    resp = client.get("/health", headers={"Origin": "https://malicious-attacker.example.com"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


def test_cors_configurado_com_wildcard_nao_permite_credentials() -> None:
    """Requirement: nunca '*' junto com credenciais."""
    app = create_app(insecure_local=True, cors_origins=["*"])
    client = TestClient(app)

    resp = client.get("/health", headers={"Origin": "https://example.com"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"
    assert resp.headers.get("access-control-allow-credentials") != "true"


def test_approve_com_chave_de_agente_retorna_403() -> None:
    """Requirement: approve com chave de agente -> 403."""
    key_service = APIKeyService()
    created = key_service.create_key(APIKeyCreate(name="agent-worker", owner="worker-agent-1"))

    app = create_app(api_key_service=key_service)
    client = TestClient(app)

    # Agent calls /v1/pipelines/approve with its machine API key
    resp = client.post(
        "/v1/pipelines/approve",
        headers={"X-API-Key": created.raw_key},
        json={"action_name": "deploy", "token": "any-token", "target_resource": "pipeline"},
    )
    assert resp.status_code == 403
    assert "human approver" in resp.json()["detail"].lower()


def test_approve_com_principal_humano_e_token_valido_retorna_200() -> None:
    """Requirement: human approver with valid control token can approve pipeline step."""
    auth_provider = LocalAuthProvider()
    auth_provider.register_user(
        username="carol",
        password="HumanPassword123!",
        roles=["approver", "admin"],
    )
    human_bearer_token = auth_provider.issue_bearer_token("carol")

    atm = ApprovalTokenManager()
    _rec, valid_approval_token = atm.issue_token(
        action_name="release_gate",
        target_resource="pipeline",
        approver="carol",
    )

    app = create_app(auth_provider=auth_provider, approval_token_manager=atm)
    client = TestClient(app)

    # Human user calls with Bearer token in header and human approval token in body
    resp = client.post(
        "/v1/pipelines/approve",
        headers={"Authorization": f"Bearer {human_bearer_token}"},
        json={
            "action_name": "release_gate",
            "token": valid_approval_token,
            "target_resource": "pipeline",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["approved"] is True
    assert data["approver"] == "carol"


def test_approve_com_token_invalido_retorna_403() -> None:
    """Requirement: human approver with invalid or expired approval token gets 403."""
    auth_provider = LocalAuthProvider()
    auth_provider.register_user(
        username="dave",
        password="HumanPassword123!",
        roles=["approver"],
    )
    human_bearer_token = auth_provider.issue_bearer_token("dave")

    atm = ApprovalTokenManager()

    app = create_app(auth_provider=auth_provider, approval_token_manager=atm)
    client = TestClient(app)

    resp = client.post(
        "/v1/pipelines/approve",
        headers={"Authorization": f"Bearer {human_bearer_token}"},
        json={
            "action_name": "release_gate",
            "token": "invalid_or_fake_token",
            "target_resource": "pipeline",
        },
    )
    assert resp.status_code == 403


def test_approve_pipeline_execucao_pausada_fluxo_completo_e_reuso_rejeita() -> None:
    """Requirement: sem control instalado, approve busca execucao pausada, valida token, e rejeita reuso."""
    # App running without control approval manager (simulating no-control environment)
    app = create_app(insecure_local=True, approval_token_manager=None)
    client = TestClient(app)

    # 1. Run pipeline that halts waiting for approval
    pipe_resp = client.post(
        "/v1/pipelines/run",
        json={"pipeline_name": "release_gate_test", "inputs": {"task": "deploy prod"}, "dry_run": False},
    )
    assert pipe_resp.status_code == 200
    pipe_data = pipe_resp.json()
    assert pipe_data["run_status"] == "waiting_approval"
    action_name = pipe_data["approval"]["action_name"]
    exec_id = pipe_data["execution_id"]
    valid_token = pipe_data["approval"]["token"]

    # 2. Random 8+ char token is rejected with 403
    bad_resp = client.post(
        "/v1/pipelines/approve",
        json={"action_name": action_name, "token": "random_fake_token_123", "execution_id": exec_id},
    )
    assert bad_resp.status_code == 403

    # 3. Valid token approves and completes execution
    good_resp = client.post(
        "/v1/pipelines/approve",
        json={"action_name": action_name, "token": valid_token, "execution_id": exec_id},
    )
    assert good_resp.status_code == 200
    assert good_resp.json()["approved"] is True

    # 4. Reusing the same token fails with 403 (single use / execution already finished)
    reuse_resp = client.post(
        "/v1/pipelines/approve",
        json={"action_name": action_name, "token": valid_token, "execution_id": exec_id},
    )
    assert reuse_resp.status_code == 403


def test_insecure_local_recusa_host_externo() -> None:
    """Requirement: --insecure-local recusa host diferente de 127.0.0.1 / localhost."""
    with pytest.raises(ValueError, match="--insecure-local mode is only permitted"):
        create_app(insecure_local=True, host="0.0.0.0")

    with pytest.raises(ValueError, match="--insecure-local mode is only permitted"):
        create_app(insecure_local=True, host="192.168.1.100")
