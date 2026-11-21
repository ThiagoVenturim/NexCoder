"""Tests for Control Plane FastAPI router and Web Panel with RBAC authentication."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nexcoder_control.approval.machines import MachineApprovalManager
from nexcoder_control.approval.tokens import ApprovalTokenManager
from nexcoder_control.auth.local import LocalAuthProvider
from nexcoder_control.keys.models import APIKeyCreate
from nexcoder_control.keys.store import APIKeyService
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_control.metering.budgets import BudgetManager
from nexcoder_control.metering.cost_tracker import CostTracker
from nexcoder_control.metering.mcp_middleware import MCPToolMeter
from nexcoder_control.web.api import create_control_router
from nexcoder_control.web.panel import build_overview, render_html_panel


@pytest.fixture
def auth_setup(local_auth: LocalAuthProvider, key_service: APIKeyService) -> dict[str, str]:
    """Register test accounts and API keys returning header fixtures."""
    # 1. Admin Human User
    local_auth.register_user(
        username="admin_user",
        password="AdminPassword123!",
        full_name="Admin Director",
        roles=["admin"],
        scopes=["admin", "control:admin", "approval:issue"],
    )
    admin_token = local_auth.issue_bearer_token("admin_user", roles=["admin"], scopes=["admin"])

    # 2. Developer Human User (non-admin, approver)
    local_auth.register_user(
        username="lead_dev",
        password="DevPassword123!",
        full_name="Lead Developer",
        roles=["developer", "approver"],
        scopes=["tools:execute", "approval:issue"],
    )
    approver_token = local_auth.issue_bearer_token(
        "lead_dev", roles=["developer", "approver"], scopes=["approval:issue"]
    )

    # 3. Regular Human User (no approver role)
    local_auth.register_user(
        username="junior_dev",
        password="JuniorPassword123!",
        full_name="Junior Developer",
        roles=["developer"],
        scopes=["tools:execute"],
    )
    regular_token = local_auth.issue_bearer_token("junior_dev", roles=["developer"], scopes=["tools:execute"])

    # 4. Service Machine API Key (non-human, tools:execute)
    svc_key = key_service.create_key(
        APIKeyCreate(
            name="CI Pipeline Key",
            owner="ci_pipeline",
            scopes=["tools:execute", "metrics:read"],
        )
    )

    # 5. Admin API Key (machine admin)
    admin_key = key_service.create_key(
        APIKeyCreate(
            name="Admin Bot Key",
            owner="admin_bot",
            scopes=["admin"],
        )
    )

    return {
        "admin_auth": f"Bearer {admin_token}",
        "approver_auth": f"Bearer {approver_token}",
        "regular_auth": f"Bearer {regular_token}",
        "service_key": svc_key.raw_key,
        "admin_key": admin_key.raw_key,
    }


@pytest.fixture
def client(
    key_service: APIKeyService,
    cost_tracker: CostTracker,
    tool_meter: MCPToolMeter,
    budget_manager: BudgetManager,
    machine_manager: MachineApprovalManager,
    audit_log: AppendOnlyAuditLog,
    approval_manager: ApprovalTokenManager,
    local_auth: LocalAuthProvider,
) -> TestClient:
    app = FastAPI()
    router = create_control_router(
        key_service=key_service,
        cost_tracker=cost_tracker,
        tool_meter=tool_meter,
        budget_mgr=budget_manager,
        machine_mgr=machine_manager,
        audit_log=audit_log,
        token_mgr=approval_manager,
        auth_provider=local_auth,
    )
    app.include_router(router)
    return TestClient(app)


class TestControlAuthAndSecurity:
    """Validate 401 unauthenticated and 403 authorization guardrails."""

    def test_unauthenticated_requests_return_401(self, client: TestClient) -> None:
        endpoints = [
            ("GET", "/control/status"),
            ("GET", "/control/panel"),
            ("GET", "/control/metrics/tools"),
            ("GET", "/control/metrics/spend"),
            ("GET", "/control/keys"),
            ("POST", "/control/keys"),
            ("GET", "/control/budgets"),
            ("GET", "/control/audit"),
            ("POST", "/control/approval/tokens"),
            ("GET", "/control/machines"),
        ]
        for method, url in endpoints:
            if method == "GET":
                resp = client.get(url)
            else:
                resp = client.post(url, json={})
            assert resp.status_code == 401, f"Expected 401 for {method} {url}, got {resp.status_code}"

    def test_invalid_bearer_token_returns_401(self, client: TestClient) -> None:
        resp = client.get("/control/status", headers={"Authorization": "Bearer invalid"})
        assert resp.status_code == 401

    def test_invalid_api_key_returns_401(self, client: TestClient) -> None:
        resp = client.get("/control/status", headers={"X-API-Key": "invalid"})
        assert resp.status_code == 401

    def test_admin_route_forbidden_for_regular_user_403(self, client: TestClient, auth_setup: dict[str, str]) -> None:
        # Regular user cannot create keys
        resp = client.post(
            "/control/keys",
            headers={"Authorization": auth_setup["regular_auth"]},
            json={"name": "test", "owner": "me", "scopes": ["tools:execute"]},
        )
        assert resp.status_code == 403
        assert "administrator" in resp.json()["detail"].lower()

    def test_machine_api_key_cannot_issue_approval_token_403(
        self, client: TestClient, auth_setup: dict[str, str]
    ) -> None:
        """Machine credentials (even with execute scopes) must be blocked from human approval token issuance."""
        resp = client.post(
            "/control/approval/tokens",
            headers={"X-API-Key": auth_setup["service_key"]},
            json={"action_name": "db_drop", "target_resource": "db:prod"},
        )
        assert resp.status_code == 403
        assert "authenticated human principals" in resp.json()["detail"]

    def test_non_approver_human_cannot_issue_approval_token_403(
        self, client: TestClient, auth_setup: dict[str, str]
    ) -> None:
        """A human user without approver/admin role cannot issue approval tokens."""
        resp = client.post(
            "/control/approval/tokens",
            headers={"Authorization": auth_setup["regular_auth"]},
            json={"action_name": "db_drop", "target_resource": "db:prod"},
        )
        assert resp.status_code == 403

    def test_approver_derived_strictly_from_authenticated_principal(
        self, client: TestClient, auth_setup: dict[str, str]
    ) -> None:
        """The approver field is bound to the authenticated principal, preventing identity spoofing."""
        resp = client.post(
            "/control/approval/tokens",
            headers={"Authorization": auth_setup["approver_auth"]},
            json={
                "action_name": "db_drop_table",
                "target_resource": "db:users",
                "ttl_minutes": 10,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["approver"] == "Lead Developer"
        raw_token = data["raw_token"]

        # Verify token and inspect stored approver
        verify_resp = client.post(
            "/control/approval/tokens/verify",
            headers={"X-API-Key": auth_setup["service_key"]},
            json={
                "raw_token": raw_token,
                "action_name": "db_drop_table",
                "target_resource": "db:users",
                "dry_run": True,
            },
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()["approver"] == "Lead Developer"


class TestControlWebAPI:
    """Validate functional behaviors of all control plane routes under proper authorization."""

    def test_status_endpoint(self, client: TestClient, auth_setup: dict[str, str]) -> None:
        response = client.get("/control/status", headers={"Authorization": auth_setup["admin_auth"]})
        assert response.status_code == 200
        data = response.json()
        assert "active_keys_count" in data
        assert "total_spend_usd" in data

    def test_keys_lifecycle_as_admin(self, client: TestClient, auth_setup: dict[str, str]) -> None:
        # Create key
        create_resp = client.post(
            "/control/keys",
            headers={"Authorization": auth_setup["admin_auth"]},
            json={
                "name": "API Test Key",
                "owner": "test_owner",
                "usd_cap": 25.0,
                "rate_limit_rpm": 60,
                "scopes": ["tools:execute"],
            },
        )
        assert create_resp.status_code == 200
        key_data = create_resp.json()
        assert "raw_key" in key_data
        key_id = key_data["key_id"]

        # List keys
        list_resp = client.get("/control/keys", headers={"Authorization": auth_setup["admin_auth"]})
        assert list_resp.status_code == 200
        assert any(k["key_id"] == key_id for k in list_resp.json())

        # Revoke key
        del_resp = client.delete(f"/control/keys/{key_id}", headers={"Authorization": auth_setup["admin_auth"]})
        assert del_resp.status_code == 200
        assert del_resp.json()["revoked"] is True

    def test_budgets_api_as_admin(self, client: TestClient, auth_setup: dict[str, str]) -> None:
        set_resp = client.post(
            "/control/budgets",
            headers={"Authorization": auth_setup["admin_auth"]},
            json={"dimension": "app", "entity_id": "portal", "limit_usd": 100.0},
        )
        assert set_resp.status_code == 200

        list_resp = client.get("/control/budgets", headers={"Authorization": auth_setup["admin_auth"]})
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1

    def test_audit_log_api(self, client: TestClient, auth_setup: dict[str, str]) -> None:
        audit_resp = client.get("/control/audit", headers={"Authorization": auth_setup["admin_auth"]})
        assert audit_resp.status_code == 200
        assert isinstance(audit_resp.json(), list)

        verify_resp = client.get("/control/audit/verify", headers={"Authorization": auth_setup["admin_auth"]})
        assert verify_resp.status_code == 200
        assert verify_resp.json()["valid"] is True

    def test_machines_api(self, client: TestClient, auth_setup: dict[str, str]) -> None:
        # Register machine as authenticated client
        reg_resp = client.post(
            "/control/machines/register",
            headers={"X-API-Key": auth_setup["service_key"]},
            json={"machine_id": "box_alpha", "hostname": "host-1"},
        )
        assert reg_resp.status_code == 200
        assert reg_resp.json()["status"] == "pending"

        # Approve machine as admin
        app_resp = client.post(
            "/control/machines/box_alpha/approve",
            headers={"Authorization": auth_setup["admin_auth"]},
        )
        assert app_resp.status_code == 200
        assert app_resp.json()["status"] == "approved"

    def test_html_panel_rendering(
        self,
        client: TestClient,
        auth_setup: dict[str, str],
        key_service: APIKeyService,
        cost_tracker: CostTracker,
        tool_meter: MCPToolMeter,
        budget_manager: BudgetManager,
        machine_manager: MachineApprovalManager,
        audit_log: AppendOnlyAuditLog,
    ) -> None:
        overview = build_overview(key_service, cost_tracker, tool_meter, budget_manager, machine_manager, audit_log)
        html = render_html_panel(overview)
        assert "<title>nexcoder Control Plane</title>" in html
        assert "Active API Keys" in html

        resp = client.get("/control/panel", headers={"Authorization": auth_setup["admin_auth"]})
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "nexcoder Control Plane" in resp.text
