from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(enum.StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def level(self) -> int:
        levels = {
            Severity.INFO: 0,
            Severity.LOW: 1,
            Severity.MEDIUM: 2,
            Severity.HIGH: 3,
            Severity.CRITICAL: 4,
        }
        return levels[self]

    def __ge__(self, other: Any) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.level >= other.level

    def __gt__(self, other: Any) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.level > other.level

    def __le__(self, other: Any) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.level <= other.level

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.level < other.level

    @classmethod
    def from_str(cls, val: str) -> Severity:
        normalized = val.strip().lower()
        mapping = {
            "critical": cls.CRITICAL,
            "fatal": cls.CRITICAL,
            "high": cls.HIGH,
            "error": cls.HIGH,
            "medium": cls.MEDIUM,
            "moderate": cls.MEDIUM,
            "warning": cls.MEDIUM,
            "low": cls.LOW,
            "minor": cls.LOW,
            "info": cls.INFO,
            "information": cls.INFO,
            "note": cls.INFO,
        }
        return mapping.get(normalized, cls.MEDIUM)


class FindingCategory(enum.StrEnum):
    SAST = "sast"
    SCA = "sca"
    SECRET = "secret"
    CONTAINER = "container"
    IAC = "iac"
    THREAT = "threat"
    COMPLIANCE = "compliance"


class Location(BaseModel):
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None
    snippet: str | None = None


class Remediation(BaseModel):
    summary: str
    diff_patch: str | None = None
    recommended_version: str | None = None
    references: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    id: str
    scanner: str
    rule_id: str
    title: str
    description: str = ""
    severity: Severity = Severity.MEDIUM
    category: FindingCategory = FindingCategory.SAST
    location: Location | None = None
    cve_id: str | None = None
    cwe_ids: list[str] = Field(default_factory=list)
    remediation: Remediation | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)
    is_suppressed: bool = False
    suppression_reason: str | None = None


class ScanMetadata(BaseModel):
    scanner: str
    version: str = "unknown"
    target_path: str
    duration_seconds: float = 0.0
    timestamp: str = ""
    success: bool = True
    error_message: str | None = None
    is_fallback: bool = False


class SBOMComponent(BaseModel):
    name: str
    version: str
    purl: str | None = None
    licenses: list[str] = Field(default_factory=list)
    component_type: str = "library"
    cpe: str | None = None


class SBOMDocument(BaseModel):
    format: str = "cyclonedx"
    schema_version: str = "1.5"
    components: list[SBOMComponent] = Field(default_factory=list)
    raw_content: str = ""


class ScanResult(BaseModel):
    scanner: str
    target_path: str
    findings: list[Finding] = Field(default_factory=list)
    metadata: ScanMetadata | None = None
    errors: list[str] = Field(default_factory=list)
    sbom: SBOMDocument | None = None
    fallbacks: list[str] = Field(default_factory=list)

    def by_severity(self, severity: Severity) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity and not f.is_suppressed]

    def has_high_or_critical(self) -> bool:
        return any(f.severity in (Severity.CRITICAL, Severity.HIGH) and not f.is_suppressed for f in self.findings)

    def has_errors(self) -> bool:
        if self.errors:
            return True
        if self.metadata and not self.metadata.success:
            return True
        return False

    def has_fallbacks(self) -> bool:
        if self.fallbacks:
            return True
        if self.metadata and self.metadata.is_fallback:
            return True
        return False

    def total_findings(self, include_suppressed: bool = False) -> int:
        if include_suppressed:
            return len(self.findings)
        return len([f for f in self.findings if not f.is_suppressed])
