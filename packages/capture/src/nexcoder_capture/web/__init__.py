"""Web capture module."""

from nexcoder_capture.web.accessibility import AccessibilityExtractor
from nexcoder_capture.web.capture import WebCaptureEngine
from nexcoder_capture.web.har import HarRecorder, sanitize_headers
from nexcoder_capture.web.policy import PolicyEnforcer
from nexcoder_capture.web.selectors import SelectorExtractor
from nexcoder_capture.web.session import SessionManager

__all__ = [
    "AccessibilityExtractor",
    "HarRecorder",
    "PolicyEnforcer",
    "SelectorExtractor",
    "SessionManager",
    "WebCaptureEngine",
    "sanitize_headers",
]
