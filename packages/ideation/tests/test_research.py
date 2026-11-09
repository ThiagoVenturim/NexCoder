from __future__ import annotations

import json

from nexcoder_core.llm.fake import FakeChatModel
from nexcoder_ideation.models import StructuredIdea, ValueHypothesis
from nexcoder_ideation.research.specialists import (
    CompetitorScout,
    MarketResearcher,
    PricingResearcher,
)
from nexcoder_ideation.research.squad import ResearchSquad
from nexcoder_ideation.search.providers import MockSearchProvider


def _sample_idea() -> StructuredIdea:
    return StructuredIdea(
        title="Autonomous API Observability Guard",
        summary="Deep tracing and anomaly detection for microservice APIs.",
        problem="Microservice failures take too long to localize and resolve.",
        target_audience=[],
        value_hypothesis=ValueHypothesis(
            problem_statement="High MTTR in distributed systems",
            proposed_solution="Agentic root cause analysis",
            key_benefit="10x faster incident resolution",
        ),
        domain_tags=["cloud", "observability", "api"],
    )


def test_market_researcher_offline() -> None:
    researcher = MarketResearcher(search_provider=MockSearchProvider())
    idea = _sample_idea()
    data = researcher.research(idea)

    assert "$14.2 Billion" in data.tam_estimate
    assert data.cagr_percentage is not None
    assert data.cagr_percentage > 10.0
    assert len(data.market_trends) >= 2
    assert len(data.sources) > 0
    assert data.sources[0].provider == "mock"


def test_competitor_scout_offline() -> None:
    scout = CompetitorScout(search_provider=MockSearchProvider())
    idea = _sample_idea()
    data = scout.research(idea)

    assert len(data.direct_competitors) >= 2
    assert len(data.indirect_competitors) >= 1
    assert len(data.market_leaders) >= 1
    assert data.direct_competitors[0].pricing_model != ""


def test_pricing_researcher_with_fake_model() -> None:
    custom_pricing = {
        "recommended_model": "usage_based",
        "pricing_tiers": [
            {
                "name": "Developer Free",
                "price_point": "$0",
                "billing_period": "monthly",
                "target_persona": "Hobbyists",
                "features_included": ["Up to 10k events/mo"],
            },
            {
                "name": "Enterprise Scale",
                "price_point": "$499/mo",
                "billing_period": "monthly",
                "target_persona": "Production Teams",
                "features_included": ["Unlimited events", "SLA 99.9%"],
            },
        ],
        "margin_considerations": "High margins due to client-side sampling.",
    }
    fake_model = FakeChatModel(responses=[json.dumps(custom_pricing)])
    researcher = PricingResearcher(search_provider=MockSearchProvider(), model=fake_model)
    data = researcher.research(_sample_idea())

    assert data.recommended_model == "usage_based"
    assert len(data.pricing_tiers) == 2
    assert data.pricing_tiers[1].name == "Enterprise Scale"
    assert data.pricing_tiers[1].price_point == "$499/mo"


def test_research_squad_end_to_end() -> None:
    squad = ResearchSquad(search_provider=MockSearchProvider())
    idea = _sample_idea()
    report = squad.run(idea)

    assert report.idea_id == idea.id
    assert report.market.tam_estimate != ""
    assert len(report.competitors.direct_competitors) > 0
    assert len(report.differentiation.differentiation_matrix) > 0
    assert len(report.gaps.unmet_needs) > 0
    assert len(report.user_voice.personas) >= 2
    assert len(report.pricing.pricing_tiers) >= 2
    assert len(report.legal_privacy.risks) >= 2
    assert len(report.all_sources) >= 5

    # Verify all sources have valid titles and URLs
    for src in report.all_sources:
        assert src.title != ""
        assert src.url.startswith("https://")
