from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from faccoder_agents.catalog.models import AgentSpec

logger = logging.getLogger(__name__)

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def parse_agent_markdown(content: str, default_slug: str = "", default_sector: str = "") -> AgentSpec:
    """Parse a markdown file with YAML frontmatter into an AgentSpec."""
    match = _FRONTMATTER_PATTERN.match(content.strip())
    if match:
        raw_yaml = match.group(1)
        body = match.group(2).strip()
        data: dict[str, Any] = yaml.safe_load(raw_yaml) or {}
    else:
        # File has no frontmatter
        data = {}
        body = content.strip()

    name = data.get("name") or default_slug.replace("-", " ").title() or "Unnamed Agent"
    slug = data.get("slug") or default_slug or name.lower().replace(" ", "-")
    sector = data.get("sector") or default_sector or "engineering"
    tier = data.get("tier") or "medium"
    description = data.get("description") or ""
    tools = data.get("tools") or []
    skills = data.get("skills") or []
    scripts = data.get("scripts") or []
    prompt = data.get("prompt") or body

    # Collect additional metadata
    reserved_keys = {"name", "slug", "sector", "tier", "description", "tools", "skills", "scripts", "prompt"}
    extra_metadata = {k: v for k, v in data.items() if k not in reserved_keys}

    return AgentSpec(
        name=name,
        slug=slug,
        sector=sector,
        tier=tier,
        description=description,
        tools=tools,
        skills=skills,
        scripts=scripts,
        prompt=prompt,
        metadata=extra_metadata,
    )


def load_agent_file(path: Path) -> AgentSpec:
    """Load an AgentSpec from a markdown file on disk."""
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Agent file not found: {path}")

    content = path.read_text(encoding="utf-8")
    default_slug = path.stem
    default_sector = path.parent.name

    spec = parse_agent_markdown(content, default_slug=default_slug, default_sector=default_sector)
    spec.source_path = path
    return spec


def load_agents_from_dir(directory: Path) -> list[AgentSpec]:
    """Recursively discover and load all .md agent specs from a directory."""
    directory = Path(directory).resolve()
    if not directory.is_dir():
        return []

    agents: list[AgentSpec] = []
    for md_file in sorted(directory.rglob("*.md")):
        if md_file.name.upper() == "README.MD":
            continue
        try:
            agent = load_agent_file(md_file)
            agents.append(agent)
        except (yaml.YAMLError, OSError, ValueError) as exc:
            logger.debug("Skipping unparseable markdown file %s: %s", md_file, exc)

    return agents
