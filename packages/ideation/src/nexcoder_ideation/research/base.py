from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from faccoder_ideation.models import ResearchSource, StructuredIdea
from faccoder_ideation.search.base import SearchProvider
from faccoder_ideation.search.providers import MockSearchProvider


class BaseResearcher(ABC):
    """Abstract base class for all research squad specialist agents."""

    name: str = "base-researcher"
    role: str = "researcher"

    def __init__(
        self,
        search_provider: SearchProvider | None = None,
        model: Any = None,
    ) -> None:
        self.search_provider = search_provider or MockSearchProvider()
        self.model = model

    def search(self, query: str, max_results: int = 5) -> list[ResearchSource]:
        """Perform search query through the configured search provider."""
        return self.search_provider.search(query, max_results=max_results)

    @abstractmethod
    def research(self, idea: StructuredIdea) -> Any:
        """Execute domain-specific research for the given structured idea."""
        raise NotImplementedError
