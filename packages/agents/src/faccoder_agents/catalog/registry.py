from __future__ import annotations

from pathlib import Path

from faccoder_agents.catalog.loader import load_agents_from_dir
from faccoder_agents.catalog.models import AgentSpec


class AgentCatalog:
    """Registry and query interface for agent persona definitions."""

    def __init__(self, agents: list[AgentSpec] | None = None) -> None:
        self._agents: dict[str, AgentSpec] = {}
        if agents:
            for agent in agents:
                self.register(agent)

    def register(self, agent: AgentSpec) -> None:
        """Register or update an agent specification."""
        self._agents[agent.slug] = agent

    def get(self, slug: str) -> AgentSpec | None:
        """Retrieve an agent specification by slug."""
        return self._agents.get(slug)

    def get_or_raise(self, slug: str) -> AgentSpec:
        """Retrieve an agent specification or raise KeyError."""
        if slug not in self._agents:
            raise KeyError(f"Agent '{slug}' not found in catalog.")
        return self._agents[slug]

    def list(
        self,
        sector: str | None = None,
        tier: str | None = None,
        skill: str | None = None,
        tool: str | None = None,
    ) -> list[AgentSpec]:
        """List registered agents with optional filtering."""
        results = list(self._agents.values())
        if sector:
            results = [a for a in results if a.sector == sector]
        if tier:
            results = [a for a in results if a.tier == tier]
        if skill:
            results = [a for a in results if skill in a.skills]
        if tool:
            results = [a for a in results if tool in a.tools]
        return sorted(results, key=lambda a: (a.sector, a.slug))

    def list_sectors(self) -> list[str]:
        """Return sorted unique list of all sectors with registered agents."""
        return sorted({a.sector for a in self._agents.values()})

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, slug: str) -> bool:
        return slug in self._agents

    @classmethod
    def from_directory(cls, directory: Path | str) -> AgentCatalog:
        """Create a catalog by scanning a directory recursively for markdown specs."""
        agents = load_agents_from_dir(Path(directory))
        return cls(agents)

    @classmethod
    def default(cls) -> AgentCatalog:
        """Attempt to load default catalog from known standard locations."""
        candidates = [
            Path(__file__).resolve().parent.parent.parent.parent / "agents",  # packages/agents/agents
            Path(__file__).resolve().parent / "seed_agents",
            Path.cwd() / "agents",
            Path.cwd() / "packages" / "agents" / "agents",
        ]
        for candidate in candidates:
            if candidate.is_dir():
                return cls.from_directory(candidate)
        return cls()
