"""Unit tests for nexcoder_capture.web.accessibility."""

from __future__ import annotations

from nexcoder_capture.web.accessibility import AccessibilityExtractor, parse_playwright_a11y


def test_parse_playwright_a11y_structure() -> None:
    raw_snapshot = {
        "role": "WebArea",
        "name": "Test Page",
        "children": [
            {
                "role": "heading",
                "name": "Main Header",
                "level": 1,
            },
            {
                "role": "button",
                "name": "Submit Form",
                "disabled": True,
                "children": [],
            },
        ],
    }

    node = parse_playwright_a11y(raw_snapshot)
    assert node.role == "WebArea"
    assert node.name == "Test Page"
    assert len(node.children) == 2

    heading = node.children[0]
    assert heading.role == "heading"
    assert heading.name == "Main Header"
    assert heading.level == 1

    button = node.children[1]
    assert button.role == "button"
    assert button.name == "Submit Form"
    assert button.disabled is True


def test_extractor_from_playwright_snapshot_none() -> None:
    extractor = AccessibilityExtractor()
    assert extractor.from_playwright_snapshot(None) is None


def test_extractor_from_html() -> None:
    html = """
    <html>
      <head><title>A11y Test</title></head>
      <body>
        <main role="main">
          <h1>Dashboard</h1>
          <button aria-label="Refresh Data" disabled>Reload</button>
          <input type="text" name="query" required placeholder="Search..." />
        </main>
      </body>
    </html>
    """
    extractor = AccessibilityExtractor()
    root_node = extractor.from_html(html)

    assert root_node.role == "document"
    assert len(root_node.children) > 0

    # Search recursively for button and input
    def find_by_role(node, role):
        results = []
        if node.role == role:
            results.append(node)
        for child in node.children:
            results.extend(find_by_role(child, role))
        return results

    buttons = find_by_role(root_node, "button")
    assert len(buttons) >= 1
    assert buttons[0].disabled is True
    assert buttons[0].name == "Refresh Data"

    inputs = find_by_role(root_node, "textbox")
    assert len(inputs) >= 1
    assert inputs[0].required is True
