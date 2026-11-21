"""nexcoder-capture: Web and desktop capture, stable selectors, test generation, and QA checks."""

from nexcoder_capture.desktop.capture import DesktopCaptureEngine
from nexcoder_capture.desktop.engine import (
    MockUIAutomationProvider,
    UIAutomationProvider,
    WindowsUIAutomationProvider,
)
from nexcoder_capture.desktop.models import (
    DesktopBoundingBox,
    DesktopCaptureConfig,
    DesktopCaptureResult,
    DesktopControlNode,
    DesktopWindowInfo,
    OCRTextBlock,
)
from nexcoder_capture.desktop.ocr import (
    MockOCRProvider,
    OCRProvider,
    TesseractOCRProvider,
)
from nexcoder_capture.generators.page_objects import generate_page_object
from nexcoder_capture.generators.playwright import generate_playwright_test
from nexcoder_capture.models import (
    AccessibilityNode,
    CaptchaDetectedError,
    CapturePolicyError,
    DomainNotAllowedError,
    NetworkEntry,
    ReadOnlyViolationError,
    RobotsDisallowedError,
    StableSelector,
    WebCaptureConfig,
    WebCaptureResult,
)
from nexcoder_capture.qa.accessibility import audit_accessibility_tree
from nexcoder_capture.qa.models import (
    AccessibilityAuditResult,
    AccessibilityViolation,
    VisualDiffResult,
)
from nexcoder_capture.qa.screen_doc import generate_screen_documentation
from nexcoder_capture.qa.visual import compare_screenshots
from nexcoder_capture.web.capture import WebCaptureEngine

__all__ = [
    "AccessibilityAuditResult",
    "AccessibilityNode",
    "AccessibilityViolation",
    "CaptchaDetectedError",
    "CapturePolicyError",
    "DesktopBoundingBox",
    "DesktopCaptureConfig",
    "DesktopCaptureEngine",
    "DesktopCaptureResult",
    "DesktopControlNode",
    "DesktopWindowInfo",
    "DomainNotAllowedError",
    "MockOCRProvider",
    "MockUIAutomationProvider",
    "NetworkEntry",
    "OCRProvider",
    "OCRTextBlock",
    "ReadOnlyViolationError",
    "RobotsDisallowedError",
    "StableSelector",
    "TesseractOCRProvider",
    "UIAutomationProvider",
    "VisualDiffResult",
    "WebCaptureConfig",
    "WebCaptureEngine",
    "WebCaptureResult",
    "WindowsUIAutomationProvider",
    "audit_accessibility_tree",
    "compare_screenshots",
    "generate_page_object",
    "generate_playwright_test",
    "generate_screen_documentation",
]
