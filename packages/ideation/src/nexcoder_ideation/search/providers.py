from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

from nexcoder_ideation.models import ResearchSource
from nexcoder_ideation.search.base import SearchProvider

logger = logging.getLogger(__name__)


class MockSearchProvider(SearchProvider):
    """Deterministic offline search provider for testing and airgapped runs."""

    name: str = "mock"

    def __init__(self, predefined_results: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.predefined_results = predefined_results or {}

    def search(self, query: str, max_results: int = 5) -> list[ResearchSource]:
        query_lower = query.lower()

        # Check if query matches any predefined pattern
        for key, results in self.predefined_results.items():
            if key.lower() in query_lower:
                return [ResearchSource(**item, provider=self.name) for item in results[:max_results]]

        # Generate synthetic realistic sources based on topic keywords
        clean_slug = re.sub(r"[^a-z0-9]+", "-", query_lower).strip("-")[:30] or "market-study"
        synthetic_sources: list[ResearchSource] = []

        topics = [
            ("Industry Overview & Trends", f"https://reports.example.org/research/{clean_slug}"),
            ("Competitive Benchmark Report", f"https://benchmarks.example.org/analysis/{clean_slug}"),
            ("Customer Reviews and Pain Points", f"https://feedback.example.net/discussions/{clean_slug}"),
            ("Technical Feasibility & Architecture", f"https://specs.example.com/whitepapers/{clean_slug}"),
            ("Regulatory & Compliance Brief", f"https://compliance.example.org/briefs/{clean_slug}"),
        ]

        for i, (title_suffix, url) in enumerate(topics[:max_results]):
            synthetic_sources.append(
                ResearchSource(
                    title=f"{query.capitalize()} - {title_suffix}",
                    url=url,
                    snippet=(
                        f"Evidence and empirical analysis regarding {query}. "
                        f"Key findings identify growth opportunities, competitive moats, "
                        f"and operational feasibility factors (sample size N={100 * (i + 1)})."
                    ),
                    provider=self.name,
                    relevance_score=max(0.6, 1.0 - (i * 0.08)),
                )
            )

        return synthetic_sources


class DuckDuckGoSearchProvider(SearchProvider):
    """No-key web search provider using public DuckDuckGo endpoints with mock fallback."""

    name: str = "duckduckgo"

    def __init__(self, timeout: float = 8.0, fallback: SearchProvider | None = None) -> None:
        self.timeout = timeout
        self.fallback = fallback or MockSearchProvider()

    def search(self, query: str, max_results: int = 5) -> list[ResearchSource]:
        try:
            # DuckDuckGo HTML or Instant Answer API
            url = "https://api.duckduckgo.com/"
            params = {"q": query, "format": "json", "no_html": "1", "no_redirect": "1"}
            headers = {"User-Agent": "nexcoder-ideation/0.1.0 (research-bot; open-source)"}

            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    results: list[ResearchSource] = []

                    # Abstract
                    if data.get("AbstractText") and data.get("AbstractURL"):
                        results.append(
                            ResearchSource(
                                title=data.get("Heading") or query,
                                url=data.get("AbstractURL"),
                                snippet=data.get("AbstractText"),
                                provider=self.name,
                                relevance_score=0.95,
                            )
                        )

                    # Related topics
                    for item in data.get("RelatedTopics", []):
                        if len(results) >= max_results:
                            break
                        if isinstance(item, dict) and item.get("FirstURL") and item.get("Text"):
                            results.append(
                                ResearchSource(
                                    title=item.get("Text")[:60] + "...",
                                    url=item.get("FirstURL"),
                                    snippet=item.get("Text"),
                                    provider=self.name,
                                    relevance_score=0.85,
                                )
                            )

                    if results:
                        return results
        except Exception as exc:
            logger.debug("DuckDuckGo search call failed or offline, falling back: %s", exc)

        return self.fallback.search(query, max_results=max_results)


class TavilySearchProvider(SearchProvider):
    """Tavily web search API provider with mock fallback."""

    name: str = "tavily"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 10.0,
        fallback: SearchProvider | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("TAVILY_API_KEY", "")
        self.timeout = timeout
        self.fallback = fallback or MockSearchProvider()

    def search(self, query: str, max_results: int = 5) -> list[ResearchSource]:
        if not self.api_key:
            return self.fallback.search(query, max_results=max_results)

        try:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": self.api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
            }
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    results: list[ResearchSource] = []
                    for item in data.get("results", []):
                        results.append(
                            ResearchSource(
                                title=item.get("title", query),
                                url=item.get("url", ""),
                                snippet=item.get("content", ""),
                                provider=self.name,
                                relevance_score=float(item.get("score", 0.9)),
                            )
                        )
                    if results:
                        return results
        except Exception as exc:
            logger.debug("Tavily search API failed, falling back: %s", exc)

        return self.fallback.search(query, max_results=max_results)


class SerpApiSearchProvider(SearchProvider):
    """SerpApi Google search provider with mock fallback."""

    name: str = "serpapi"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 10.0,
        fallback: SearchProvider | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("SERPAPI_API_KEY", "")
        self.timeout = timeout
        self.fallback = fallback or MockSearchProvider()

    def search(self, query: str, max_results: int = 5) -> list[ResearchSource]:
        if not self.api_key:
            return self.fallback.search(query, max_results=max_results)

        try:
            url = "https://serpapi.com/search"
            params = {
                "api_key": self.api_key,
                "q": query,
                "engine": "google",
                "num": max_results,
            }
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    results: list[ResearchSource] = []
                    for item in data.get("organic_results", [])[:max_results]:
                        results.append(
                            ResearchSource(
                                title=item.get("title", query),
                                url=item.get("link", ""),
                                snippet=item.get("snippet", ""),
                                provider=self.name,
                                relevance_score=0.9,
                            )
                        )
                    if results:
                        return results
        except Exception as exc:
            logger.debug("SerpApi search failed, falling back: %s", exc)

        return self.fallback.search(query, max_results=max_results)


class BraveSearchProvider(SearchProvider):
    """Brave Web Search API provider with mock fallback."""

    name: str = "brave"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 10.0,
        fallback: SearchProvider | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("BRAVE_API_KEY", "")
        self.timeout = timeout
        self.fallback = fallback or MockSearchProvider()

    def search(self, query: str, max_results: int = 5) -> list[ResearchSource]:
        if not self.api_key:
            return self.fallback.search(query, max_results=max_results)

        try:
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {"X-Subscription-Token": self.api_key, "Accept": "application/json"}
            params = {"q": query, "count": max_results}
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    results: list[ResearchSource] = []
                    for item in data.get("web", {}).get("results", [])[:max_results]:
                        results.append(
                            ResearchSource(
                                title=item.get("title", query),
                                url=item.get("url", ""),
                                snippet=item.get("description", ""),
                                provider=self.name,
                                relevance_score=0.9,
                            )
                        )
                    if results:
                        return results
        except Exception as exc:
            logger.debug("Brave search failed, falling back: %s", exc)

        return self.fallback.search(query, max_results=max_results)


def get_search_provider(
    preferred_name: str | None = None,
    allow_network: bool = True,
) -> SearchProvider:
    """Factory selecting the appropriate search provider based on configuration and available keys."""
    mock = MockSearchProvider()
    if not allow_network or os.getenv("NEXCODER_PRESET") == "offline":
        return mock

    name = (preferred_name or os.getenv("SEARCH_PROVIDER", "duckduckgo")).lower()
    if name == "mock":
        return mock
    if name == "tavily" and os.getenv("TAVILY_API_KEY"):
        return TavilySearchProvider(fallback=mock)
    if name == "serpapi" and os.getenv("SERPAPI_API_KEY"):
        return SerpApiSearchProvider(fallback=mock)
    if name == "brave" and os.getenv("BRAVE_API_KEY"):
        return BraveSearchProvider(fallback=mock)
    if name == "duckduckgo":
        return DuckDuckGoSearchProvider(fallback=mock)

    return mock
