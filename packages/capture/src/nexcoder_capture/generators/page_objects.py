"""Page Object Model generator producing typed Page Object classes."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from faccoder_capture.models import StableSelector, WebCaptureResult


def _to_pascal_case(text: str, fallback: str = "CapturedPage") -> str:
    """Convert text into PascalCase class name."""
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return fallback
    pascal = "".join(w.capitalize() for w in words)
    if not pascal.lower().endswith("page"):
        pascal += "Page"
    elif pascal.endswith("page"):
        pascal = pascal[:-4] + "Page"
    return pascal


def _to_snake_case(text: str, fallback: str = "element") -> str:
    """Convert text into snake_case identifier."""
    cleaned = re.sub(r"[^\w\s-]", "", text.lower())
    snake = re.sub(r"[-\s]+", "_", cleaned).strip("_")
    if not snake or not snake[0].isalpha():
        snake = f"{fallback}_{snake}".strip("_")
    return snake


def _format_locator_expr(selector: StableSelector) -> str:
    """Return locator expression string."""
    test_id = selector.test_id or selector.attributes.get("data-testid")
    if test_id:
        clean_id = test_id.strip().replace('"', '\\"')
        return f'self.page.get_by_test_id("{clean_id}")'

    if selector.role and selector.text:
        clean_text = " ".join(selector.text.split()).replace('"', '\\"')
        return f'self.page.get_by_role("{selector.role}", name="{clean_text}")'

    if selector.strategy == "text" or (selector.text and "getByText" in selector.primary):
        clean_text = " ".join((selector.text or "").split()).replace('"', '\\"')
        return f'self.page.get_by_text("{clean_text}")'

    primary = selector.primary_selector.replace('"', '\\"')
    return f'self.page.locator("{primary}")'


def generate_page_object(
    result: WebCaptureResult,
    class_name: str | None = None,
) -> str:
    """Generate a typed Playwright Page Object Model class from a WebCaptureResult."""
    if not class_name:
        if result.title:
            class_name = _to_pascal_case(result.title)
        else:
            path = urlparse(result.url).path.strip("/").replace("/", " ")
            class_name = _to_pascal_case(path, fallback="CapturedPage")

    lines: list[str] = [
        f'"""Page Object for {result.url}."""',
        "",
        "from __future__ import annotations",
        "",
        "from playwright.sync_api import Locator, Page",
        "",
        "",
        f"class {class_name}:",
        f'    """Page Object Model representing {result.title or "captured page"}."""',
        "",
        "    def __init__(self, page: Page) -> None:",
        "        self.page = page",
        "",
        "    def goto(self) -> None:",
        f'        """Navigate to {result.url}."""',
        f'        self.page.goto("{result.url}")',
        "",
    ]

    seen_names: set[str] = set()
    property_entries: list[tuple[str, str, StableSelector]] = []

    for sel in result.selectors:
        tag = (sel.tag or "element").lower()
        role = (sel.role or "").lower()

        # Derive a human-readable property name
        prop_base = (
            sel.test_id
            or sel.attributes.get("data-testid")
            or sel.attributes.get("name")
            or sel.attributes.get("id")
            or sel.text
            or role
            or tag
        )
        snake_name = _to_snake_case(prop_base, fallback=tag)

        # Avoid collision with class methods or keywords
        if snake_name in {"goto", "page", "init"} or snake_name in seen_names:
            snake_name = f"{snake_name}_{len(seen_names) + 1}"
        seen_names.add(snake_name)

        loc_expr = _format_locator_expr(sel)
        property_entries.append((snake_name, loc_expr, sel))

    # Add locator properties
    for prop_name, loc_expr, _ in property_entries:
        lines.append("    @property")
        lines.append(f"    def {prop_name}(self) -> Locator:")
        lines.append(f"        return {loc_expr}")
        lines.append("")

    # Add interaction helper methods
    for prop_name, _, sel in property_entries:
        tag = (sel.tag or "").lower()
        role = (sel.role or "").lower()
        input_type = sel.attributes.get("type", "text").lower()

        if tag in {"input", "textarea"} or role in {"textbox", "searchbox"}:
            if input_type in {"checkbox", "radio"}:
                lines.append(f"    def check_{prop_name}(self) -> None:")
                lines.append(f"        self.{prop_name}.check()")
                lines.append("")
            elif input_type not in {"submit", "button", "reset", "hidden"}:
                lines.append(f"    def fill_{prop_name}(self, value: str) -> None:")
                lines.append(f"        self.{prop_name}.fill(value)")
                lines.append("")
        elif tag == "button" or role == "button" or input_type == "submit":
            lines.append(f"    def click_{prop_name}(self) -> None:")
            lines.append(f"        self.{prop_name}.click()")
            lines.append("")

    return "\n".join(lines)
