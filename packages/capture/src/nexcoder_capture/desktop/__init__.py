"""Desktop window capture, UI Automation, and OCR fallback module."""

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

__all__ = [
    "DesktopBoundingBox",
    "DesktopCaptureConfig",
    "DesktopCaptureEngine",
    "DesktopCaptureResult",
    "DesktopControlNode",
    "DesktopWindowInfo",
    "MockOCRProvider",
    "MockUIAutomationProvider",
    "OCRProvider",
    "OCRTextBlock",
    "TesseractOCRProvider",
    "UIAutomationProvider",
    "WindowsUIAutomationProvider",
]
