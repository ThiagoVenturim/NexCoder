"""Accessibility tree modeling and extraction."""

from __future__ import annotations

from typing import Any

from faccoder_capture.models import AccessibilityNode
from faccoder_capture.web.selectors import DOMParser, ElementNode


def parse_playwright_a11y(raw_node: dict[str, Any]) -> AccessibilityNode:
    """Recursively parse Playwright's accessibility snapshot dictionary into an AccessibilityNode."""
    children_raw = raw_node.get("children", [])
    children = [parse_playwright_a11y(c) for c in children_raw if isinstance(c, dict)]

    return AccessibilityNode(
        role=raw_node.get("role", "generic"),
        name=raw_node.get("name"),
        value=str(raw_node["value"]) if "value" in raw_node and raw_node["value"] is not None else None,
        description=raw_node.get("description"),
        keyshortcuts=raw_node.get("keyshortcuts"),
        roledescription=raw_node.get("roledescription"),
        valuetext=raw_node.get("valuetext"),
        disabled=bool(raw_node.get("disabled", False)),
        expanded=raw_node.get("expanded"),
        focused=bool(raw_node.get("focused", False)),
        modal=bool(raw_node.get("modal", False)),
        multiline=bool(raw_node.get("multiline", False)),
        multiselectable=bool(raw_node.get("multiselectable", False)),
        readonly=bool(raw_node.get("readonly", False)),
        required=bool(raw_node.get("required", False)),
        selected=bool(raw_node.get("selected", False)),
        checked=raw_node.get("checked", False),
        pressed=raw_node.get("pressed", False),
        level=raw_node.get("level"),
        valuemin=float(raw_node["valuemin"]) if "valuemin" in raw_node else None,
        valuemax=float(raw_node["valuemax"]) if "valuemax" in raw_node else None,
        children=children,
    )


class AccessibilityExtractor:
    """Extracts or derives accessibility trees from snapshots or HTML."""

    def from_playwright_snapshot(self, snapshot: dict[str, Any] | None) -> AccessibilityNode | None:
        """Parse raw snapshot returned by Playwright page.accessibility.snapshot()."""
        if not snapshot:
            return None
        return parse_playwright_a11y(snapshot)

    def from_html(self, html: str) -> AccessibilityNode:
        """Derive an accessibility tree from raw HTML for offline and fixture environments."""
        parser = DOMParser()
        parser.feed(html)
        return self._convert_dom_to_a11y(parser.root)

    def _convert_dom_to_a11y(self, dom_node: ElementNode) -> AccessibilityNode:
        role = dom_node.role or ("document" if dom_node.tag == "document" else "generic")
        name = dom_node.accessible_name
        children = [self._convert_dom_to_a11y(child) for child in dom_node.children]

        disabled = "disabled" in dom_node.attrs
        required = "required" in dom_node.attrs
        readonly = "readonly" in dom_node.attrs

        return AccessibilityNode(
            role=role,
            name=name,
            disabled=disabled,
            required=required,
            readonly=readonly,
            children=children,
        )
