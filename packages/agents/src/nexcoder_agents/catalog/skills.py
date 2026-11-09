from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from faccoder_agents.catalog.models import validate_safe_slug

logger = logging.getLogger(__name__)

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


class SkillSpec(BaseModel):
    """Specification of an agent skill matching the SKILL.md format."""

    name: str
    slug: str
    description: str = ""
    content: str = ""
    user_invocable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_path: Path | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        return validate_safe_slug(v, category="skill")

    def to_markdown(self) -> str:
        """Render standard SKILL.md format with YAML frontmatter."""
        frontmatter = {
            "name": self.slug,
            "description": self.description,
            "user-invocable": self.user_invocable,
        }
        yaml_header = yaml.safe_dump(frontmatter, sort_keys=False).strip()
        body = self.content.strip()
        return f"---\n{yaml_header}\n---\n\n{body}\n"


def parse_skill_markdown(content: str, default_slug: str = "") -> SkillSpec:
    """Parse a SKILL.md file with YAML frontmatter into a SkillSpec."""
    match = _FRONTMATTER_PATTERN.match(content.strip())
    if match:
        raw_yaml = match.group(1)
        body = match.group(2).strip()
        data: dict[str, Any] = yaml.safe_load(raw_yaml) or {}
    else:
        data = {}
        body = content.strip()

    slug = data.get("name") or default_slug or "unnamed-skill"
    name = slug.replace("-", " ").title()
    desc = data.get("description") or ""
    invocable = data.get("user-invocable", True)

    reserved_keys = {"name", "description", "user-invocable"}
    extra_metadata = {k: v for k, v in data.items() if k not in reserved_keys}

    return SkillSpec(
        name=name,
        slug=slug,
        description=desc,
        content=body,
        user_invocable=invocable,
        metadata=extra_metadata,
    )


def load_skill_file(path: Path) -> SkillSpec:
    """Load a SkillSpec from a SKILL.md file on disk."""
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Skill file not found: {path}")

    content = path.read_text(encoding="utf-8")
    default_slug = path.parent.name if path.name.lower() == "skill.md" else path.stem
    spec = parse_skill_markdown(content, default_slug=default_slug)
    spec.source_path = path
    return spec


def load_skills_from_dir(directory: Path) -> list[SkillSpec]:
    """Discover all SKILL.md files in a directory hierarchy."""
    directory = Path(directory).resolve()
    if not directory.is_dir():
        return []

    skills: list[SkillSpec] = []
    for skill_file in sorted(directory.rglob("SKILL.md")):
        try:
            skill = load_skill_file(skill_file)
            skills.append(skill)
        except (yaml.YAMLError, OSError, ValueError) as exc:
            logger.debug("Skipping unparseable skill %s: %s", skill_file, exc)

    return skills


class SkillCatalog:
    """Registry and query interface for agent skills."""

    def __init__(self, skills: list[SkillSpec] | None = None) -> None:
        self._skills: dict[str, SkillSpec] = {}
        if skills:
            for skill in skills:
                self.register(skill)

    def register(self, skill: SkillSpec) -> None:
        self._skills[skill.slug] = skill

    def get(self, slug: str) -> SkillSpec | None:
        return self._skills.get(slug)

    def get_or_raise(self, slug: str) -> SkillSpec:
        if slug not in self._skills:
            raise KeyError(f"Skill '{slug}' not found in catalog.")
        return self._skills[slug]

    def list(self) -> list[SkillSpec]:
        return sorted(self._skills.values(), key=lambda s: s.slug)

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, slug: str) -> bool:
        return slug in self._skills

    @classmethod
    def from_directory(cls, directory: Path | str) -> SkillCatalog:
        skills = load_skills_from_dir(Path(directory))
        return cls(skills)

    @classmethod
    def default(cls) -> SkillCatalog:
        candidates = [
            Path(__file__).resolve().parent.parent.parent.parent / "skills",
            Path.cwd() / "skills",
            Path.cwd() / "packages" / "agents" / "skills",
        ]
        for candidate in candidates:
            if candidate.is_dir():
                return cls.from_directory(candidate)
        return cls()
