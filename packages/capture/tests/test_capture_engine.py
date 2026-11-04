"""Unit tests for faccoder_capture.web.capture."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from faccoder_capture.models import (
    CaptchaDetectedError,
    DomainNotAllowedError,
    WebCaptureConfig,
)
from faccoder_capture.web.capture import WebCaptureEngine

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Fixture Page</title></head>
<body>
  <header>
    <h1>Welcome to App</h1>
  </header>
  <main>
    <form id="login-form">
      <input type="text" data-testid="username-input" placeholder="Username" />
      <input type="password" data-testid="password-input" placeholder="Password" />
      <button type="submit" id="submit-btn">Login</button>
    </form>
    <a href="/help" aria-label="Help and Support">Help</a>
  </main>
</body>
</html>
"""


def test_capture_html_basic() -> None:
    engine = WebCaptureEngine()
    result = engine.capture_html(html=SAMPLE_HTML, base_url="http://localhost/login", title="Login Page")

    assert result.url == "http://localhost/login"
    assert result.title == "Login Page"
    assert "Welcome to App" in result.dom
    assert result.accessibility_tree is not None
    assert len(result.selectors) >= 3
    assert len(result.har_entries) == 1
    assert result.har_entries[0].url == "http://localhost/login"
    assert result.har_entries[0].status == 200
    assert result.screenshot_bytes is None


def test_capture_html_with_screenshot() -> None:
    config = WebCaptureConfig(capture_screenshot=True)
    engine = WebCaptureEngine(config=config)
    result = engine.capture_html(html=SAMPLE_HTML)

    assert result.screenshot_bytes is not None
    assert result.screenshot_bytes.startswith(b"\x89PNG")


def test_capture_html_with_network_entries() -> None:
    engine = WebCaptureEngine()
    extra_entries = [
        {
            "url": "http://localhost/api/user",
            "method": "GET",
            "status": 200,
            "mime_type": "application/json",
            "size_bytes": 128,
        }
    ]
    result = engine.capture_html(html=SAMPLE_HTML, network_entries=extra_entries)
    assert len(result.har_entries) == 2
    assert result.har_entries[1].url == "http://localhost/api/user"


def test_capture_html_captcha_blocked() -> None:
    engine = WebCaptureEngine()
    captcha_html = "<html><body><div class='g-recaptcha'></div></body></html>"

    with pytest.raises(CaptchaDetectedError):
        engine.capture_html(html=captcha_html)


def test_capture_html_domain_policy() -> None:
    config = WebCaptureConfig(allowed_domains=["allowed.org"])
    engine = WebCaptureEngine(config=config)

    with pytest.raises(DomainNotAllowedError):
        engine.capture_html(html=SAMPLE_HTML, base_url="https://forbidden.org/page")


def test_capture_html_flags_disabled() -> None:
    config = WebCaptureConfig(
        capture_dom=False,
        capture_accessibility=False,
        capture_har=False,
        extract_selectors=False,
    )
    engine = WebCaptureEngine(config=config)
    result = engine.capture_html(html=SAMPLE_HTML)

    assert result.dom == ""
    assert result.accessibility_tree is None
    assert result.har_entries == []
    assert result.selectors == []


def test_capture_file(tmp_path: Path) -> None:
    fixture_file = tmp_path / "fixture.html"
    fixture_file.write_text(SAMPLE_HTML, encoding="utf-8")

    engine = WebCaptureEngine()
    result = engine.capture_file(fixture_file)

    assert result.title == "fixture"
    assert "Welcome to App" in result.dom
    assert len(result.selectors) >= 3


def test_capture_file_missing(tmp_path: Path) -> None:
    engine = WebCaptureEngine()
    missing_file = tmp_path / "not_found.html"

    with pytest.raises(FileNotFoundError):
        engine.capture_file(missing_file)


def test_capture_page_async_mock() -> None:
    async def _run() -> None:
        mock_page = AsyncMock()
        mock_page.url = "https://example.com/dashboard"
        mock_page.title = AsyncMock(return_value="Dashboard")
        mock_page.content = AsyncMock(return_value=SAMPLE_HTML)
        mock_page.screenshot = AsyncMock(return_value=b"\x89PNG-fake-screenshot")

        mock_accessibility = MagicMock()
        mock_accessibility.snapshot = AsyncMock(
            return_value={
                "role": "WebArea",
                "name": "Dashboard",
                "children": [{"role": "button", "name": "Login"}],
            }
        )
        mock_page.accessibility = mock_accessibility

        config = WebCaptureConfig(
            allowed_domains=["example.com"],
            capture_screenshot=True,
        )
        engine = WebCaptureEngine(config=config)

        result = await engine.capture_page_async(mock_page)

        assert result.url == "https://example.com/dashboard"
        assert result.title == "Dashboard"
        assert "Welcome to App" in result.dom
        assert result.accessibility_tree is not None
        assert result.accessibility_tree.role == "WebArea"
        assert result.screenshot_bytes == b"\x89PNG-fake-screenshot"
        assert len(result.selectors) >= 3

    asyncio.run(_run())


def test_capture_page_async_detects_captcha() -> None:
    async def _run() -> None:
        mock_page = AsyncMock()
        mock_page.url = "https://example.com/challenge"
        mock_page.title = AsyncMock(return_value="Verify Human")
        mock_page.content = AsyncMock(
            return_value="<html><body><div id='cf-turnstile'>Verifying human</div></body></html>"
        )

        engine = WebCaptureEngine(config=WebCaptureConfig(allowed_domains=["example.com"]))

        with pytest.raises(CaptchaDetectedError):
            await engine.capture_page_async(mock_page)

    asyncio.run(_run())
