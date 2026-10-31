from __future__ import annotations

from pathlib import Path

import pytest
from faccoder_agents.catalog import (
    AgentCatalog,
    AgentSector,
    AgentSpec,
    parse_agent_markdown,
)


def test_parse_agent_markdown_basic() -> None:
    raw = """---
name: Database Specialist
slug: db-specialist
sector: engineering
tier: large
description: Expert in database schemas and query plans.
tools:
  - query_runner
skills:
  - query-optimization
---

You are a database specialist.
Focus on indexing and transactions.
"""
    spec = parse_agent_markdown(raw)
    assert spec.name == "Database Specialist"
    assert spec.slug == "db-specialist"
    assert spec.sector == "engineering"
    assert spec.tier == "large"
    assert spec.description == "Expert in database schemas and query plans."
    assert spec.tools == ["query_runner"]
    assert spec.skills == ["query-optimization"]
    assert "You are a database specialist." in spec.prompt


def test_render_prompt_interpolation() -> None:
    spec = AgentSpec(
        name="Reviewer",
        slug="reviewer",
        sector="qa",
        tier="medium",
        prompt="Review pull request #{pr_id} on repository {repo_name}.",
    )
    rendered = spec.render_prompt(pr_id=42, repo_name="faccoder")
    assert rendered == "Review pull request #42 on repository faccoder."


def test_seed_catalog_covers_all_ten_sectors() -> None:
    repo_agents_dir = Path(__file__).resolve().parent.parent / "agents"
    assert repo_agents_dir.is_dir(), f"Expected agents dir at {repo_agents_dir}"

    catalog = AgentCatalog.from_directory(repo_agents_dir)
    assert len(catalog) >= 15

    registered_sectors = set(catalog.list_sectors())
    expected_sectors = set(AgentSector.ALL)

    missing = expected_sectors - registered_sectors
    assert not missing, f"Missing sectors in seed catalog: {missing}"

    # Verify key agents exist
    assert "lead-architect" in catalog
    assert "requirements-analyst" in catalog
    assert "security-auditor" in catalog
    assert "qa-engineer" in catalog
    assert "incident-responder" in catalog


def test_catalog_filtering() -> None:
    repo_agents_dir = Path(__file__).resolve().parent.parent / "agents"
    catalog = AgentCatalog.from_directory(repo_agents_dir)

    eng_agents = catalog.list(sector="engineering")
    assert len(eng_agents) >= 2
    for agent in eng_agents:
        assert agent.sector == "engineering"

    large_agents = catalog.list(tier="large")
    assert len(large_agents) >= 1
    for agent in large_agents:
        assert agent.tier == "large"


def test_get_or_raise() -> None:
    catalog = AgentCatalog()
    with pytest.raises(KeyError):
        catalog.get_or_raise("non-existent-agent")
