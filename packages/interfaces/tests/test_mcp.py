from __future__ import annotations

import io
import json

from faccoder_interfaces.mcp.protocol import JSONRPCRequest
from faccoder_interfaces.mcp.server import MCPServer


def test_mcp_initialize() -> None:
    server = MCPServer()
    req = JSONRPCRequest(id=1, method="initialize")
    res = server.handle_request(req)

    assert res is not None
    assert res.id == 1
    assert res.result["protocolVersion"] == "2024-11-05"
    assert res.result["serverInfo"]["name"] == "faccoder"
    assert "tools" in res.result["capabilities"]


def test_mcp_ping() -> None:
    server = MCPServer()
    req = JSONRPCRequest(id="ping-1", method="ping")
    res = server.handle_request(req)

    assert res is not None
    assert res.id == "ping-1"
    assert res.result == {}


def test_mcp_tools_list() -> None:
    server = MCPServer()
    req = JSONRPCRequest(id=2, method="tools/list")
    res = server.handle_request(req)

    assert res is not None
    assert "tools" in res.result
    tool_names = [t["name"] for t in res.result["tools"]]
    assert "research_idea" in tool_names
    assert "judge_idea" in tool_names
    assert "plan_sprints" in tool_names
    assert "capture_page" in tool_names


def test_mcp_tools_call_success() -> None:
    server = MCPServer()
    req = JSONRPCRequest(
        id=3,
        method="tools/call",
        params={
            "name": "research_idea",
            "arguments": {"idea": "AI documentation engine", "dry_run": True},
        },
    )
    res = server.handle_request(req)

    assert res is not None
    assert res.id == 3
    assert res.error is None
    content = res.result["content"]
    assert len(content) == 1
    payload = json.loads(content[0]["text"])
    assert payload["status"] == "success"


def test_mcp_tools_call_unavailable_tool() -> None:
    server = MCPServer()
    req = JSONRPCRequest(
        id=4,
        method="tools/call",
        params={
            "name": "capture_page",
            "arguments": {"url": "https://example.com"},
        },
    )
    res = server.handle_request(req)

    assert res is not None
    content = res.result["content"]
    payload = json.loads(content[0]["text"])
    assert payload["status"] == "unavailable"
    assert payload["module"] == "capture"


def test_mcp_tools_call_unknown_tool() -> None:
    server = MCPServer()
    req = JSONRPCRequest(
        id=5,
        method="tools/call",
        params={"name": "unknown_tool_xyz"},
    )
    res = server.handle_request(req)

    assert res is not None
    assert res.error is not None
    assert res.error["code"] == -32601


def test_mcp_handle_message_json_parse_error() -> None:
    server = MCPServer()
    resp_raw = server.handle_message_json("invalid json {{{")
    assert resp_raw is not None
    resp = json.loads(resp_raw)
    assert resp["error"]["code"] == -32700


def test_mcp_process_stdio_sync() -> None:
    server = MCPServer()
    input_stream = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 10, "method": "ping"}) + "\n")
    output_stream = io.StringIO()

    server.process_stdio_sync(input_stream, output_stream)
    output_lines = output_stream.getvalue().strip().splitlines()

    assert len(output_lines) == 1
    resp = json.loads(output_lines[0])
    assert resp["id"] == 10
    assert resp["result"] == {}


def test_mcp_sse_session_lifecycle() -> None:
    async def _run() -> None:
        server = MCPServer()
        session_id, queue = server.create_sse_session()
        assert session_id in server._sse_sessions

        # Post message
        msg = json.dumps({"jsonrpc": "2.0", "id": 42, "method": "ping"})
        await server.post_sse_message(session_id, msg)

        received = await queue.get()
        parsed = json.loads(received)
        assert parsed["id"] == 42

        server.close_sse_session(session_id)
        assert session_id not in server._sse_sessions

    import asyncio

    asyncio.run(_run())


def test_mcp_approve_step_token_aleatorio_rejeita() -> None:
    server = MCPServer()

    # Step 1: Start pipeline that pauses on approval
    call_pipe = JSONRPCRequest(
        id=50,
        method="tools/call",
        params={
            "name": "run_pipeline",
            "arguments": {"pipeline_name": "mcp_gate_pipeline", "dry_run": False},
        },
    )
    pipe_res = server.handle_request(call_pipe)
    assert pipe_res is not None
    payload = json.loads(pipe_res.result["content"][0]["text"])
    action_name = payload["approval"]["action_name"]
    exec_id = payload["execution_id"]

    # Step 2: Call approve_step with random 8+ char token -> rejected
    call_appr = JSONRPCRequest(
        id=51,
        method="tools/call",
        params={
            "name": "approve_step",
            "arguments": {
                "action_name": action_name,
                "token": "random_fake_token_12345",
                "execution_id": exec_id,
            },
        },
    )
    appr_res = server.handle_request(call_appr)
    assert appr_res is not None
    appr_payload = json.loads(appr_res.result["content"][0]["text"])
    assert appr_payload["status"] == "rejected"
    assert appr_payload["approved"] is False


def test_mcp_approve_step_valid_and_single_use() -> None:
    server = MCPServer()

    # Step 1: Start pipeline that pauses on approval
    call_pipe = JSONRPCRequest(
        id=60,
        method="tools/call",
        params={
            "name": "run_pipeline",
            "arguments": {"pipeline_name": "mcp_gate_valid", "dry_run": False},
        },
    )
    pipe_res = server.handle_request(call_pipe)
    assert pipe_res is not None
    payload = json.loads(pipe_res.result["content"][0]["text"])
    action_name = payload["approval"]["action_name"]
    exec_id = payload["execution_id"]
    valid_token = payload["approval"]["token"]

    # Step 2: First approval succeeds
    call_appr1 = JSONRPCRequest(
        id=61,
        method="tools/call",
        params={
            "name": "approve_step",
            "arguments": {
                "action_name": action_name,
                "token": valid_token,
                "execution_id": exec_id,
            },
        },
    )
    appr_res1 = server.handle_request(call_appr1)
    assert appr_res1 is not None
    res1_payload = json.loads(appr_res1.result["content"][0]["text"])
    assert res1_payload["status"] == "approved"
    assert res1_payload["approved"] is True

    # Step 3: Second approval with same token fails (single use)
    call_appr2 = JSONRPCRequest(
        id=62,
        method="tools/call",
        params={
            "name": "approve_step",
            "arguments": {
                "action_name": action_name,
                "token": valid_token,
                "execution_id": exec_id,
            },
        },
    )
    appr_res2 = server.handle_request(call_appr2)
    assert appr_res2 is not None
    res2_payload = json.loads(appr_res2.result["content"][0]["text"])
    assert res2_payload["status"] == "rejected"
    assert res2_payload["approved"] is False
