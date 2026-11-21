from __future__ import annotations

import json
from pathlib import Path

from nexcoder_interfaces.plugin.claude import (
    export_claude_plugin,
    generate_mcp_json,
    write_mcp_json,
)


def test_generate_mcp_json_stdio() -> None:
    config = generate_mcp_json(transport="stdio")
    assert "mcpServers" in config
    assert "nexcoder" in config["mcpServers"]
    server = config["mcpServers"]["nexcoder"]
    assert server["command"] == "nexcoder"
    assert server["args"] == ["serve", "--transport", "stdio"]


def test_generate_mcp_json_sse() -> None:
    config = generate_mcp_json(transport="sse", url="http://127.0.0.1:9000/sse")
    server = config["mcpServers"]["nexcoder"]
    assert server["transport"] == "sse"
    assert server["url"] == "http://127.0.0.1:9000/sse"


def test_write_mcp_json(tmp_path: Path) -> None:
    out_file = write_mcp_json(output_dir=tmp_path, transport="stdio")
    assert out_file.is_file()
    assert out_file.name == ".mcp.json"

    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert "nexcoder" in data["mcpServers"]


def test_export_claude_plugin(tmp_path: Path) -> None:
    out_dir = tmp_path / "plugin_export"
    res = export_claude_plugin(output_dir=out_dir, transport="stdio")

    assert Path(res["mcp_config"]).is_file()
    assert len(res["agents_exported"]) >= 5
    assert len(res["skills_exported"]) >= 3
