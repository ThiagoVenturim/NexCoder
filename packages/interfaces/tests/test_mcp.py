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
