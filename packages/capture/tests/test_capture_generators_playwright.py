"""Unit tests for faccoder_capture.generators.playwright."""

from __future__ import annotations

from faccoder_capture.generators.playwright import (
    _format_locator,
    _sanitize_name,
    generate_playwright_test,
)
from faccoder_capture.models import StableSelector, WebCaptureResult


def test_sanitize_name() -> None:
    assert _sanitize_name("Login Page - User Portal") == "login_page_user_portal"
    assert _sanitize_name("123 Numeric Start") == "capture_page_123_numeric_start"
    assert _sanitize_name("") == "capture_page"


def test_format_locator_strategies() -> None:
    # Test ID strategy
    s_testid = StableSelector(
        primary="getByTestId('submit-btn')",
        css="[data-testid='submit-btn']",
        xpath="//*[@data-testid='submit-btn']",
        tag="button",
        test_id="submit-btn",
        attributes={"data-testid": "submit-btn"},
    )
    assert _format_locator(s_testid) == 'page.get_by_test_id("submit-btn")'

    # Role and name strategy
    s_role = StableSelector(
        primary="getByRole('button', name='Sign In')",
        css="button:has-text('Sign In')",
        xpath="//button[text()='Sign In']",
        tag="button",
        role="button",
        name="Sign In",
        text="Sign In",
    )
    assert _format_locator(s_role) == 'page.get_by_role("button", name="Sign In")'

    # Test ID strategy with alternate test attribute (data-cy)
    s_cy = StableSelector(
        primary="getByTestId('search-box')",
        css="[data-cy='search-box']",
        xpath="//*[@data-cy='search-box']",
        tag="input",
        test_id="search-box",
        attributes={"data-cy": "search-box"},
    )
    assert _format_locator(s_cy) == 'page.get_by_test_id("search-box")'

    # Text strategy with multiline whitespace
    s_text = StableSelector(
        primary="getByText('Help & Support')",
        css="a:has-text('Help & Support')",
        xpath="//a[contains(text(), 'Help')]",
        tag="a",
        strategy="text",
        text="Help   \n   & Support",
    )
    assert _format_locator(s_text) == 'page.get_by_text("Help & Support")'

    # Fallback to locator
    s_fallback = StableSelector(
        primary="#custom-id",
        css="#custom-id",
        xpath="//*[@id='custom-id']",
        tag="div",
    )
    assert _format_locator(s_fallback) == 'page.locator("#custom-id")'


def test_generate_playwright_test_full_page() -> None:
    username_sel = StableSelector(
        primary="[name='username']",
        css="[name='username']",
        xpath="//input[@name='username']",
        tag="input",
        role="textbox",
        attributes={"type": "text", "name": "username"},
    )
    remember_sel = StableSelector(
        primary="#remember",
        css="#remember",
        xpath="//input[@id='remember']",
        tag="input",
        role="checkbox",
        attributes={"type": "checkbox", "id": "remember"},
    )
    submit_sel = StableSelector(
        primary="getByTestId('login-btn')",
        css="[data-testid='login-btn']",
        xpath="//*[@data-testid='login-btn']",
        tag="button",
        role="button",
        test_id="login-btn",
        attributes={"data-testid": "login-btn"},
    )

    result = WebCaptureResult(
        url="https://example.com/login",
        title="Account Portal",
        selectors=[username_sel, remember_sel, submit_sel],
    )

    code = generate_playwright_test(result)

    assert "def test_account_portal(page: Page) -> None:" in code
    assert 'page.goto("https://example.com/login")' in code
    assert 'expect(page).to_have_title("Account Portal")' in code
    assert '.fill("test_input")' in code
    assert ".check()" in code
    assert ".click()" in code


def test_generate_playwright_test_custom_name_and_empty_selectors() -> None:
    result = WebCaptureResult(url="https://example.com/empty", title="")
    code = generate_playwright_test(result, test_name="test_custom_flow")

    assert "def test_custom_flow(page: Page) -> None:" in code
    assert "expect(page.locator('body')).to_be_visible()" in code
