"""Stable selector extraction from DOM structures."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from faccoder_capture.models import StableSelector

TEST_ID_ATTRS = ("data-testid", "data-test", "data-cy", "data-qa", "data-test-id")
INTERACTIVE_TAGS = {"button", "input", "select", "textarea", "a", "form"}
VOID_TAGS = {
    "input",
    "img",
    "br",
    "hr",
    "meta",
    "link",
    "area",
    "base",
    "col",
    "embed",
    "param",
    "source",
    "track",
    "wbr",
}


class ElementNode:
    """Represents a parsed element for selector generation."""

    def __init__(
        self,
        tag: str,
        attrs: dict[str, str],
        parent: ElementNode | None = None,
        index_in_parent: int = 1,
    ) -> None:
        self.tag = tag.lower()
        self.attrs = attrs
        self.parent = parent
        self.index_in_parent = index_in_parent
        self.children: list[ElementNode] = []
        self.text_content: str = ""

    @property
    def id_val(self) -> str | None:
        return self.attrs.get("id")

    @property
    def test_id(self) -> str | None:
        for attr in TEST_ID_ATTRS:
            if attr in self.attrs:
                return self.attrs[attr]
        return None

    @property
    def role(self) -> str | None:
        if "role" in self.attrs:
            return self.attrs["role"]
        if self.tag == "button":
            return "button"
        if self.tag == "a" and "href" in self.attrs:
            return "link"
        if self.tag == "input":
            input_type = self.attrs.get("type", "text").lower()
            if input_type in ("button", "submit", "reset"):
                return "button"
            if input_type == "checkbox":
                return "checkbox"
            if input_type == "radio":
                return "radio"
            return "textbox"
        return None

    @property
    def accessible_name(self) -> str | None:
        for attr in ("aria-label", "aria-labelledby", "title", "placeholder", "name"):
            if attr in self.attrs:
                return self.attrs[attr]
        if self.text_content.strip():
            return self.text_content.strip()
        return None


class DOMParser(HTMLParser):
    """Parses HTML into a tree of ElementNodes."""

    def __init__(self) -> None:
        super().__init__()
        self.root: ElementNode = ElementNode("document", {})
        self.current: ElementNode = self.root
        self.elements: list[ElementNode] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        attr_dict = {k.lower(): v or "" for k, v in attrs}
        sibling_count = sum(1 for c in self.current.children if c.tag == tag_lower) + 1
        node = ElementNode(tag_lower, attr_dict, parent=self.current, index_in_parent=sibling_count)
        self.current.children.append(node)
        self.elements.append(node)
        if tag_lower not in VOID_TAGS:
            self.current = node

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in VOID_TAGS:
            return
        if self.current.parent:
            self.current = self.current.parent

    def handle_data(self, data: str) -> None:
        self.current.text_content += data


class SelectorExtractor:
    """Extracts stable, robust selectors for interactive DOM elements."""

    def extract_from_html(self, html: str) -> list[StableSelector]:
        """Parse HTML string and generate selectors for interactive elements."""
        parser = DOMParser()
        parser.feed(html)
        return self.extract_from_elements(parser.elements)

    def extract_from_elements(self, elements: list[ElementNode]) -> list[StableSelector]:
        """Generate selectors for a list of ElementNodes."""
        selectors: list[StableSelector] = []
        for el in elements:
            if not self._is_candidate(el):
                continue
            selector = self._compute_selector(el)
            if selector:
                selectors.append(selector)
        return selectors

    def _is_candidate(self, el: ElementNode) -> bool:
        if el.tag in INTERACTIVE_TAGS:
            return True
        if el.test_id or el.id_val or el.role or "tabindex" in el.attrs:
            return True
        return False

    def _compute_selector(self, el: ElementNode) -> StableSelector:
        test_id = el.test_id
        tag = el.tag
        role = el.role
        name = el.accessible_name
        xpath = self._generate_xpath(el)

        # 1. Test ID strategy
        if test_id:
            for attr in TEST_ID_ATTRS:
                if attr in el.attrs:
                    css = f"[{attr}='{test_id}']"
                    return StableSelector(
                        primary=f"getByTestId('{test_id}')",
                        css=css,
                        xpath=f"//*[@{attr}='{test_id}']",
                        tag=tag,
                        role=role,
                        name=name,
                        test_id=test_id,
                        confidence=1.0,
                        strategy="test_id",
                    )

        # 2. Unique ID strategy
        if el.id_val and self._is_valid_id(el.id_val):
            id_val = el.id_val
            return StableSelector(
                primary=f"#{id_val}",
                css=f"#{id_val}",
                xpath=f"//*[@id='{id_val}']",
                tag=tag,
                role=role,
                name=name,
                confidence=0.95,
                strategy="id",
            )

        # 3. Role + accessible name
        if role and name:
            safe_name = name.replace("'", "\\'")
            css = (
                f"[role='{role}'][aria-label='{safe_name}']"
                if "aria-label" in el.attrs
                else f"{tag}[aria-label='{safe_name}']"
            )
            return StableSelector(
                primary=f"getByRole('{role}', name='{safe_name}')",
                css=css if "aria-label" in el.attrs else f"{tag}:has-text('{safe_name}')",
                xpath=f"//{tag}[(@role='{role}' or not(@role)) and contains(., '{safe_name}')]",
                tag=tag,
                role=role,
                name=name,
                confidence=0.90,
                strategy="role_name",
            )

        # 4. Text content strategy (for buttons, links)
        if name and tag in ("button", "a"):
            safe_name = name.replace("'", "\\'")
            return StableSelector(
                primary=f"getByText('{safe_name}')",
                css=f"{tag}:has-text('{safe_name}')",
                xpath=f"//{tag}[contains(text(), '{safe_name}')]",
                tag=tag,
                role=role,
                name=name,
                confidence=0.85,
                strategy="text",
            )

        # 5. Structural CSS fallback
        css_path = self._generate_css_path(el)
        return StableSelector(
            primary=css_path,
            css=css_path,
            xpath=xpath,
            tag=tag,
            role=role,
            name=name,
            confidence=0.70,
            strategy="css_path",
        )

    def _is_valid_id(self, id_val: str) -> bool:
        # Avoid dynamic ids like react-:r1: or purely numeric ids
        if re.search(r"^[:0-9]|-[0-9]{5,}", id_val):
            return False
        return True

    def _generate_css_path(self, el: ElementNode) -> str:
        parts: list[str] = []
        curr: ElementNode | None = el
        while curr and curr.tag != "document":
            if curr.id_val and self._is_valid_id(curr.id_val):
                parts.append(f"#{curr.id_val}")
                break
            parts.append(f"{curr.tag}:nth-of-type({curr.index_in_parent})")
            curr = curr.parent
        return " > ".join(reversed(parts)) if parts else el.tag

    def _generate_xpath(self, el: ElementNode) -> str:
        parts: list[str] = []
        curr: ElementNode | None = el
        while curr and curr.tag != "document":
            if curr.id_val and self._is_valid_id(curr.id_val):
                parts.append(f"//*[@id='{curr.id_val}']")
                break
            parts.append(f"{curr.tag}[{curr.index_in_parent}]")
            curr = curr.parent
        if not parts:
            return f"//{el.tag}"
        rev = list(reversed(parts))
        if rev[0].startswith("//"):
            return rev[0] + ("/" + "/".join(rev[1:]) if len(rev) > 1 else "")
        return "/" + "/".join(rev)
