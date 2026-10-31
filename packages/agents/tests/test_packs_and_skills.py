from __future__ import annotations

from pathlib import Path

from faccoder_agents.catalog import AgentCatalog, SkillCatalog


def test_stack_packs_loaded() -> None:
    catalog = AgentCatalog.default()
    assert len(catalog) >= 30

    expected_stacks = [
        "python-specialist",
        "java-specialist",
        "csharp-dotnet-specialist",
        "go-specialist",
        "node-ts-specialist",
        "c-cpp-specialist",
        "cobol-specialist",
        "delphi-specialist",
        "outsystems-specialist",
    ]

    for slug in expected_stacks:
        agent = catalog.get(slug)
        assert agent is not None, f"Stack pack '{slug}' missing from catalog"
        assert agent.sector == "stacks"
        assert agent.description
        assert agent.skills
        assert agent.prompt


def test_regulation_packs_loaded() -> None:
    catalog = AgentCatalog.default()

    lgpd = catalog.get("privacy-compliance-specialist")
    assert lgpd is not None
    assert lgpd.sector == "regulations"
    assert "lgpd-consent-audit" in lgpd.skills

    fiscal = catalog.get("brazilian-fiscal-specialist")
    assert fiscal is not None
    assert fiscal.sector == "regulations"
    assert "brazilian-fiscal-validation" in fiscal.skills


def test_skill_catalog_default_discovery() -> None:
    skills = SkillCatalog.default()
    assert len(skills) >= 7

    expected_skills = [
        "delphi-crash-guard",
        "delphi-encoding-fixer",
        "delphi-dfm-repair",
        "outsystems-performance-guard",
        "python-async-patterns",
        "lgpd-consent-audit",
        "brazilian-fiscal-validation",
    ]

    for slug in expected_skills:
        skill = skills.get(slug)
        assert skill is not None, f"Skill '{slug}' missing from skill catalog"
        assert skill.description
        assert skill.content
        rendered = skill.to_markdown()
        assert f"name: {slug}" in rendered
        assert "---" in rendered


def test_skill_catalog_load_dir(tmp_path: Path) -> None:
    skill_dir = tmp_path / "custom-skill"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: custom-skill\ndescription: Custom skill description.\n---\n\n# Custom Skill\nInstructions here.",
        encoding="utf-8",
    )

    cat = SkillCatalog.from_directory(tmp_path)
    assert len(cat) == 1
    assert "custom-skill" in cat
    assert cat.get("custom-skill").description == "Custom skill description."
