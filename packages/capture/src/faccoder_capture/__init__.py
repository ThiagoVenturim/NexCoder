"""faccoder-capture: Web and desktop capture, stable selectors, test generation, and QA checks."""

from faccoder_capture.desktop.capture import DesktopCaptureEngine
from faccoder_capture.desktop.engine import (
    MockUIAutomationProvider,
    UIAutomationProvider,
    WindowsUIAutomationProvider,
)
from faccoder_capture.desktop.models import (
    DesktopBoundingBox,
    DesktopCaptureConfig,
    DesktopCaptureResult,
    DesktopControlNode,
    DesktopWindowInfo,
    OCRTextBlock,
)
from faccoder_capture.desktop.ocr import (
    MockOCRProvider,
    OCRProvider,
    TesseractOCRProvider,
)
from faccoder_capture.generators.page_objects import generate_page_object
from faccoder_capture.generators.playwright import generate_playwright_test
from faccoder_capture.models import (
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
from faccoder_capture.qa.accessibility import audit_accessibility_tree
from faccoder_capture.qa.models import (
    AccessibilityAuditResult,
    AccessibilityViolation,
    VisualDiffResult,
)
from faccoder_capture.qa.screen_doc import generate_screen_documentation
from faccoder_capture.qa.visual import compare_screenshots
from faccoder_capture.web.capture import WebCaptureEngine

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
