"""faccoder-capture: Web and desktop capture, stable selectors, test generation, and QA checks."""

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
    "DomainNotAllowedError",
    "NetworkEntry",
    "ReadOnlyViolationError",
    "RobotsDisallowedError",
    "StableSelector",
    "WebCaptureConfig",
    "WebCaptureResult",
    "WebCaptureEngine",
]
