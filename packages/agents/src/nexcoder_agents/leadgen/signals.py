"""Passive observation of a public business web site.

The inspector reads robots.txt and the published home page with plain GET requests,
the same way a visitor's browser would. It never probes other paths, ports or
parameters, never sends crafted payloads and never runs a scanner. A real security
assessment of a third-party site is out of scope here: it needs the target to pass the
TargetAuthorizationGate from nexcoder-control (see USAGE_POLICY.md) and then runs in
nexcoder-security, not in this module.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlparse, urlunparse
from urllib.robotparser import RobotFileParser

from pydantic import BaseModel

from nexcoder_agents.leadgen.models import LeadGenPolicyError, PassiveSignal, SignalCode, SiteObservation

USER_AGENT = "NexCoder-LeadGen/0.1 (passive public page check; respects robots.txt)"
MAX_BODY_CHARS = 2_000_000


class FetchResult(BaseModel):
    """Outcome of one GET request."""

    url: str
    status_code: int | None = None
    final_url: str | None = None
    text: str = ""
    error: str | None = None


class PageFetcher(Protocol):
    """Performs one plain GET request. Implementations must not add probes or payloads."""

    def get(self, url: str) -> FetchResult: ...


class HttpxPageFetcher:
    """Default fetcher: one GET per call, short timeout, identified user agent, few redirects."""

    def __init__(self, timeout_seconds: float = 10.0, client: Any = None) -> None:
        import httpx

        self._client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            max_redirects=3,
            headers={"User-Agent": USER_AGENT},
        )

    def get(self, url: str) -> FetchResult:
        try:
            resp = self._client.get(url)
        except Exception as exc:  # network errors mean the site is not reachable
            return FetchResult(url=url, error=type(exc).__name__)
        return FetchResult(
            url=url,
            status_code=resp.status_code,
            final_url=str(resp.url),
            text=resp.text[:MAX_BODY_CHARS],
        )


_OUTDATED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("font tag", re.compile(r"<font[\s>]", re.IGNORECASE)),
    ("marquee or blink tag", re.compile(r"<(?:marquee|blink)[\s>]", re.IGNORECASE)),
    ("frameset layout", re.compile(r"<frameset[\s>]", re.IGNORECASE)),
    ("center tag", re.compile(r"<center[\s>]", re.IGNORECASE)),
    ("table based layout", re.compile(r"<table[^>]*(?:bgcolor|cellpadding)=", re.IGNORECASE)),
    ("jQuery 1.x", re.compile(r"jquery[-.]?1\.\d+(?:\.\d+)?(?:\.min)?\.js", re.IGNORECASE)),
)
_FLASH = re.compile(r"\.swf\b|application/x-shockwave-flash", re.IGNORECASE)
_VIEWPORT = re.compile(r"<meta[^>]+name=[\"']?viewport", re.IGNORECASE)
_CONTACT = re.compile(
    r"mailto:|tel:|wa\.me/|api\.whatsapp\.com|<form[\s>]|\bcontato\b|\bcontact\b|fale conosco",
    re.IGNORECASE,
)
_COPYRIGHT_YEAR = re.compile(r"(?:&copy;|\u00a9|copyright)\s*(?:\d{4}\s*[-/]\s*)?((?:19|20)\d{2})", re.IGNORECASE)


def analyze_html(html: str, *, current_year: int | None = None) -> list[PassiveSignal]:
    """Derive design and contact signals from the home page markup."""
    year = current_year or datetime.now(UTC).year
    signals: list[PassiveSignal] = []

    hints = [label for label, pattern in _OUTDATED_PATTERNS if pattern.search(html)]
    years = [int(y) for y in _COPYRIGHT_YEAR.findall(html)]
    if years and max(years) <= year - 6:
        hints.append(f"copyright notice last updated in {max(years)}")
    if _FLASH.search(html):
        hints.append("Flash content")
    if _FLASH.search(html) or len(hints) >= 2:
        signals.append(PassiveSignal(code=SignalCode.OUTDATED_DESIGN, detail="; ".join(hints), weight=2))

    if not _VIEWPORT.search(html):
        signals.append(
            PassiveSignal(
                code=SignalCode.NOT_RESPONSIVE,
                detail="No viewport meta tag; the page likely does not adapt to phones",
                weight=2,
            )
        )
    if not _CONTACT.search(html):
        signals.append(
            PassiveSignal(
                code=SignalCode.NO_CONTACT_INFO,
                detail="No e-mail link, phone link, contact form or contact section on the home page",
                weight=2,
            )
        )
    return signals


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


class PassiveSiteInspector:
    """Looks at robots.txt and the published home page only. Never scans."""

    def __init__(
        self,
        fetcher: PageFetcher | None = None,
        *,
        user_agent: str = USER_AGENT,
        min_interval_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        current_year: int | None = None,
    ) -> None:
        self._fetcher = fetcher
        self.user_agent = user_agent
        self.min_interval_seconds = min_interval_seconds
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: dict[str, float] = {}
        self._current_year = current_year

    @property
    def fetcher(self) -> PageFetcher:
        if self._fetcher is None:
            self._fetcher = HttpxPageFetcher()
        return self._fetcher

    def _polite_get(self, url: str, allowed: set[str], requests_made: list[str]) -> FetchResult:
        if url not in allowed:
            raise LeadGenPolicyError(f"Passive inspection may only request the home page and robots.txt, not '{url}'")
        host = urlparse(url).netloc.lower()
        last = self._last_request_at.get(host)
        if last is not None:
            wait = self.min_interval_seconds - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        requests_made.append(f"GET {url}")
        result = self.fetcher.get(url)
        self._last_request_at[host] = self._clock()
        return result

    def inspect(self, website: str | None) -> SiteObservation:
        """Observe a public site passively and return the signals found."""
        if not website or not website.strip():
            return SiteObservation(
                url=None,
                signals=[PassiveSignal(code=SignalCode.NO_WEBSITE, detail="No website listed", weight=5)],
            )

        url = website.strip()
        if "://" not in url:
            url = f"http://{url}"
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise LeadGenPolicyError(f"Unsupported website address: {website}")
        if parsed.query or parsed.fragment:
            # Only the published page itself; no parameters are ever sent.
            url = urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", ""))
        elif not parsed.path:
            url = f"{url}/"

        robots_url = f"{_origin(url)}/robots.txt"
        allowed = {robots_url, url}
        requests_made: list[str] = []
        signals: list[PassiveSignal] = []

        robots = self._polite_get(robots_url, allowed, requests_made)
        if robots.error is not None:
            signals.append(
                PassiveSignal(code=SignalCode.SITE_OFFLINE, detail=f"Site not reachable ({robots.error})", weight=4)
            )
            return SiteObservation(url=url, signals=signals, requests_made=requests_made)

        parser = RobotFileParser()
        status = robots.status_code or 0
        if 200 <= status < 300:
            parser.parse(robots.text.splitlines())
        elif 400 <= status < 500:
            parser.parse([])  # no robots.txt: crawling allowed (RFC 9309)
        else:
            parser.disallow_all = True  # server error: assume disallowed (RFC 9309)

        if not parser.can_fetch(self.user_agent, url):
            if parsed.scheme == "http":
                signals.append(
                    PassiveSignal(code=SignalCode.NO_HTTPS, detail="Published address uses plain HTTP", weight=3)
                )
            signals.append(
                PassiveSignal(
                    code=SignalCode.ROBOTS_DISALLOWED,
                    detail="robots.txt does not allow automated access to the home page; page not read",
                    weight=0,
                )
            )
            return SiteObservation(url=url, signals=signals, requests_made=requests_made)

        page = self._polite_get(url, allowed, requests_made)
        if page.error is not None or (page.status_code or 0) >= 500:
            reason = page.error or f"HTTP {page.status_code}"
            signals.append(
                PassiveSignal(code=SignalCode.SITE_OFFLINE, detail=f"Site not reachable ({reason})", weight=4)
            )
            return SiteObservation(
                url=url, status_code=page.status_code, signals=signals, requests_made=requests_made
            )

        final_url = page.final_url or url
        if urlparse(final_url).scheme != "https":
            signals.append(
                PassiveSignal(code=SignalCode.NO_HTTPS, detail="Home page is served without HTTPS", weight=3)
            )
        if (page.status_code or 0) >= 400:
            signals.append(
                PassiveSignal(
                    code=SignalCode.SITE_OFFLINE, detail=f"Home page answers HTTP {page.status_code}", weight=4
                )
            )
        else:
            signals.extend(analyze_html(page.text, current_year=self._current_year))

        return SiteObservation(
            url=url,
            reachable=(page.status_code or 0) < 400,
            status_code=page.status_code,
            final_url=final_url,
            signals=signals,
            requests_made=requests_made,
        )


def require_authorized_security_target(
    gate: Any,
    target: str,
    *,
    owned_target: bool = False,
    authorized_by: str | None = None,
    approval_token: str | None = None,
    authorization_document: Any = None,
) -> Any:
    """Gate for any real security assessment of a prospect site.

    Lead-gen never runs it. This only checks the TargetAuthorizationGate and returns the
    authorization record so the operator can run a campaign in nexcoder-security. An
    unmarked third-party site raises TargetNotAuthorizedError and the denial is audited.
    """
    if gate is None:
        raise LeadGenPolicyError("A TargetAuthorizationGate is required before any security assessment")
    return gate.verify_target(
        target,
        mode="security_assessment",
        owned_target=owned_target,
        authorized_by=authorized_by,
        approval_token=approval_token,
        authorization_document=authorization_document,
    )
