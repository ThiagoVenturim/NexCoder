from __future__ import annotations

from pathlib import Path

from nexcoder_agents.catalog.loader import load_agent_file
from nexcoder_agents.catalog.skills import load_skills_from_dir


def test_discovery_skills_load_correctly():
    skills_dir = Path("packages/agents/skills")
    skills = {s.slug: s for s in load_skills_from_dir(skills_dir)}

    assert "onboarding-empresa-produto" in skills
    skill_a = skills["onboarding-empresa-produto"]
    assert skill_a.user_invocable is True
    assert "Persona A" in skill_a.content

    assert "onboarding-validacao-ideia" in skills
    skill_b = skills["onboarding-validacao-ideia"]
    assert skill_b.user_invocable is True
    assert "Persona B" in skill_b.content


def test_discovery_agent_loads_correctly():
    agent_path = Path("packages/agents/agents/requirements/discovery-agent.md")
    agent = load_agent_file(agent_path)

    assert agent.slug == "discovery-agent"
    assert agent.sector == "requirements"
    assert agent.tier == "medium"
    assert "detectar_persona" in agent.tools
    assert "iniciar_entrevista" in agent.tools
    assert "responder" in agent.tools
    assert "gerar_perfil" in agent.tools
    assert "onboarding-empresa-produto" in agent.skills
    assert "onboarding-validacao-ideia" in agent.skills
