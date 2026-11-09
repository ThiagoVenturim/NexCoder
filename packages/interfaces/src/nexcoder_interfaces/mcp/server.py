from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from typing import Any, TextIO

from faccoder_interfaces.mcp.protocol import (
    JSONRPCRequest,
    JSONRPCResponse,
    MCPContentItem,
    MCPToolCallResult,
    MCPToolSchema,
)
from faccoder_interfaces.tools import TOOL_DEFINITIONS, ToolDefinition

logger = logging.getLogger(__name__)


class MCPServer:
    """Model Context Protocol (MCP) server supporting stdio and streamable HTTP / SSE."""

    def __init__(
        self,
        name: str = "faccoder",
        version: str = "0.1.0",
        tools: dict[str, ToolDefinition] | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.tools = tools if tools is not None else TOOL_DEFINITIONS
        self._sse_sessions: dict[str, asyncio.Queue[str]] = {}

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return list of tool schemas for MCP tools/list."""
        schemas = []
        for _name, tool in self.tools.items():
            schemas.append(
                MCPToolSchema(
                    name=tool.name,
                    description=tool.description,
                    inputSchema=tool.parameters,
                ).model_dump()
            )
        return schemas

    def handle_request(self, req: JSONRPCRequest) -> JSONRPCResponse | None:
        """Dispatch a single JSON-RPC 2.0 request."""
        # Notifications (no id)
        if req.id is None and req.method.startswith("notifications/"):
            return None

        if req.method == "initialize":
            return JSONRPCResponse(
                id=req.id,
                result={
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": self.name,
                        "version": self.version,
                    },
                    "capabilities": {
                        "tools": {
                            "listChanged": False,
                        },
                        "logging": {},
                    },
                },
            )

        if req.method == "ping":
            return JSONRPCResponse(id=req.id, result={})

        if req.method == "tools/list":
            return JSONRPCResponse(
                id=req.id,
                result={"tools": self.get_tool_schemas()},
            )

        if req.method == "tools/call":
            params = req.params or {}
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if not tool_name or tool_name not in self.tools:
                return JSONRPCResponse(
                    id=req.id,
                    error={
                        "code": -32601,
                        "message": f"Method or tool not found: '{tool_name}'",
                    },
                )

            tool = self.tools[tool_name]
            try:
                result_data = tool.handler(**arguments)
                text_content = json.dumps(result_data, indent=2, default=str)
                is_error = isinstance(result_data, dict) and result_data.get("status") in ("error", "rejected")
                call_result = MCPToolCallResult(
                    content=[MCPContentItem(type="text", text=text_content)],
                    isError=is_error,
                )
                return JSONRPCResponse(id=req.id, result=call_result.model_dump())
            except Exception as exc:
                logger.exception("Error executing tool %s: %s", tool_name, exc)
                call_result = MCPToolCallResult(
                    content=[MCPContentItem(type="text", text=f"Error executing tool: {exc}")],
                    isError=True,
                )
                return JSONRPCResponse(id=req.id, result=call_result.model_dump())

        # Unknown method
        return JSONRPCResponse(
            id=req.id,
            error={
                "code": -32601,
                "message": f"Method '{req.method}' not found",
            },
        )

    def handle_message_json(self, raw_json: str) -> str | None:
        """Parse raw JSON line, dispatch request, and return JSON string response."""
        try:
            data = json.loads(raw_json)
        except Exception as exc:
            err = JSONRPCResponse(
                id=None,
                error={"code": -32700, "message": f"Parse error: {exc}"},
            )
            return err.model_dump_json()

        if isinstance(data, list):
            responses = []
            for item in data:
                req = JSONRPCRequest.model_validate(item)
                res = self.handle_request(req)
                if res:
                    responses.append(res.model_dump())
            return json.dumps(responses) if responses else None

        req = JSONRPCRequest.model_validate(data)
        res = self.handle_request(req)
        return res.model_dump_json() if res else None

    def process_stdio_sync(self, input_stream: TextIO, output_stream: TextIO) -> None:
        """Process requests synchronously over given streams until EOF."""
        for line in input_stream:
            line = line.strip()
            if not line:
                continue
            resp = self.handle_message_json(line)
            if resp:
                output_stream.write(resp + "\n")
                output_stream.flush()

    async def run_stdio(self) -> None:
        """Run MCP server reading from sys.stdin and writing to sys.stdout."""
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while not reader.at_eof():
            line_bytes = await reader.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8").strip()
            if not line:
                continue
            response_json = self.handle_message_json(line)
            if response_json:
                sys.stdout.write(response_json + "\n")
                sys.stdout.flush()

    def create_sse_session(self) -> tuple[str, asyncio.Queue[str]]:
        """Create a new SSE session queue."""
        session_id = str(uuid.uuid4())
        queue: asyncio.Queue[str] = asyncio.Queue()
        self._sse_sessions[session_id] = queue
        return session_id, queue

    def close_sse_session(self, session_id: str) -> None:
        """Remove SSE session."""
        self._sse_sessions.pop(session_id, None)

    async def post_sse_message(self, session_id: str, raw_json: str) -> str | None:
        """Receive message from client and enqueue response to the session's SSE stream."""
        response_json = self.handle_message_json(raw_json)
        queue = self._sse_sessions.get(session_id)
        if queue and response_json:
            await queue.put(response_json)
        return response_json
