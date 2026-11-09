from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def generate_mcp_json(
    transport: str = "stdio",
    server_name: str = "nexcoder",
    command: str = "nexcoder",
    args: list[str] | None = None,
    url: str = "http://127.0.0.1:8000/sse",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Generate Claude Code .mcp.json configuration dictionary."""
    if transport == "sse":
        server_config: dict[str, Any] = {
            "url": url,
            "transport": "sse",
        }
    else:
        server_config = {
            "command": command,
            "args": args if args is not None else ["serve", "--transport", "stdio"],
            "env": env or {},
        }

    return {
        "mcpServers": {
            server_name: server_config,
        }
    }


def write_mcp_json(
    output_dir: Path | str = ".",
    transport: str = "stdio",
    server_name: str = "nexcoder",
    command: str = "nexcoder",
    args: list[str] | None = None,
    url: str = "http://127.0.0.1:8000/sse",
    env: dict[str, str] | None = None,
) -> Path:
    """Write .mcp.json file into the target directory."""
    target_path = Path(output_dir).resolve() / ".mcp.json"
    config_dict = generate_mcp_json(
        transport=transport,
        server_name=server_name,
        command=command,
        args=args,
        url=url,
        env=env,
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(config_dict, indent=2), encoding="utf-8")
    return target_path


def export_claude_plugin(
    output_dir: Path | str = ".",
    transport: str = "stdio",
    include_agents: bool = True,
    zip_output: bool = False,
) -> dict[str, Any]:
    """Export complete Claude Code workspace bundle with .mcp.json, agents, and skills."""
    target = Path(output_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)

    mcp_file = write_mcp_json(output_dir=target, transport=transport)
    result: dict[str, Any] = {
        "output_dir": str(target),
        "mcp_config": str(mcp_file),
        "agents_exported": [],
        "skills_exported": [],
    }

    if include_agents:
        try:
            from nexcoder_agents.catalog import AgentCatalog, SkillCatalog
            from nexcoder_agents.export import export_claude_package

            catalog = AgentCatalog.default()
            skills = SkillCatalog.default()
            export_res = export_claude_package(
                catalog=catalog,
                output_dir=target,
                skill_catalog=skills,
                zip_output=zip_output,
            )
            result["agents_exported"] = export_res.agents_exported
            result["skills_exported"] = export_res.skills_exported
            if export_res.zip_path:
                result["zip_path"] = str(export_res.zip_path)
        except Exception as exc:
            result["agent_export_error"] = str(exc)

    return result
