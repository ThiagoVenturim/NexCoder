"""QA checking, visual regression, accessibility auditing, and screen documentation."""

from nexcoder_capture.qa.accessibility import audit_accessibility_tree
from nexcoder_capture.qa.models import (
    AccessibilityAuditResult,
    AccessibilityViolation,
    VisualDiffResult,
)
from nexcoder_capture.qa.screen_doc import generate_screen_documentation
from nexcoder_capture.qa.visual import compare_screenshots

__all__ = [
    "AccessibilityAuditResult",
    "AccessibilityViolation",
    "VisualDiffResult",
    "audit_accessibility_tree",
    "compare_screenshots",
    "generate_screen_documentation",
]
