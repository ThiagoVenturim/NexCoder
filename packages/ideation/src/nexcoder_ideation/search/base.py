from __future__ import annotations

from abc import ABC, abstractmethod

from nexcoder_ideation.models import ResearchSource


class SearchProvider(ABC):
    """Abstract search provider for researching market, competitors, and trends."""

    name: str = "base"

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[ResearchSource]:
        """Perform search and return list of cited research sources."""
        raise NotImplementedError
