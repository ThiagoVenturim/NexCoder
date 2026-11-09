"""Data models for nexcoder-capture."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from nexcoder_capture.desktop.models import (
    DesktopBoundingBox,
    DesktopCaptureConfig,
    DesktopCaptureResult,
    DesktopControlNode,
    DesktopWindowInfo,
    OCRTextBlock,
)


class AccessibilityNode(BaseModel):
    """Represents a node in the accessibility tree."""

    role: str
    name: str | None = None
    value: str | None = None
    description: str | None = None
    keyshortcuts: str | None = None
    roledescription: str | None = None
    valuetext: str | None = None
    disabled: bool = False
    expanded: bool | None = None
    focused: bool = False
    modal: bool = False
    multiline: bool = False
    multiselectable: bool = False
    readonly: bool = False
    required: bool = False
    selected: bool = False
    checked: bool | str = False
    pressed: bool | str = False
    level: int | None = None
    valuemin: float | None = None
    valuemax: float | None = None
    children: list[AccessibilityNode] = Field(default_factory=list)


class StableSelector(BaseModel):
    """Represents a computed stable selector for an interactive element."""

    primary: str
    css: str
    xpath: str
    tag: str
    role: str | None = None
    name: str | None = None
    test_id: str | None = None
    confidence: float = 1.0
    strategy: str = "id"
    attributes: dict[str, str] = Field(default_factory=dict)
    text: str | None = None

    @model_validator(mode="after")
    def _fill_defaults(self) -> StableSelector:
        if not self.attributes:
            attrs: dict[str, str] = {}
            if self.test_id:
                attrs["data-testid"] = self.test_id
            if self.name:
                attrs["name"] = self.name
            self.attributes = attrs
        if self.text is None and self.name:
            self.text = self.name
        return self

    @property
    def primary_selector(self) -> str:
        return self.primary

    @property
    def selector_type(self) -> str:
        return self.strategy


class NetworkEntry(BaseModel):
    """Represents a single captured HTTP request/response transaction."""

    url: str
    method: str
    status: int
    request_headers: dict[str, str] = Field(default_factory=dict)
    response_headers: dict[str, str] = Field(default_factory=dict)
    mime_type: str = ""
    time_ms: float = 0.0
    size_bytes: int = 0

    @property
    def response_body_size(self) -> int:
        return self.size_bytes


class WebCaptureConfig(BaseModel):
    """Configuration options for web capture operations."""

    capture_dom: bool = True
    capture_accessibility: bool = True
    capture_screenshot: bool = False
    capture_har: bool = True
    extract_selectors: bool = True
    timeout_ms: int = 30000
    user_agent: str = "nexcoder-capture/0.1.0"
    honor_robots_txt: bool = True
    allowed_domains: list[str] = Field(default_factory=list)
    read_only: bool = True
    storage_state_path: str | None = None


class WebCaptureResult(BaseModel):
    """Result of a web capture run."""

    url: str
    title: str = ""
    dom: str = ""
    accessibility_tree: AccessibilityNode | None = None
    screenshot_bytes: bytes | None = None
    screenshot_path: str | None = None
    har_entries: list[NetworkEntry] = Field(default_factory=list)
    selectors: list[StableSelector] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    is_captcha_detected: bool = False
    status_code: int = 200
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def network_entries(self) -> list[NetworkEntry]:
        return self.har_entries


class CapturePolicyError(Exception):
    """Base exception for capture policy violations."""


class RobotsDisallowedError(CapturePolicyError):
    """Raised when URL is disallowed by robots.txt."""


class CaptchaDetectedError(CapturePolicyError):
    """Raised when a CAPTCHA challenge is encountered. Bypassing is prohibited."""


class DomainNotAllowedError(CapturePolicyError):
    """Raised when URL domain is outside the allowed domains list."""


class ReadOnlyViolationError(CapturePolicyError):
    """Raised when an operation attempts a mutating action in read-only mode."""


__all__ = [
    "AccessibilityNode",
    "CaptchaDetectedError",
    "CapturePolicyError",
    "DesktopBoundingBox",
    "DesktopCaptureConfig",
    "DesktopCaptureResult",
    "DesktopControlNode",
    "DesktopWindowInfo",
    "DomainNotAllowedError",
    "NetworkEntry",
    "OCRTextBlock",
    "ReadOnlyViolationError",
    "RobotsDisallowedError",
    "StableSelector",
    "WebCaptureConfig",
    "WebCaptureResult",
]
