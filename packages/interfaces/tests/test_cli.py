from __future__ import annotations

import json
from pathlib import Path

from faccoder_interfaces.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "idea" in result.stdout
    assert "judge" in result.stdout
    assert "plan" in result.stdout
    assert "serve" in result.stdout


def test_cli_init_command(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "Successfully initialized faccoder project" in result.stdout

    config_file = tmp_path / "faccoder.yaml"
    assert config_file.is_file()
    content = config_file.read_text(encoding="utf-8")
    assert "preset: hybrid" in content


def test_cli_idea_command() -> None:
    result = runner.invoke(app, ["idea", "Automated code review agent", "--dry-run"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "success"
    assert "market" in data


def test_cli_judge_command() -> None:
    result = runner.invoke(app, ["judge", "Automated test generator", "--dry-run"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "success"
    assert "verdict" in data


def test_cli_plan_command(tmp_path: Path) -> None:
    prd_file = tmp_path / "prd.md"
    prd_file.write_text(
        "# PRD: Test\n# Epic: E1\n## Story: S1\n### Task: T1\n- Layer: backend\n- Estimate: 4.0h\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["plan", str(prd_file)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "success"
    assert data["tasks_count"] == 1


def test_cli_index_command(tmp_path: Path) -> None:
    code_file = tmp_path / "mod.py"
    code_file.write_text("def test_func(): pass\n", encoding="utf-8")
    result = runner.invoke(app, ["index", "--path", str(tmp_path)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "success"


def test_cli_docs_command(tmp_path: Path) -> None:
    code_file = tmp_path / "mod.py"
    code_file.write_text("def documented_func(): pass\n", encoding="utf-8")
    result = runner.invoke(app, ["docs", "--path", str(tmp_path), "--level", "module"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "success"


def test_cli_capture_command() -> None:
    result = runner.invoke(app, ["capture", "https://example.com"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "unavailable"
    assert data["module"] == "capture"


def test_cli_run_agent_command() -> None:
    result = runner.invoke(app, ["run", "lead-architect", "--task", "Design database"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "success"
    assert data["agent"]["slug"] == "lead-architect"


def test_cli_run_pipeline_command() -> None:
    result = runner.invoke(app, ["run", "standard_pipeline", "--pipeline", "--task", "Run checks"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "success"


def test_cli_export_mcp_command(tmp_path: Path) -> None:
    result = runner.invoke(app, ["export", "mcp", "--out", str(tmp_path)])
    assert result.exit_code == 0
    mcp_file = tmp_path / ".mcp.json"
    assert mcp_file.is_file()
    data = json.loads(mcp_file.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    assert "faccoder" in data["mcpServers"]


def test_cli_export_claude_command(tmp_path: Path) -> None:
    out_dir = tmp_path / "claude_out"
    result = runner.invoke(app, ["export", "claude", "--out", str(out_dir)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert Path(data["mcp_config"]).is_file()
