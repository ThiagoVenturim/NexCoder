"""Security scan monitor and vulnerability baseline diffing engine."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class SecurityVulnerability(BaseModel):
    id: str  # e.g., "GHSA-xxxx" or "CVE-2026-xxxx"
    package: str
    installed_version: str
    fixed_version: str | None = None
    severity: Severity = Severity.MEDIUM
    description: str = ""


class SecurityBaselineDiff(BaseModel):
    new_vulnerabilities: list[SecurityVulnerability] = Field(default_factory=list)
    resolved_vulnerabilities: list[SecurityVulnerability] = Field(default_factory=list)
    outdated_packages: list[str] = Field(default_factory=list)
    critical_or_high_count: int = 0
    requires_immediate_action: bool = False
    summary_markdown: str = ""


class SecurityWatcher:
    """Watches periodic security scan outputs and generates diff alerts against baseline."""

    def diff_scans(
        self,
        baseline: list[SecurityVulnerability],
        current: list[SecurityVulnerability],
        outdated_packages: list[str] | None = None,
    ) -> SecurityBaselineDiff:
        """Compare current scan against baseline and compute risk assessment."""
        base_map = {v.id: v for v in baseline}
        curr_map = {v.id: v for v in current}

        new_vulns = [v for vid, v in curr_map.items() if vid not in base_map]
        resolved = [v for vid, v in base_map.items() if vid not in curr_map]

        crit_high = sum(1 for v in new_vulns if v.severity in (Severity.CRITICAL, Severity.HIGH))
        immediate = crit_high > 0

        outdated = outdated_packages or []

        lines = [
            "### Continuous Security Scan Diff",
            f"- **New Vulnerabilities**: {len(new_vulns)}",
            f"- **Resolved Vulnerabilities**: {len(resolved)}",
            f"- **Outdated Dependencies**: {len(outdated)}",
            f"- **Critical / High Count**: {crit_high}",
            f"- **Immediate Action Required**: {'YES' if immediate else 'NO'}",
        ]
        if new_vulns:
            lines.append("- **New Vulnerability Details**:")
            for v in new_vulns:
                fix_ver = v.fixed_version or "N/A"
                lines.append(f"  - [{v.severity}] {v.id} in {v.package} ({v.installed_version}) -> Fix: {fix_ver}")

        return SecurityBaselineDiff(
            new_vulnerabilities=new_vulns,
            resolved_vulnerabilities=resolved,
            outdated_packages=outdated,
            critical_or_high_count=crit_high,
            requires_immediate_action=immediate,
            summary_markdown="\n".join(lines),
        )
