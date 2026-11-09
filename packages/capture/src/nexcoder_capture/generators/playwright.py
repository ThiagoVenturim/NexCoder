"""Playwright test generator producing executable pytest-playwright test cases."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from nexcoder_capture.models import StableSelector, WebCaptureResult


def _sanitize_name(text: str, fallback: str = "capture_page") -> str:
    """Convert text into a valid snake_case identifier."""
    cleaned = re.sub(r"[^\w\s-]", "", text.lower())
    sanitized = re.sub(r"[-\s]+", "_", cleaned).strip("_")
    if not sanitized or not sanitized[0].isalpha():
        sanitized = f"{fallback}_{sanitized}".strip("_")
    return sanitized


def _format_locator(selector: StableSelector) -> str:
    """Format a stable selector into a Playwright locator call."""
    test_id = selector.test_id or selector.attributes.get("data-testid")
    if test_id:
        clean_id = test_id.strip().replace('"', '\\"')
        return f'page.get_by_test_id("{clean_id}")'

    if selector.role and selector.text:
        clean_text = " ".join(selector.text.split()).replace('"', '\\"')
        return f'page.get_by_role("{selector.role}", name="{clean_text}")'

    if selector.strategy == "text" or (selector.text and "getByText" in selector.primary):
        clean_text = " ".join((selector.text or "").split()).replace('"', '\\"')
        return f'page.get_by_text("{clean_text}")'

    primary = selector.primary_selector.replace('"', '\\"')
    return f'page.locator("{primary}")'


def generate_playwright_test(
    result: WebCaptureResult,
    test_name: str | None = None,
) -> str:
    """Generate an executable pytest-playwright test script from a WebCaptureResult."""
    if not test_name:
        if result.title:
            test_name = f"test_{_sanitize_name(result.title)}"
        else:
            path = urlparse(result.url).path.strip("/").replace("/", "_")
            test_name = f"test_{_sanitize_name(path, fallback='page')}"

    lines: list[str] = [
        f'"""Automated Playwright test for {result.url}."""',
        "",
        "from playwright.sync_api import Page, expect",
        "",
        "",
        f"def {test_name}(page: Page) -> None:",
        f'    """Verify {result.title or "captured page"} layout and key interactions."""',
        f'    page.goto("{result.url}")',
    ]

    if result.title:
        escaped_title = result.title.replace('"', '\\"')
        lines.append(f'    expect(page).to_have_title("{escaped_title}")')

    seen_locators: set[str] = set()

    # Process selectors into assertions and sample actions
    for sel in result.selectors:
        loc = _format_locator(sel)
        if loc in seen_locators:
            continue
        seen_locators.add(loc)

        tag = (sel.tag or "").lower()
        role = (sel.role or "").lower()

        # Input elements
        if tag in {"input", "textarea"} or role in {"textbox", "searchbox"}:
            lines.append(f"    expect({loc}).to_be_visible()")
            input_type = sel.attributes.get("type", "text").lower()
            if input_type in {"checkbox", "radio"}:
                lines.append(f"    {loc}.check()")
            elif input_type not in {"submit", "button", "reset", "hidden"}:
                lines.append(f'    {loc}.fill("test_input")')
        # Buttons
        elif tag == "button" or role == "button" or sel.attributes.get("type") == "submit":
            lines.append(f"    expect({loc}).to_be_visible()")
            lines.append(f"    {loc}.click()")
        # Links and headings
        else:
            lines.append(f"    expect({loc}).to_be_visible()")

    if not result.selectors:
        lines.append("    expect(page.locator('body')).to_be_visible()")

    lines.append("")
    return "\n".join(lines)
