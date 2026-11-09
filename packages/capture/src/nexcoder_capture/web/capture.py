"""Web capture engine supporting Playwright and offline fixture captures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from faccoder_capture.models import (
    WebCaptureConfig,
    WebCaptureResult,
)
from faccoder_capture.web.accessibility import AccessibilityExtractor
from faccoder_capture.web.har import HarRecorder
from faccoder_capture.web.policy import PolicyEnforcer
from faccoder_capture.web.selectors import SelectorExtractor
from faccoder_capture.web.session import SessionManager


class WebCaptureEngine:
    """Unified web capture engine with Playwright and offline fixture support."""

    def __init__(self, config: WebCaptureConfig | None = None) -> None:
        self.config = config or WebCaptureConfig()
        self.policy = PolicyEnforcer(self.config)
        self.selectors_extractor = SelectorExtractor()
        self.a11y_extractor = AccessibilityExtractor()
        self.session_manager = SessionManager(self.config, self.policy)

    def capture_html(
        self,
        html: str,
        base_url: str = "http://localhost/fixture.html",
        title: str = "Offline Fixture",
        network_entries: list[dict[str, Any]] | None = None,
    ) -> WebCaptureResult:
        """Capture from an in-memory HTML string or local fixture without network access."""
        self.policy.validate_url(base_url)
        self.policy.assert_no_captcha(html)

        dom = html if self.config.capture_dom else ""
        a11y = self.a11y_extractor.from_html(html) if self.config.capture_accessibility else None
        selectors = self.selectors_extractor.extract_from_html(html) if self.config.extract_selectors else []

        har_recorder = HarRecorder()
        if self.config.capture_har:
            har_recorder.add_entry(
                url=base_url,
                method="GET",
                status=200,
                mime_type="text/html",
                size_bytes=len(html.encode("utf-8")),
            )
            if network_entries:
                for entry in network_entries:
                    har_recorder.add_entry(**entry)

        screenshot_bytes: bytes | None = None
        if self.config.capture_screenshot:
            # Deterministic offline 1x1 PNG bytes for fixture testing
            screenshot_bytes = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )

        return WebCaptureResult(
            url=base_url,
            title=title,
            dom=dom,
            accessibility_tree=a11y,
            screenshot_bytes=screenshot_bytes,
            har_entries=har_recorder.entries,
            selectors=selectors,
            metadata={"mode": "offline_html", "read_only": self.config.read_only},
        )

    def capture_file(self, file_path: str | Path) -> WebCaptureResult:
        """Capture from a local HTML file fixture."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Fixture file not found: {file_path}")

        html = path.read_text(encoding="utf-8")
        url = path.as_uri()
        return self.capture_html(html=html, base_url=url, title=path.stem)

    async def capture_page_async(self, page: Any, url: str | None = None) -> WebCaptureResult:
        """Capture from an active Playwright async Page object."""
        target_url = url or page.url
        self.policy.validate_url(target_url)

        title = await page.title()
        dom = await page.content() if self.config.capture_dom else ""

        self.policy.assert_no_captcha(dom)

        a11y_tree = None
        if self.config.capture_accessibility:
            snapshot = await page.accessibility.snapshot()
            a11y_tree = self.a11y_extractor.from_playwright_snapshot(snapshot)

        selectors = self.selectors_extractor.extract_from_html(dom) if self.config.extract_selectors else []

        screenshot_bytes = None
        if self.config.capture_screenshot:
            screenshot_bytes = await page.screenshot(type="png", full_page=True)

        return WebCaptureResult(
            url=target_url,
            title=title,
            dom=dom,
            accessibility_tree=a11y_tree,
            screenshot_bytes=screenshot_bytes,
            selectors=selectors,
            metadata={"mode": "playwright_async", "read_only": self.config.read_only},
        )
