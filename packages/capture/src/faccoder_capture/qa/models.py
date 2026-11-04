"""Data models for QA checks, visual regression, and accessibility auditing."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VisualDiffResult(BaseModel):
    """Result of visual regression comparison between two screenshot buffers."""

    diff_score: float = 0.0
    is_match: bool = True
    threshold: float = 0.01
    total_pixels: int = 0
    mismatched_pixels: int = 0
    diff_bounds: list[tuple[int, int, int, int]] = Field(default_factory=list)
    diff_image_bytes: bytes | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AccessibilityViolation(BaseModel):
    """Represents a single accessibility rule violation."""

    rule_id: str
    description: str
    impact: str = "moderate"
    node_role: str = ""
    node_name: str | None = None
    selector: str | None = None
    help_url: str | None = None


class AccessibilityAuditResult(BaseModel):
    """Consolidated report of accessibility inspection."""

    violations: list[AccessibilityViolation] = Field(default_factory=list)
    passes: int = 0
    total_checked: int = 0
    score: float = 100.0
    is_compliant: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
