"""QA checking, visual regression, accessibility auditing, and screen documentation."""

from faccoder_capture.qa.accessibility import audit_accessibility_tree
from faccoder_capture.qa.models import (
    AccessibilityAuditResult,
    AccessibilityViolation,
    VisualDiffResult,
)
from faccoder_capture.qa.screen_doc import generate_screen_documentation
from faccoder_capture.qa.visual import compare_screenshots

__all__ = [
    "AccessibilityAuditResult",
    "AccessibilityViolation",
    "VisualDiffResult",
    "audit_accessibility_tree",
    "compare_screenshots",
    "generate_screen_documentation",
]
