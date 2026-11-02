"""Tests for Control Plane FastAPI router and Web Panel."""

from __future__ import annotations

import pytest
from faccoder_control.approval.machines import MachineApprovalManager
from faccoder_control.approval.tokens import ApprovalTokenManager
from faccoder_control.keys.store import APIKeyService
from faccoder_control.metering.audit import AppendOnlyAuditLog
from faccoder_control.metering.budgets import BudgetManager
from faccoder_control.metering.cost_tracker import CostTracker
from faccoder_control.metering.mcp_middleware import MCPToolMeter
from faccoder_control.web.api import create_control_router
from faccoder_control.web.panel import build_overview, render_html_panel
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(
    key_service: APIKeyService,
    cost_tracker: CostTracker,
    tool_meter: MCPToolMeter,
    budget_manager: BudgetManager,
    machine_manager: MachineApprovalManager,
    audit_log: AppendOnlyAuditLog,
    approval_manager: ApprovalTokenManager,
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
    )
    app.include_router(router)
    return TestClient(app)


class TestControlWebAPI:
    def test_status_endpoint(self, client: TestClient) -> None:
        response = client.get("/control/status")
        assert response.status_code == 200
        data = response.json()
        assert "active_keys_count" in data
        assert "total_spend_usd" in data

    def test_keys_lifecycle(self, client: TestClient) -> None:
        # Create key
        create_resp = client.post(
            "/control/keys",
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
        list_resp = client.get("/control/keys")
        assert list_resp.status_code == 200
        assert any(k["key_id"] == key_id for k in list_resp.json())

        # Revoke key
        del_resp = client.delete(f"/control/keys/{key_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["revoked"] is True

    def test_audit_log_api(self, client: TestClient) -> None:
        audit_resp = client.get("/control/audit")
        assert audit_resp.status_code == 200
        assert isinstance(audit_resp.json(), list)

        verify_resp = client.get("/control/audit/verify")
        assert verify_resp.status_code == 200
        assert verify_resp.json()["valid"] is True

    def test_machines_api(self, client: TestClient) -> None:
        reg_resp = client.post(
            "/control/machines/register",
            json={"machine_id": "box_alpha", "hostname": "host-1", "registered_by": "alice"},
        )
        assert reg_resp.status_code == 200
        assert reg_resp.json()["status"] == "pending"

        app_resp = client.post("/control/machines/box_alpha/approve")
        assert app_resp.status_code == 200
        assert app_resp.json()["status"] == "approved"

    def test_approval_tokens_api(self, client: TestClient) -> None:
        issue_resp = client.post(
            "/control/approval/tokens",
            json={
                "action_name": "db_drop_table",
                "target_resource": "db:users",
                "approver": "security_officer",
                "ttl_minutes": 10,
            },
        )
        assert issue_resp.status_code == 200
        data = issue_resp.json()
        assert "token_id" in data
        assert "raw_token" in data
        raw_token = data["raw_token"]

        # Verify dry-run
        dry_run_resp = client.post(
            "/control/approval/tokens/verify",
            json={
                "raw_token": raw_token,
                "action_name": "db_drop_table",
                "target_resource": "db:users",
                "dry_run": True,
            },
        )
        assert dry_run_resp.status_code == 200
        assert dry_run_resp.json()["dry_run_count"] == 1
        assert not dry_run_resp.json()["is_consumed"]

        # Final consume
        consume_resp = client.post(
            "/control/approval/tokens/verify",
            json={
                "raw_token": raw_token,
                "action_name": "db_drop_table",
                "target_resource": "db:users",
                "dry_run": False,
            },
        )
        assert consume_resp.status_code == 200
        assert consume_resp.json()["is_consumed"]

        # Re-consuming fails closed (HTTP 403)
        fail_resp = client.post(
            "/control/approval/tokens/verify",
            json={
                "raw_token": raw_token,
                "action_name": "db_drop_table",
                "target_resource": "db:users",
                "dry_run": False,
            },
        )
        assert fail_resp.status_code == 403

    def test_html_panel_rendering(
        self,
        client: TestClient,
        key_service: APIKeyService,
        cost_tracker: CostTracker,
        tool_meter: MCPToolMeter,
        budget_manager: BudgetManager,
        machine_manager: MachineApprovalManager,
        audit_log: AppendOnlyAuditLog,
    ) -> None:
        # Test direct renderer
        overview = build_overview(key_service, cost_tracker, tool_meter, budget_manager, machine_manager, audit_log)
        html = render_html_panel(overview)
        assert "<title>faccoder Control Plane</title>" in html
        assert "Active API Keys" in html

        # Test endpoint
        resp = client.get("/control/panel")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "faccoder Control Plane" in resp.text
