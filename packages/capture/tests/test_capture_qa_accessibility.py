"""Unit tests for nexcoder_capture.qa.accessibility."""

from __future__ import annotations

from nexcoder_capture.models import AccessibilityNode
from nexcoder_capture.qa.accessibility import audit_accessibility_tree


def test_audit_fully_compliant_tree() -> None:
    nodes = [
        AccessibilityNode(role="banner", name="Main Header"),
        AccessibilityNode(role="navigation", name="Site Nav"),
        AccessibilityNode(role="button", name="Search Submit"),
        AccessibilityNode(role="link", name="Privacy Policy"),
        AccessibilityNode(role="textbox", name="Username", value="admin"),
        AccessibilityNode(role="img", name="Company Logo"),
    ]

    result = audit_accessibility_tree(nodes)

    assert result.is_compliant is True
    assert result.score == 100.0
    assert len(result.violations) == 0
    assert result.passes == result.total_checked


def test_audit_invalid_aria_role() -> None:
    node = AccessibilityNode(role="custom-clickable-box", name="Click here")
    result = audit_accessibility_tree([node])

    assert result.is_compliant is False
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.rule_id == "valid-role"
    assert v.node_role == "custom-clickable-box"


def test_audit_missing_accessible_name_on_interactive_elements() -> None:
    # Button without name, valuetext or description
    btn_empty = AccessibilityNode(role="button", name="")
    result = audit_accessibility_tree([btn_empty])

    assert result.is_compliant is False
    v_ids = [v.rule_id for v in result.violations]
    assert "missing-accessible-name" in v_ids


def test_audit_empty_link() -> None:
    link_empty = AccessibilityNode(role="link", name=None)
    result = audit_accessibility_tree([link_empty])

    assert result.is_compliant is False
    v = next(v for v in result.violations if v.rule_id == "empty-link")
    assert v.impact == "serious"


def test_audit_unlabeled_form_control() -> None:
    textbox_empty = AccessibilityNode(role="textbox", name="")
    result = audit_accessibility_tree([textbox_empty])

    assert result.is_compliant is False
    v = next(v for v in result.violations if v.rule_id == "input-label")
    assert v.impact == "critical"


def test_audit_image_missing_alt() -> None:
    img_empty = AccessibilityNode(role="img", name=None)
    result = audit_accessibility_tree([img_empty])

    assert result.is_compliant is False
    v = next(v for v in result.violations if v.rule_id == "missing-image-alt")
    assert v.impact == "serious"


def test_audit_nested_tree_traversal() -> None:
    # Root document with child button missing accessible name
    bad_button = AccessibilityNode(role="button", name="")
    good_link = AccessibilityNode(role="link", name="Home")
    root = AccessibilityNode(
        role="document",
        name="Page",
        children=[bad_button, good_link],
    )

    result = audit_accessibility_tree([root])
    assert result.is_compliant is False
    assert any(v.rule_id == "missing-accessible-name" for v in result.violations)
