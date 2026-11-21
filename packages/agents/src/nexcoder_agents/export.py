from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from nexcoder_agents.catalog.models import AgentSpec, validate_safe_slug
from nexcoder_agents.catalog.registry import AgentCatalog
from nexcoder_agents.catalog.skills import SkillCatalog, SkillSpec

logger = logging.getLogger(__name__)


def resolve_safe_export_path(base_dir: Path, *parts: str) -> Path:
    """Safely resolve an export target path and verify it remains strictly inside base_dir."""
    resolved_base = base_dir.resolve()
    target = resolved_base.joinpath(*parts).resolve()
    if not target.is_relative_to(resolved_base):
        raise ValueError(f"Path traversal detected: target '{target}' escapes base directory '{resolved_base}'.")
    return target


class ClaudeExportResult(BaseModel):
    """Result of exporting agents and skills to a Claude Code package."""

    output_dir: Path
    agents_exported: list[str] = Field(default_factory=list)
    skills_exported: list[str] = Field(default_factory=list)
    zip_path: Path | None = None
    manifest: dict[str, Any] = Field(default_factory=dict)


def _clean_single_line(text: str, limit: int = 400) -> str:
    """Format string for single-line YAML frontmatter attributes."""
    cleaned = " ".join(str(text or "").split())
    return cleaned[:limit].replace('"', "'")


def format_claude_agent_md(agent: AgentSpec) -> str:
    """Format an AgentSpec into Claude Code subagent markdown."""
    lines = [
        "---",
        f"name: {agent.slug}",
        f'description: "{_clean_single_line(agent.description or agent.name)}"',
    ]
    if agent.tools:
        lines.append(f"tools: {', '.join(agent.tools)}")
    if agent.skills:
        lines.append(f"skills: {', '.join(agent.skills)}")
    lines.append("---")
    header = "\n".join(lines)
    body = agent.prompt.strip()
    return f"{header}\n\n{body}\n"


def export_claude_package(
    catalog: AgentCatalog,
    output_dir: Path | str,
    skill_catalog: SkillCatalog | None = None,
    sectors: list[str] | None = None,
    tiers: list[str] | None = None,
    zip_output: bool = False,
) -> ClaudeExportResult:
    """Export catalog agents and declared skills into a Claude Code package."""
    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    agents_dir = out_path / "agents"
    skills_dir = out_path / "skills"
    agents_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)

    skills_source = skill_catalog or SkillCatalog.default()

    # 1. Filter and export agents
    all_agents = catalog.list()
    if sectors:
        all_agents = [a for a in all_agents if a.sector in sectors]
    if tiers:
        all_agents = [a for a in all_agents if a.tier in tiers]

    exported_agents: list[str] = []
    referenced_skills: set[str] = set()

    for agent in all_agents:
        validate_safe_slug(agent.slug, category="agent")
        agent_content = format_claude_agent_md(agent)
        agent_file = resolve_safe_export_path(agents_dir, f"{agent.slug}.md")
        agent_file.write_text(agent_content, encoding="utf-8")
        exported_agents.append(agent.slug)

        for skill_slug in agent.skills:
            referenced_skills.add(skill_slug)

    # 2. Export skills
    exported_skills: list[str] = []
    # Export all skills from the skill catalog, plus any referenced ones
    skills_to_export = set(referenced_skills) | {s.slug for s in skills_source.list()}

    for skill_slug in sorted(skills_to_export):
        validate_safe_slug(skill_slug, category="skill")
        skill_item = skills_source.get(skill_slug)
        skill_dest_dir = resolve_safe_export_path(skills_dir, skill_slug)
        skill_dest_dir.mkdir(parents=True, exist_ok=True)
        skill_dest_file = resolve_safe_export_path(skills_dir, skill_slug, "SKILL.md")

        if skill_item is not None:
            content = skill_item.to_markdown()
        else:
            # Fallback placeholder for referenced skill not yet fully documented
            placeholder = SkillSpec(
                name=skill_slug.replace("-", " ").title(),
                slug=skill_slug,
                description=f"Skill {skill_slug} referenced by exported agent.",
                content=f"# {skill_slug.replace('-', ' ').title()}\n\nGuidance for {skill_slug}.\n",
            )
            content = placeholder.to_markdown()

        skill_dest_file.write_text(content, encoding="utf-8")
        exported_skills.append(skill_slug)

    # 3. Generate manifest and README
    now_iso = datetime.now(UTC).isoformat()
    manifest_data: dict[str, Any] = {
        "format": "claude-code-package",
        "version": "0.1.0",
        "generated_at": now_iso,
        "total_agents": len(exported_agents),
        "total_skills": len(exported_skills),
        "agents": [
            {
                "slug": a.slug,
                "name": a.name,
                "sector": a.sector,
                "tier": a.tier,
                "tools": a.tools,
                "skills": a.skills,
            }
            for a in all_agents
        ],
        "skills": exported_skills,
    }

    manifest_file = out_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    readme_content = f"""# Claude Code Agent & Skill Package

Generated by nexcoder-agents on {now_iso}.

## Contents
- **Agents**: {len(exported_agents)} subagents in `agents/`
- **Skills**: {len(exported_skills)} skills in `skills/`

## Usage with Claude Code
1. Copy the contents of `agents/` into your project's `.claude/agents/` (or run as subagents).
2. Copy the contents of `skills/` into your `.claude/skills/` directory.
"""
    (out_path / "README.md").write_text(readme_content, encoding="utf-8")

    zip_file_path = None
    if zip_output:
        archive_name = out_path.with_suffix(".zip")
        shutil.make_archive(str(out_path), "zip", out_path)
        zip_file_path = archive_name

    return ClaudeExportResult(
        output_dir=out_path,
        agents_exported=exported_agents,
        skills_exported=exported_skills,
        zip_path=zip_file_path,
        manifest=manifest_data,
    )
