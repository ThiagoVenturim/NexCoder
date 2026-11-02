"""Accessibility auditing engine for inspecting accessibility tree hierarchies."""

from __future__ import annotations

from faccoder_capture.models import AccessibilityNode
from faccoder_capture.qa.models import AccessibilityAuditResult, AccessibilityViolation

STANDARD_ARIA_ROLES = {
    "alert",
    "alertdialog",
    "application",
    "article",
    "banner",
    "button",
    "cell",
    "checkbox",
    "columnheader",
    "combobox",
    "complementary",
    "contentinfo",
    "definition",
    "dialog",
    "directory",
    "document",
    "feed",
    "figure",
    "form",
    "generic",
    "grid",
    "gridcell",
    "group",
    "heading",
    "image",
    "img",
    "link",
    "list",
    "listbox",
    "listitem",
    "log",
    "main",
    "marquee",
    "math",
    "menu",
    "menubar",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "navigation",
    "none",
    "note",
    "option",
    "paragraph",
    "presentation",
    "progressbar",
    "radio",
    "radiogroup",
    "region",
    "row",
    "rowgroup",
    "rowheader",
    "scrollbar",
    "search",
    "searchbox",
    "separator",
    "slider",
    "spinbutton",
    "status",
    "switch",
    "tab",
    "table",
    "tablist",
    "tabpanel",
    "term",
    "textbox",
    "timer",
    "toolbar",
    "tooltip",
    "tree",
    "treegrid",
    "treeitem",
}

INTERACTIVE_ROLES = {
    "button",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "tab",
    "switch",
}

INPUT_ROLES = {
    "textbox",
    "combobox",
    "searchbox",
    "spinbutton",
    "slider",
    "listbox",
    "checkbox",
    "radio",
}


def audit_accessibility_tree(
    nodes: list[AccessibilityNode],
) -> AccessibilityAuditResult:
    """Audit accessibility tree nodes against core accessibility requirements."""
    violations: list[AccessibilityViolation] = []
    passes = 0
    total_checked = 0

    def _has_name(node: AccessibilityNode) -> bool:
        if node.name is not None and node.name.strip():
            return True
        if node.valuetext is not None and node.valuetext.strip():
            return True
        if node.description is not None and node.description.strip():
            return True
        return False

    for node in nodes:
        role_lower = (node.role or "").strip().lower()

        # Rule 1: Valid role check
        total_checked += 1
        if role_lower and role_lower not in STANDARD_ARIA_ROLES:
            violations.append(
                AccessibilityViolation(
                    rule_id="valid-role",
                    description=f"Element has unrecognized ARIA role '{node.role}'.",
                    impact="moderate",
                    node_role=node.role,
                    node_name=node.name,
                )
            )
        else:
            passes += 1

        # Rule 2: Interactive elements must have accessible name
        if role_lower in INTERACTIVE_ROLES:
            total_checked += 1
            if not _has_name(node):
                violations.append(
                    AccessibilityViolation(
                        rule_id="missing-accessible-name",
                        description=f"Interactive element of role '{node.role}' is missing an accessible name.",
                        impact="critical",
                        node_role=node.role,
                        node_name=node.name,
                    )
                )
            else:
                passes += 1

        # Rule 3: Links must have accessible text
        if role_lower == "link":
            total_checked += 1
            if not _has_name(node):
                violations.append(
                    AccessibilityViolation(
                        rule_id="empty-link",
                        description="Link element contains no accessible text or label.",
                        impact="serious",
                        node_role=node.role,
                        node_name=node.name,
                    )
                )
            else:
                passes += 1

        # Rule 4: Form controls must have accessible label
        if role_lower in INPUT_ROLES:
            total_checked += 1
            if not _has_name(node):
                violations.append(
                    AccessibilityViolation(
                        rule_id="input-label",
                        description=f"Form control '{node.role}' is missing an accessible label or name.",
                        impact="critical",
                        node_role=node.role,
                        node_name=node.name,
                    )
                )
            else:
                passes += 1

        # Rule 5: Images must have accessible name or alt text
        if role_lower in {"img", "image", "graphic"}:
            total_checked += 1
            if not _has_name(node):
                violations.append(
                    AccessibilityViolation(
                        rule_id="missing-image-alt",
                        description="Image element is missing an alt text or accessible name.",
                        impact="serious",
                        node_role=node.role,
                        node_name=node.name,
                    )
                )
            else:
                passes += 1

    score = (passes / max(1, total_checked)) * 100.0
    is_compliant = len(violations) == 0

    return AccessibilityAuditResult(
        violations=violations,
        passes=passes,
        total_checked=total_checked,
        score=round(score, 2),
        is_compliant=is_compliant,
    )
