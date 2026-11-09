"""Data models for desktop window inspection, UI automation, and OCR fallback."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class DesktopBoundingBox(BaseModel):
    """Bounding box coordinates for desktop windows and controls."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)


class DesktopWindowInfo(BaseModel):
    """Metadata describing a desktop application window."""

    handle: int
    title: str = ""
    class_name: str = ""
    process_id: int = 0
    bounds: DesktopBoundingBox | None = None
    is_visible: bool = True


class DesktopControlNode(BaseModel):
    """Represents a UI element in the Windows UI Automation tree."""

    handle: int = 0
    name: str = ""
    control_type: str = "Control"
    class_name: str = ""
    bounds: DesktopBoundingBox | None = None
    is_enabled: bool = True
    is_visible: bool = True
    automation_id: str | None = None
    value: str | None = None
    children: list[DesktopControlNode] = Field(default_factory=list)


class OCRTextBlock(BaseModel):
    """Extracted text block from an image with bounding box and confidence score."""

    text: str
    bounds: DesktopBoundingBox | None = None
    confidence: float = 1.0


class DesktopCaptureConfig(BaseModel):
    """Configuration settings for desktop capture operations."""

    capture_screenshot: bool = True
    extract_controls: bool = True
    run_ocr_fallback: bool = True
    ocr_min_confidence: float = 0.5
    read_only: bool = True
    max_depth: int = 20


class DesktopCaptureResult(BaseModel):
    """Aggregated output of a desktop capture run."""

    window_info: DesktopWindowInfo | None = None
    controls: list[DesktopControlNode] = Field(default_factory=list)
    screenshot_bytes: bytes | None = None
    ocr_results: list[OCRTextBlock] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
