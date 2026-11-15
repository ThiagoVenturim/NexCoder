from __future__ import annotations

from pathlib import Path
from typing import Any

from nexcoder_control.approval.target_gate import redact_secrets
from pydantic import Field

from nexcoder_security.agents.base import AgentAnalysisResult, AgentFinding, BaseSecurityAgent
from nexcoder_security.models import Finding, FindingCategory
from nexcoder_security.scanners.review_scanners import (
    DataLeakageScanner,
    GeneralSecurityScanner,
    PromptInjectionScanner,
    SQLInjectionScanner,
)


class DetailedAgentFinding(AgentFinding):
    """Extended agent finding with file:line location, rule_id, and concrete fix instructions."""

    rule_id: str = ""
    file_path: str = "general"
    line_start: int = 1
    location_ref: str = "general:1"
    how_to_fix: str = ""
    diff_patch: str | None = None


class SpecialistReviewResult(AgentAnalysisResult):
    """Structured review result from a domain-specific security agent."""

    domain: str = "security"
    detailed_findings: list[DetailedAgentFinding] = Field(default_factory=list)


def _extract_or_scan_findings(
    target: Any,
    scanner_cls: type[Any],
    category_filter: set[FindingCategory],
) -> list[Finding]:
    """Extract matching Findings from a list/ScanResult or scan a path/code target offline."""
    if isinstance(target, list):
        return [f for f in target if isinstance(f, Finding) and f.category in category_filter]
    if hasattr(target, "findings"):
        return [f for f in target.findings if isinstance(f, Finding) and f.category in category_filter]
    if isinstance(target, (str, Path)):
        path = Path(target)
        if path.exists():
            scanner = scanner_cls()
            return scanner.scan(path, force_offline_fallback=True).findings
    return []


def _to_detailed_findings(findings: list[Finding], default_category: str) -> list[DetailedAgentFinding]:
    detailed: list[DetailedAgentFinding] = []
    for f in findings:
        file_p = f.location.file_path if f.location else "general"
        line_no = f.location.line_start if f.location and f.location.line_start is not None else 1
        loc_ref = f"{file_p}:{line_no}"
        how_to_fix = f.how_to_fix
        diff_patch = f.remediation.diff_patch if f.remediation else None
        safe_desc = str(redact_secrets(f.description or f.title))

        detailed.append(
            DetailedAgentFinding(
                title=f.title,
                description=safe_desc,
                severity=f.severity.value,
                category=f.category.value or default_category,
                recommendation=how_to_fix,
                rule_id=f.rule_id,
                file_path=file_p,
                line_start=line_no,
                location_ref=loc_ref,
                how_to_fix=how_to_fix,
                diff_patch=diff_patch,
            )
        )
    return detailed


class PromptInjectionAgent(BaseSecurityAgent):
    """sec-prompt-injection: audits LLM inputs, system/user separation, external data boundaries, and tool calls."""

    def __init__(self) -> None:
        super().__init__(
            name="sec-prompt-injection",
            role=(
                "Specialist agent in LLM prompt injection defense, system/user role isolation, "
                "external data sanitization, and tool argument validation."
            ),
        )

    def analyze(self, target: Any, offline: bool = True) -> SpecialistReviewResult:
        findings = _extract_or_scan_findings(
            target,
            PromptInjectionScanner,
            {FindingCategory.PROMPT_INJECTION},
        )
        detailed = _to_detailed_findings(findings, "prompt_injection")
        return SpecialistReviewResult(
            agent_name=self.name,
            domain="prompt_injection",
            summary=f"Analyzed LLM prompt boundaries and tool calls: {len(detailed)} findings identified.",
            findings=list(detailed),
            detailed_findings=detailed,
            metadata={"total_findings": len(detailed)},
        )


class SQLInjectionAgent(BaseSecurityAgent):
    """sec-sql-injection: audits SQL query construction and ORM usage for injection risks."""

    def __init__(self) -> None:
        super().__init__(
            name="sec-sql-injection",
            role="Specialist agent in SQL parameterization, query safety, and ORM security review.",
        )

    def analyze(self, target: Any, offline: bool = True) -> SpecialistReviewResult:
        findings = _extract_or_scan_findings(
            target,
            SQLInjectionScanner,
            {FindingCategory.SQL_INJECTION},
        )
        detailed = _to_detailed_findings(findings, "sql_injection")
        return SpecialistReviewResult(
            agent_name=self.name,
            domain="sql_injection",
            summary=f"Analyzed SQL queries and ORM statements: {len(detailed)} findings identified.",
            findings=list(detailed),
            detailed_findings=detailed,
            metadata={"total_findings": len(detailed)},
        )


class DataLeakageAgent(BaseSecurityAgent):
    """sec-data-leakage: audits logs, API responses, HAR captures, reports, state dumps, and data egress for leaks."""

    def __init__(self) -> None:
        super().__init__(
            name="sec-data-leakage",
            role=(
                "Specialist agent in preventing credential, token, and PII leakage across logs, "
                "responses, HAR captures, serialized state, and outbound egress."
            ),
        )

    def analyze(self, target: Any, offline: bool = True) -> SpecialistReviewResult:
        findings = _extract_or_scan_findings(
            target,
            DataLeakageScanner,
            {FindingCategory.DATA_LEAKAGE, FindingCategory.SECRET},
        )
        detailed = _to_detailed_findings(findings, "data_leakage")
        return SpecialistReviewResult(
            agent_name=self.name,
            domain="data_leakage",
            summary=f"Analyzed logs, responses, state, and egress channels: {len(detailed)} findings identified.",
            findings=list(detailed),
            detailed_findings=detailed,
            metadata={"total_findings": len(detailed)},
        )


class AppSecGeneralAgent(BaseSecurityAgent):
    """sec-appsec-general: audits route authentication, CORS, constant-time token comparison, traversal, SSRF, shell."""

    def __init__(self) -> None:
        super().__init__(
            name="sec-appsec-general",
            role=(
                "Specialist agent in route authentication, fail-closed access control, CORS policy, "
                "constant-time token comparison, path traversal, SSRF, and command injection."
            ),
        )

    def analyze(self, target: Any, offline: bool = True) -> SpecialistReviewResult:
        findings = _extract_or_scan_findings(
            target,
            GeneralSecurityScanner,
            {FindingCategory.AUTH_SECURITY, FindingCategory.SAST},
        )
        detailed = _to_detailed_findings(findings, "auth_security")
        return SpecialistReviewResult(
            agent_name=self.name,
            domain="general_security",
            summary=f"Analyzed application security controls: {len(detailed)} findings identified.",
            findings=list(detailed),
            detailed_findings=detailed,
            metadata={"total_findings": len(detailed)},
        )
