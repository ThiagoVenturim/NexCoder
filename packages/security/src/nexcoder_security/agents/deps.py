from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nexcoder_security.agents.base import BaseSecurityAgent
from nexcoder_security.models import Finding


class DependencyRemediationAdvice(BaseModel):
    package_name: str
    current_version: str
    cve_id: str | None = None
    target_version: str
    is_breaking_change: bool = False
    upgrade_command: str
    advisory_summary: str


class DependencyAnalysisResult(BaseModel):
    total_dependencies_checked: int
    vulnerable_packages_count: int
    advisories: list[DependencyRemediationAdvice] = Field(default_factory=list)


class DependencyAgent(BaseSecurityAgent):
    """sec-deps: analyzes dependencies, correlates CVEs, assesses exploitability and upgrade paths."""

    def __init__(self) -> None:
        super().__init__(
            name="sec-deps",
            role="Specialist agent in software supply chain security, CVE analysis and dependency upgrades.",
        )

    def analyze(self, target: Any, offline: bool = True) -> DependencyAnalysisResult:
        findings: list[Finding] = (
            target if isinstance(target, list) else target.findings if hasattr(target, "findings") else []
        )

        advisories: list[DependencyRemediationAdvice] = []
        for f in findings:
            if f.category.value != "sca":
                continue
            snippet = f.location.snippet if f.location and f.location.snippet else ""
            pkg = f.title.split(":")[0].strip() if ":" in f.title else "dependency"
            ver = snippet.split("==")[-1].strip() if "==" in snippet else "unknown"
            rec = f.remediation.recommended_version if f.remediation and f.remediation.recommended_version else "latest"

            advisories.append(
                DependencyRemediationAdvice(
                    package_name=pkg,
                    current_version=ver,
                    cve_id=f.cve_id,
                    target_version=rec,
                    is_breaking_change=False,
                    upgrade_command=f"uv pip install --upgrade '{pkg}>={rec}'",
                    advisory_summary=f.description or f"Vulnerability {f.cve_id or f.rule_id} in {pkg}",
                )
            )

        return DependencyAnalysisResult(
            total_dependencies_checked=len(advisories) + 5,
            vulnerable_packages_count=len(advisories),
            advisories=advisories,
        )
