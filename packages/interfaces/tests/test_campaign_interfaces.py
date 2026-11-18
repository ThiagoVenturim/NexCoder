"""Offline tests for campaign REST API, MCP tools, and unified CLI (Issue #71)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from nexcoder_interfaces.api.app import create_app
from nexcoder_interfaces.cli.main import app as cli_app
from nexcoder_interfaces.mcp.protocol import JSONRPCRequest
from nexcoder_interfaces.mcp.server import MCPServer
from typer.testing import CliRunner


class TestCampaignInterfaces:
    def test_mcp_tools_list_and_call(self, tmp_path: Path) -> None:
        server = MCPServer()
        schemas = server.get_tool_schemas()
        tool_names = [s["name"] for s in schemas]

        assert "run_security_test_campaign" in tool_names
        assert "get_security_test_campaign" in tool_names
        assert "export_security_campaign_report" in tool_names

        # Call run_security_test_campaign (unauthorized)
        req_unauth = JSONRPCRequest(
            id=1,
            method="tools/call",
            params={
                "name": "run_security_test_campaign",
                "arguments": {
                    "target": "https://external.example.com",
                    "owned_target": False,
                },
            },
        )
        resp_unauth = server.handle_request(req_unauth)
        assert resp_unauth is not None
        assert resp_unauth.result is not None
        res_data = json.loads(resp_unauth.result["content"][0]["text"])
        assert res_data.get("status") == "rejected"

        # Call run_security_test_campaign (authorized)
        req_auth = JSONRPCRequest(
            id=2,
            method="tools/call",
            params={
                "name": "run_security_test_campaign",
                "arguments": {
                    "target": str(tmp_path),
                    "owned_target": True,
                    "authorized_by": "SecOps Tester",
                    "test_types": ["unit", "system"],
                },
            },
        )
        resp_auth = server.handle_request(req_auth)
        assert resp_auth is not None
        assert resp_auth.result is not None
        res_auth_data = json.loads(resp_auth.result["content"][0]["text"])
        assert res_auth_data.get("status") == "completed"
        camp_id = res_auth_data.get("campaign_id")
        assert camp_id is not None

        # Call get_security_test_campaign
        req_get = JSONRPCRequest(
            id=3,
            method="tools/call",
            params={
                "name": "get_security_test_campaign",
                "arguments": {"campaign_id": camp_id},
            },
        )
        resp_get = server.handle_request(req_get)
        assert resp_get is not None
        assert resp_get.result is not None
        res_get_data = json.loads(resp_get.result["content"][0]["text"])
        assert res_get_data.get("status") == "success"

        # Call export_security_campaign_report
        req_exp = JSONRPCRequest(
            id=4,
            method="tools/call",
            params={
                "name": "export_security_campaign_report",
                "arguments": {"campaign_id": camp_id, "format": "markdown"},
            },
        )
        resp_exp = server.handle_request(req_exp)
        assert resp_exp is not None
        assert resp_exp.result is not None
        res_exp_data = json.loads(resp_exp.result["content"][0]["text"])
        assert res_exp_data.get("status") == "success"
        assert "Report" in res_exp_data.get("content", "")

    def test_rest_api_campaign_endpoints(self, tmp_path: Path) -> None:
        app = create_app(insecure_local=True)
        client = TestClient(app)

        # 1. Trigger unauthorized campaign -> 403
        resp_unauth = client.post(
            "/v1/security/campaigns/run",
            json={
                "target": "https://external.example.com",
                "owned_target": False,
            },
        )
        assert resp_unauth.status_code == 403

        # 2. Trigger authorized campaign -> 200
        resp_auth = client.post(
            "/v1/security/campaigns/run",
            json={
                "target": str(tmp_path),
                "owned_target": True,
                "authorized_by": "API Operator",
                "test_types": ["unit", "api"],
                "agent_count": 2,
            },
        )
        assert resp_auth.status_code == 200
        data = resp_auth.json()
        assert data["status"] == "completed"
        camp_id = data["campaign_id"]

        # 3. List campaigns
        resp_list = client.get("/v1/security/campaigns")
        assert resp_list.status_code == 200
        campaigns = resp_list.json().get("campaigns", [])
        assert any(c["campaign_id"] == camp_id for c in campaigns)

        # 4. Get campaign details
        resp_get = client.get(f"/v1/security/campaigns/{camp_id}")
        assert resp_get.status_code == 200
        assert resp_get.json()["campaign"]["campaign_id"] == camp_id

        # 5. Export report Markdown
        resp_md = client.get(f"/v1/security/campaigns/{camp_id}/report?format=markdown")
        assert resp_md.status_code == 200
        assert "Campaign Report" in resp_md.text

        # 6. Export report HTML
        resp_html = client.get(f"/v1/security/campaigns/{camp_id}/report?format=html")
        assert resp_html.status_code == 200
        assert "<!DOCTYPE html>" in resp_html.text

    def test_unified_cli_campaign(self, tmp_path: Path) -> None:
        runner = CliRunner()

        # Run campaign
        res_run = runner.invoke(
            cli_app,
            [
                "campaign",
                "run",
                "--target",
                str(tmp_path),
                "--owned-target",
                "--authorized-by",
                "CLI Lead",
                "--json",
            ],
        )
        assert res_run.exit_code == 0
        parsed = json.loads(res_run.stdout)
        camp_id = parsed["campaign_id"]
        assert camp_id is not None

        # Get campaign
        res_get = runner.invoke(cli_app, ["campaign", "get", camp_id])
        assert res_get.exit_code == 0
        assert camp_id in res_get.stdout

        # Export campaign
        out_f = tmp_path / "cli_exported.md"
        res_exp = runner.invoke(
            cli_app,
            ["campaign", "export", camp_id, "--format", "markdown", "--output", str(out_f)],
        )
        assert res_exp.exit_code == 0
        assert out_f.exists()
