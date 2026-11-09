"""Unit tests for nexcoder_capture.generators.page_objects."""

from __future__ import annotations

from nexcoder_capture.generators.page_objects import (
    _format_locator_expr,
    _to_pascal_case,
    _to_snake_case,
    generate_page_object,
)
from nexcoder_capture.models import StableSelector, WebCaptureResult


def test_naming_helpers() -> None:
    assert _to_pascal_case("user settings modal") == "UserSettingsModalPage"
    assert _to_pascal_case("AdminPage") == "AdminPage"
    assert _to_pascal_case("!!!") == "CapturedPage"

    assert _to_snake_case("Submit Order Button") == "submit_order_button"
    assert _to_snake_case("123-number") == "element_123_number"
    assert _to_snake_case("") == "element"


def test_format_locator_expr() -> None:
    s_test = StableSelector(
        primary="getByTestId('search')",
        css="[data-testid='search']",
        xpath="//*[@data-testid='search']",
        tag="input",
        test_id="search",
        attributes={"data-testid": "search"},
    )
    assert _format_locator_expr(s_test) == 'self.page.get_by_test_id("search")'

    s_role = StableSelector(
        primary="getByRole('button', name='Save')",
        css="button:has-text('Save')",
        xpath="//button[text()='Save']",
        tag="button",
        role="button",
        name="Save",
        text="Save",
    )
    assert _format_locator_expr(s_role) == 'self.page.get_by_role("button", name="Save")'

    # Test ID strategy with alternate test attribute (data-qa)
    s_qa = StableSelector(
        primary="getByTestId('search-box')",
        css="[data-qa='search-box']",
        xpath="//*[@data-qa='search-box']",
        tag="input",
        test_id="search-box",
        attributes={"data-qa": "search-box"},
    )
    assert _format_locator_expr(s_qa) == 'self.page.get_by_test_id("search-box")'

    # Text strategy
    s_text = StableSelector(
        primary="getByText('Documentation')",
        css="a:has-text('Documentation')",
        xpath="//a[contains(text(), 'Documentation')]",
        tag="a",
        strategy="text",
        text="Documentation",
    )
    assert _format_locator_expr(s_text) == 'self.page.get_by_text("Documentation")'

    s_css = StableSelector(
        primary=".navbar > a",
        css=".navbar > a",
        xpath="//a",
        tag="a",
    )
    assert _format_locator_expr(s_css) == 'self.page.locator(".navbar > a")'


def test_generate_page_object_complete() -> None:
    username = StableSelector(
        primary="[name='user']",
        css="[name='user']",
        xpath="//input",
        tag="input",
        role="textbox",
        attributes={"name": "user", "type": "text"},
    )
    agree = StableSelector(
        primary="#agree-terms",
        css="#agree-terms",
        xpath="//input[@id='agree-terms']",
        tag="input",
        role="checkbox",
        attributes={"id": "agree_terms", "type": "checkbox"},
    )
    submit = StableSelector(
        primary="button#submit",
        css="button#submit",
        xpath="//button",
        tag="button",
        name="Submit",
        attributes={"id": "submit"},
    )

    result = WebCaptureResult(
        url="https://example.com/checkout",
        title="Checkout Experience",
        selectors=[username, agree, submit],
    )

    code = generate_page_object(result)

    assert "class CheckoutExperiencePage:" in code
    assert "def goto(self) -> None:" in code
    assert 'self.page.goto("https://example.com/checkout")' in code

    # Locator properties
    assert "@property" in code
    assert "def user(self) -> Locator:" in code
    assert "def agree_terms(self) -> Locator:" in code
    assert "def submit(self) -> Locator:" in code

    # Action helper methods
    assert "def fill_user(self, value: str) -> None:" in code
    assert "def check_agree_terms(self) -> None:" in code
    assert "def click_submit(self) -> None:" in code


def test_generate_page_object_deduplication_and_custom_name() -> None:
    # Multiple selectors resolving to conflicting names like "page" or "goto"
    sel1 = StableSelector(primary="#page", css="#page", xpath="//div", tag="div", attributes={"id": "page"})
    sel2 = StableSelector(primary="#goto", css="#goto", xpath="//div", tag="div", attributes={"id": "goto"})
    sel3 = StableSelector(primary="#page-2", css="#page-2", xpath="//div", tag="div", attributes={"id": "page"})

    result = WebCaptureResult(
        url="https://example.com/app",
        selectors=[sel1, sel2, sel3],
    )

    code = generate_page_object(result, class_name="CustomAppPage")
    assert "class CustomAppPage:" in code
    # Collision names appended with index
    assert "def page_1(self) -> Locator:" in code
    assert "def goto_2(self) -> Locator:" in code
    assert "def page_3(self) -> Locator:" in code
