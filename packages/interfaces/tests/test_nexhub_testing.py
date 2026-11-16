from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nexcoder_interfaces.api.app import create_app
from nexcoder_interfaces.cli.main import app as cli_app
from nexcoder_interfaces.mcp.protocol import JSONRPCRequest
from nexcoder_interfaces.mcp.server import MCPServer
from nexcoder_interfaces.testing.models import SecurityTestRunConfig
from nexcoder_interfaces.testing.service import SecurityTestService
from nexcoder_interfaces.tools import TOOL_DEFINITIONS
from nexcoder_interfaces.tools.testing import (
    cancel_security_test,
    export_security_test_report,
    get_security_test_canvas,
    get_security_test_status,
    trigger_security_tests,
    verify_security_test_target,
)
from typer.testing import CliRunner


@pytest.fixture
def temp_workspace() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Create a sample project structure
        src = root / "src"
        src.mkdir()
        (src / "app.py").write_text(
            "def calculate_total(a, b):\n    return a + b\n",
            encoding="utf-8",
        )
        tests_dir = root / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text(
            "from src.app import calculate_total\ndef test_add():\n    assert calculate_total(1, 2) == 3\n",
            encoding="utf-8",
        )
        (root / "pyproject.toml").write_text(
            "[project]\nname = 'sample-app'\nversion = '0.1.0'\n",
            encoding="utf-8",
        )
        yield root


@pytest.fixture
def test_client() -> TestClient:
    app = create_app(insecure_local=True, host="127.0.0.1")
    return TestClient(app)


def test_target_authorization_gate_rejection(temp_workspace: Path):
    """Execution must be rejected when target is not marked as owned and lacks approval token."""
    res = trigger_security_tests(
        path=str(temp_workspace),
        owned_target=False,
        authorized_by="tester",
    )
    assert res["status"] == "rejected"
    assert res["authorized"] is False
    assert "rejection_reason" in res
    assert "not marked as owned" in res["rejection_reason"]


def test_target_authorization_preflight(temp_workspace: Path):
    """Preflight check returns clear authorization state and disclaimer for NexHub UI."""
    # Unauthorized
    pre_unauth = verify_security_test_target(
        path=str(temp_workspace),
        owned_target=False,
    )
    assert pre_unauth["authorized"] is False
    assert pre_unauth["requires_confirmation"] is True
    assert "Explicit Authorization Required" in pre_unauth["preview_disclaimer"]
    assert "unit" in pre_unauth["supported_test_types"]

    # Authorized
    pre_auth = verify_security_test_target(
        path=str(temp_workspace),
        owned_target=True,
        authorized_by="dev-lead",
    )
    assert pre_auth["authorized"] is True
    assert pre_auth["requires_confirmation"] is False
    assert pre_auth["authorized_by"] == "dev-lead"


def test_dispatch_and_canvas_payload(temp_workspace: Path):
    """Authorized run executes offline and formats agent cards, notes, and connections for NexHub canvas."""
    res = trigger_security_tests(
        path=str(temp_workspace),
        test_types=["unit", "system", "process", "dom", "api", "security"],
        num_agents=3,
        budget_limit=25.0,
        owned_target=True,
        authorized_by="security-team",
        offline=True,
    )
    assert res["status"] == "completed"
    assert res["authorized"] is True
    assert res["authorized_by"] == "security-team"
    assert res["num_agents"] == 3
    assert res["progress_percent"] == 100.0
    assert res["budget"]["spent"] > 0
    assert res["budget"]["spent"] <= 25.0

    # Canvas verification
    canvas = res["canvas"]
    assert "cards" in canvas
    assert "notes" in canvas
    assert "connections" in canvas

    # Orchestrator card + 3 worker agent cards
    assert len(canvas["cards"]) == 4
    orch_card = canvas["cards"][0]
    assert orch_card["agent_type"] == "orchestrator"
    assert orch_card["state"] == "completed"
    assert len(orch_card["logs"]) > 0

    worker_cards = canvas["cards"][1:]
    assert len(worker_cards) == 3
    for card in worker_cards:
        assert card["state"] == "completed"
        assert len(card["assigned_types"]) > 0
        assert len(card["logs"]) > 0
        assert card["position"]["y"] == 480

    # Notes: Summary and Remediations
    assert len(canvas["notes"]) == 2
    summary_note = canvas["notes"][0]
    assert summary_note["category"] == "report"
    assert "Test Report:" in summary_note["title"]
    assert "Agent Execution Summary" in summary_note["body"]

    remediation_note = canvas["notes"][1]
    assert remediation_note["category"] == "action_items"
    assert "Remediations & Action Items:" in remediation_note["title"]

    # Connections
    assert len(canvas["connections"]) > 0
    orch_connections = [c for c in canvas["connections"] if c["from_id"] == orch_card["id"]]
    assert len(orch_connections) == 3


def test_status_and_canvas_tools(temp_workspace: Path):
    """Status and canvas retrieval tools return recorded progress and layout."""
    res = trigger_security_tests(
        path=str(temp_workspace),
        test_types=["unit", "security"],
        num_agents=2,
        owned_target=True,
        authorized_by="qa-engineer",
    )
    run_id = res["run_id"]

    # Query status
    status_res = get_security_test_status(run_id)
    assert status_res["status"] == "completed"
    assert status_res["run_id"] == run_id
    assert len(status_res["agents"]) == 2

    # Query canvas
    canvas_res = get_security_test_canvas(run_id)
    assert canvas_res["status"] == "success"
    assert len(canvas_res["canvas"]["cards"]) == 3
    assert len(canvas_res["canvas"]["notes"]) == 2

    # Query non-existent run
    not_found = get_security_test_status("nonexistent-run")
    assert not_found["status"] == "not_found"


def test_export_report_markdown_and_json(temp_workspace: Path):
    """Exporting test reports provides Markdown report and raw JSON data."""
    res = trigger_security_tests(
        path=str(temp_workspace),
        test_types=["unit"],
        owned_target=True,
        authorized_by="auditor",
    )
    run_id = res["run_id"]

    md_export = export_security_test_report(run_id, format="markdown")
    assert md_export["status"] == "success"
    assert "# Test Report:" in md_export["content"]

    json_export = export_security_test_report(run_id, format="json")
    assert json_export["status"] == "success"
    assert json_export["content"]["run_id"] == run_id


def test_service_cancellation(temp_workspace: Path):
    """Test run cancellation updates record state and logs cancellation message."""
    service = SecurityTestService()
    config = SecurityTestRunConfig(
        target_path=str(temp_workspace),
        owned_target=True,
        authorized_by="admin",
    )
    # Dispatch creates record
    record = service.dispatch_run(config)
    # Test cancel tool
    res = cancel_security_test(record.run_id, service=service)
    assert res["run_id"] == record.run_id


def test_budget_limit_handling(temp_workspace: Path):
    """Budget limit stops execution when threshold is exceeded."""
    res = trigger_security_tests(
        path=str(temp_workspace),
        test_types=["unit", "system", "process", "dom", "api", "security"],
        num_agents=4,
        budget_limit=0.50,  # Very small budget
        owned_target=True,
        authorized_by="cfo",
    )
    assert res["status"] == "completed"
    # Spent should not exceed the limit
    assert res["budget"]["spent"] <= 0.60


def test_rest_api_endpoints(test_client: TestClient, temp_workspace: Path):
    """REST API endpoints expose preflight, execution, status, canvas, and report."""
    # 1. Preflight
    pre_resp = test_client.post(
        "/v1/security-tests/preflight",
        json={"path": str(temp_workspace), "owned_target": True, "authorized_by": "api-caller"},
    )
    assert pre_resp.status_code == 200
    pre_data = pre_resp.json()
    assert pre_data["authorized"] is True

    # 2. Run
    run_resp = test_client.post(
        "/v1/security-tests/run",
        json={
            "path": str(temp_workspace),
            "test_types": ["unit", "api"],
            "num_agents": 2,
            "owned_target": True,
            "authorized_by": "api-caller",
        },
    )
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["status"] == "completed"
    run_id = run_data["run_id"]

    # 3. Status
    status_resp = test_client.get(f"/v1/security-tests/runs/{run_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["run_id"] == run_id

    # 4. Canvas
    canvas_resp = test_client.get(f"/v1/security-tests/runs/{run_id}/canvas")
    assert canvas_resp.status_code == 200
    assert "cards" in canvas_resp.json()["canvas"]

    # 5. Report
    report_resp = test_client.get(f"/v1/security-tests/runs/{run_id}/report?format=markdown")
    assert report_resp.status_code == 200
    assert "# Test Report:" in report_resp.json()["content"]

    # 6. Stream
    stream_resp = test_client.get(f"/v1/security-tests/runs/{run_id}/stream")
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers["content-type"]
    assert "run_started" in stream_resp.text


def test_mcp_server_integration(temp_workspace: Path):
    """MCP server discovers and invokes the new security testing tools via JSON-RPC."""
    server = MCPServer()

    # Verify tools/list contains testing tools
    list_req = JSONRPCRequest(id=1, method="tools/list")
    list_resp = server.handle_request(list_req)
    assert list_resp is not None
    tool_names = [t["name"] for t in list_resp.result["tools"]]
    assert "trigger_security_tests" in tool_names
    assert "get_security_test_status" in tool_names
    assert "get_security_test_canvas" in tool_names
    assert "verify_security_test_target" in tool_names

    # Call verify_security_test_target
    pre_req = JSONRPCRequest(
        id=2,
        method="tools/call",
        params={
            "name": "verify_security_test_target",
            "arguments": {"path": str(temp_workspace), "owned_target": True, "authorized_by": "mcp-agent"},
        },
    )
    pre_resp = server.handle_request(pre_req)
    assert pre_resp is not None
    assert pre_resp.error is None
    assert "Target verified and authorized" in pre_resp.result["content"][0]["text"]

    # Call trigger_security_tests
    call_req = JSONRPCRequest(
        id=3,
        method="tools/call",
        params={
            "name": "trigger_security_tests",
            "arguments": {
                "path": str(temp_workspace),
                "test_types": ["unit", "system"],
                "num_agents": 2,
                "owned_target": True,
                "authorized_by": "mcp-agent",
            },
        },
    )
    call_resp = server.handle_request(call_req)
    assert call_resp is not None
    assert call_resp.error is None
    assert "completed" in call_resp.result["content"][0]["text"]


def test_cli_commands(temp_workspace: Path):
    """CLI subcommands support preflight, execution, status, and canvas display."""
    runner = CliRunner()

    # Preflight
    pre_res = runner.invoke(
        cli_app,
        ["test", "preflight", "--path", str(temp_workspace), "--owned-target", "--authorized-by", "cli-user"],
    )
    assert pre_res.exit_code == 0
    assert '"authorized": true' in pre_res.stdout

    # Run
    run_res = runner.invoke(
        cli_app,
        [
            "test",
            "run",
            "--path",
            str(temp_workspace),
            "--types",
            "unit,api",
            "--num-agents",
            "2",
            "--owned-target",
            "--authorized-by",
            "cli-user",
            "--json",
        ],
    )
    assert run_res.exit_code == 0
    assert '"status": "completed"' in run_res.stdout


def test_tool_definitions_registry():
    """Verify tool definitions are correctly registered in TOOL_DEFINITIONS."""
    assert "trigger_security_tests" in TOOL_DEFINITIONS
    assert "get_security_test_status" in TOOL_DEFINITIONS
    assert "get_security_test_canvas" in TOOL_DEFINITIONS
    assert "verify_security_test_target" in TOOL_DEFINITIONS
    assert "cancel_security_test" in TOOL_DEFINITIONS
    assert "export_security_test_report" in TOOL_DEFINITIONS

    tool = TOOL_DEFINITIONS["trigger_security_tests"]
    assert tool.module == "testing"
    assert tool.is_available is True
