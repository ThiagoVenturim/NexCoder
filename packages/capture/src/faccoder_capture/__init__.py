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
from faccoder_capture.web.capture import WebCaptureEngine

__all__ = [
    "AccessibilityNode",
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
    "WebCaptureConfig",
    "WebCaptureEngine",
    "WebCaptureResult",
    "WindowsUIAutomationProvider",
]
