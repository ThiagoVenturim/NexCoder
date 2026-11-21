from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from nexcoder_agents.catalog import AgentCatalog, SkillCatalog
from nexcoder_agents.catalog.models import AgentSpec
from nexcoder_agents.catalog.skills import SkillSpec
from nexcoder_agents.cli import main
from nexcoder_agents.export import (
    export_claude_package,
    format_claude_agent_md,
    resolve_safe_export_path,
    validate_safe_slug,
)


def test_format_claude_agent_md() -> None:
    catalog = AgentCatalog.default()
    architect = catalog.get_or_raise("lead-architect")
    formatted = format_claude_agent_md(architect)

    assert "---" in formatted
    assert "name: lead-architect" in formatted
    assert "description:" in formatted
    assert "skills:" in formatted
    assert "# Lead Architect" in formatted


def test_export_claude_package(tmp_path: Path) -> None:
    catalog = AgentCatalog.default()
    skills = SkillCatalog.default()

    out_dir = tmp_path / "claude_pkg"
    result = export_claude_package(
        catalog=catalog,
        output_dir=out_dir,
        skill_catalog=skills,
        sectors=["engineering", "stacks"],
        zip_output=True,
    )

    assert result.output_dir.is_dir()
    assert len(result.agents_exported) >= 5
    assert len(result.skills_exported) >= 3

    # Verify directory structure
    agents_dir = out_dir / "agents"
    skills_dir = out_dir / "skills"
    assert agents_dir.is_dir()
    assert skills_dir.is_dir()

    # Verify agent file format
    lead_arch = agents_dir / "lead-architect.md"
    assert lead_arch.is_file()
    arch_content = lead_arch.read_text(encoding="utf-8")
    assert "name: lead-architect" in arch_content

    # Verify skill file format
    delphi_skill = skills_dir / "delphi-crash-guard" / "SKILL.md"
    assert delphi_skill.is_file()

    # Verify manifest.json
    manifest_file = out_dir / "manifest.json"
    assert manifest_file.is_file()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_data["format"] == "claude-code-package"
    assert manifest_data["total_agents"] == len(result.agents_exported)

    # Verify zip output
    assert result.zip_path is not None
    assert result.zip_path.is_file()
    with zipfile.ZipFile(result.zip_path, "r") as z:
        namelist = z.namelist()
        assert "manifest.json" in namelist or any("manifest.json" in n for n in namelist)


def test_cli_execution(tmp_path: Path, capsys) -> None:
    # 1. list-agents
    ret_agents = main(["list-agents", "--sector", "engineering"])
    assert ret_agents == 0
    captured = capsys.readouterr()
    assert "lead-architect" in captured.out

    # 2. list-skills
    ret_skills = main(["list-skills"])
    assert ret_skills == 0
    captured_skills = capsys.readouterr()
    assert "delphi-crash-guard" in captured_skills.out

    # 3. export --claude
    target_dir = tmp_path / "cli_export"
    ret_export = main(["export", "--claude", "-o", str(target_dir), "-s", "direction"])
    assert ret_export == 0
    assert (target_dir / "manifest.json").is_file()


def test_cli_no_args_prints_help(capsys) -> None:
    code = main([])
    assert code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out.lower() or "nexcoder-agents" in captured.out


def test_export_claude_package_empty_sectors(tmp_path: Path) -> None:
    catalog = AgentCatalog.default()
    skills = SkillCatalog.default()

    out_dir = tmp_path / "empty_export"
    result = export_claude_package(
        catalog=catalog,
        output_dir=out_dir,
        skill_catalog=skills,
        sectors=["non-existent-sector"],
        zip_output=False,
    )
    assert len(result.agents_exported) == 0
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["total_agents"] == 0


def test_slug_validation_and_path_traversal_prevention(tmp_path: Path) -> None:
    # 1. Valid slugs pass
    assert validate_safe_slug("python-dev") == "python-dev"
    assert validate_safe_slug("qa_lead_01") == "qa_lead_01"

    # 2. Path traversal or invalid characters raise ValueError
    for bad_slug in ["../traversal", "sub/dir", "bad..name", "bad name", "a*b", "", ".."]:
        with pytest.raises(ValueError, match="Invalid"):
            validate_safe_slug(bad_slug)

    # 3. Model level validation
    with pytest.raises(ValueError, match="Invalid agent slug"):
        AgentSpec(name="Bad Agent", slug="../evil", sector="engineering")

    with pytest.raises(ValueError, match="Invalid skill slug"):
        SkillSpec(name="Bad Skill", slug="bad/skill", content="exploit")

    # 4. Safe path resolution prevents escaping base directory
    base = tmp_path / "sandbox"
    base.mkdir()
    safe_path = resolve_safe_export_path(base, "agents", "good.md")
    assert safe_path.is_relative_to(base.resolve())

    with pytest.raises(ValueError, match="Path traversal detected"):
        resolve_safe_export_path(base, "..", "outside.md")
