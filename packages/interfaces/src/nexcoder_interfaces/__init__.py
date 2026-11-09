"""nexcoder-interfaces: Unified CLI, MCP server, and REST API for nexcoder."""

from __future__ import annotations

from nexcoder_interfaces.api.app import app, create_app
from nexcoder_interfaces.cli.main import main
from nexcoder_interfaces.mcp.server import MCPServer
from nexcoder_interfaces.plugin.claude import export_claude_plugin, generate_mcp_json, write_mcp_json
from nexcoder_interfaces.registry import get_module_statuses
from nexcoder_interfaces.tools import TOOL_DEFINITIONS

__version__ = "0.1.0"

__all__ = [
    "MCPServer",
    "TOOL_DEFINITIONS",
    "__version__",
    "app",
    "create_app",
    "export_claude_plugin",
    "generate_mcp_json",
    "get_module_statuses",
    "main",
    "write_mcp_json",
]
