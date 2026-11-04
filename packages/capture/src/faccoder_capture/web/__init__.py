"""Web capture module."""

from faccoder_capture.web.accessibility import AccessibilityExtractor
from faccoder_capture.web.capture import WebCaptureEngine
from faccoder_capture.web.har import HarRecorder, sanitize_headers
from faccoder_capture.web.policy import PolicyEnforcer
from faccoder_capture.web.selectors import SelectorExtractor
from faccoder_capture.web.session import SessionManager

__all__ = [
    "AccessibilityExtractor",
    "HarRecorder",
    "PolicyEnforcer",
    "SelectorExtractor",
    "SessionManager",
    "WebCaptureEngine",
    "sanitize_headers",
]
