from __future__ import annotations

from pydantic import BaseModel, Field

from faccoder_security.models import Finding


class GatePolicy(BaseModel):
    name: str = "default-production-gate"
    max_critical: int = 0
    max_high: int = 0
    max_medium: int | None = None
    allowed_cves: list[str] = Field(default_factory=list)
    allowed_rules: list[str] = Field(default_factory=list)
    block_on_secrets: bool = True
    require_sbom: bool = False


class GateVerdict(BaseModel):
    passed: bool
    policy_name: str
    total_findings_evaluated: int
    blocking_findings: list[Finding] = Field(default_factory=list)
    summary: str
    reasons: list[str] = Field(default_factory=list)
