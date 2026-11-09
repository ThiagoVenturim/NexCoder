from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] | None = None


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    result: Any | None = None
    error: dict[str, Any] | None = None


class MCPToolSchema(BaseModel):
    name: str
    description: str
    inputSchema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})


class MCPContentItem(BaseModel):
    type: str = "text"
    text: str


class MCPToolCallResult(BaseModel):
    content: list[MCPContentItem]
    isError: bool = False
