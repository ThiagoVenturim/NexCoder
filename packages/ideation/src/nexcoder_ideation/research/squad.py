from __future__ import annotations

import logging
from typing import Any

from nexcoder_ideation.models import (
    ResearchSource,
    ResearchSquadReport,
    StructuredIdea,
)
from nexcoder_ideation.research.specialists import (
    CompetitorScout,
    DifferentiatorAnalyst,
    GapHunter,
    LegalPrivacyResearcher,
    MarketResearcher,
    PricingResearcher,
    UserVoiceResearcher,
)
from nexcoder_ideation.search.base import SearchProvider
from nexcoder_ideation.search.providers import MockSearchProvider

logger = logging.getLogger(__name__)


class ResearchSquad:
    """Orchestrator for the multi-agent research squad executing comprehensive idea diligence."""

    def __init__(
        self,
        search_provider: SearchProvider | None = None,
        model: Any = None,
    ) -> None:
        self.search_provider = search_provider or MockSearchProvider()
        self.model = model

        # Instantiate specialists
        self.market_researcher = MarketResearcher(search_provider=self.search_provider, model=self.model)
        self.competitor_scout = CompetitorScout(search_provider=self.search_provider, model=self.model)
        self.differentiator_analyst = DifferentiatorAnalyst(search_provider=self.search_provider, model=self.model)
        self.gap_hunter = GapHunter(search_provider=self.search_provider, model=self.model)
        self.user_voice_researcher = UserVoiceResearcher(search_provider=self.search_provider, model=self.model)
        self.pricing_researcher = PricingResearcher(search_provider=self.search_provider, model=self.model)
        self.legal_privacy_researcher = LegalPrivacyResearcher(search_provider=self.search_provider, model=self.model)

    def run(self, idea: StructuredIdea) -> ResearchSquadReport:
        """Run all squad specialists on the structured idea and consolidate their findings."""
        logger.info("Starting ResearchSquad diligence for idea: %s (%s)", idea.title, idea.id)

        market_data = self.market_researcher.research(idea)
        competitors_data = self.competitor_scout.research(idea)
        diff_data = self.differentiator_analyst.research(idea)
        gap_data = self.gap_hunter.research(idea)
        user_voice_data = self.user_voice_researcher.research(idea)
        pricing_data = self.pricing_researcher.research(idea)
        legal_data = self.legal_privacy_researcher.research(idea)

        # Consolidate and deduplicate all sources
        seen_urls: set[str] = set()
        deduped_sources: list[ResearchSource] = []

        all_collected_sources = (
            market_data.sources
            + competitors_data.sources
            + diff_data.sources
            + gap_data.sources
            + user_voice_data.sources
            + pricing_data.sources
            + legal_data.sources
        )

        for src in all_collected_sources:
            if src.url and src.url not in seen_urls:
                seen_urls.add(src.url)
                deduped_sources.append(src)
            elif not src.url:
                deduped_sources.append(src)

        report = ResearchSquadReport(
            idea_id=idea.id,
            market=market_data,
            competitors=competitors_data,
            differentiation=diff_data,
            gaps=gap_data,
            user_voice=user_voice_data,
            pricing=pricing_data,
            legal_privacy=legal_data,
            all_sources=deduped_sources,
        )

        logger.info(
            "ResearchSquad completed for idea %s: %d total unique cited sources.",
            idea.id,
            len(deduped_sources),
        )
        return report
