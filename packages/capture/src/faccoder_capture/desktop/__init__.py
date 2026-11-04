"""Desktop window capture, UI Automation, and OCR fallback module."""

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
