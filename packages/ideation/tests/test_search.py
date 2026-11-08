from __future__ import annotations

from faccoder_ideation.search.providers import (
    DuckDuckGoSearchProvider,
    MockSearchProvider,
    get_search_provider,
)


def test_mock_search_provider_deterministic() -> None:
    provider = MockSearchProvider()
    results = provider.search("developer productivity tools", max_results=3)

    assert len(results) == 3
    for res in results:
        assert res.url.startswith("https://")
        assert res.provider == "mock"
        assert res.relevance_score > 0.0
        assert "developer productivity tools" in res.title.lower()


def test_mock_search_predefined_results() -> None:
    custom_results = {
        "pricing": [
            {
                "title": "SaaS Pricing Index 2026",
                "url": "https://pricing.example.org/report",
                "snippet": "Average B2B dev tool seats cost $29/month.",
            }
        ]
    }
    provider = MockSearchProvider(predefined_results=custom_results)
    results = provider.search("SaaS pricing research", max_results=5)

    assert len(results) == 1
    assert results[0].title == "SaaS Pricing Index 2026"
    assert results[0].url == "https://pricing.example.org/report"


def test_duckduckgo_fallback_to_mock() -> None:
    # When offline or failing, DuckDuckGo provider falls back to mock
    mock_fallback = MockSearchProvider()
    ddg = DuckDuckGoSearchProvider(timeout=0.01, fallback=mock_fallback)
    results = ddg.search("cloud security posture management", max_results=2)

    assert len(results) == 2
    assert results[0].provider == "mock"


def test_get_search_provider_offline() -> None:
    provider = get_search_provider(preferred_name="tavily", allow_network=False)
    assert isinstance(provider, MockSearchProvider)
    assert provider.name == "mock"
