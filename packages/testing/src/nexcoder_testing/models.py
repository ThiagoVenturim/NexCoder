"""Data models for multi-agent extreme application testing (nexcoder-testing)."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nexcoder_security.gate import GateVerdict
from nexcoder_security.models import Finding, Severity
from pydantic import BaseModel, Field, model_validator


class TestScope(enum.StrEnum):
    """Supported extreme testing scopes over an owned target application."""

    __test__ = False

    UNIT = "unit"
    SYSTEM = "system"
    DOM = "dom"
    API = "api"
    SECURITY = "security"

    @classmethod
    def all_scopes(cls) -> list[TestScope]:
        return [cls.UNIT, cls.SYSTEM, cls.DOM, cls.API, cls.SECURITY]


class APIEndpointSpec(BaseModel):
    """Specification of an HTTP API endpoint belonging to the user's target application."""

    method: str = "GET"
    path: str
    requires_auth: bool = False
    expected_status: int = 200
    request_schema: dict[str, str] = Field(default_factory=dict)
    valid_payload: dict[str, Any] | None = None
    expected_response_keys: list[str] = Field(default_factory=list)
    rate_limit_header: str | None = None


class DOMScreenSpec(BaseModel):
    """Specification of a UI screen/route in the user's target application."""

    name: str
    url_or_path: str
    html_content: str | None = None
    expected_selectors: list[str] = Field(default_factory=list)
    expected_texts: list[str] = Field(default_factory=list)


class SystemFlowSpec(BaseModel):
    """Specification of an end-to-end system or process flow to exercise."""

    name: str
    description: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)
    command: list[str] | None = None
    expected_exit_code: int = 0


class ExtremeTestConfig(BaseModel):
    """Configuration for an extreme testing run on an owned/authorized user target."""

    target_path: Path = Field(default_factory=lambda: Path("."))
    base_url: str | None = None
    num_agents: int = Field(default=3, ge=1, le=64)
    scopes: list[TestScope] = Field(default_factory=TestScope.all_scopes)
    offline: bool = True
    read_only: bool = True
    owned_target: bool = False
    authorized_by: str = "owner"
    approval_token: str | None = None
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1", "::1", "testserver"])
    endpoints: list[APIEndpointSpec] = Field(default_factory=list)
    screens: list[DOMScreenSpec] = Field(default_factory=list)
    system_flows: list[SystemFlowSpec] = Field(default_factory=list)
    valid_auth_token: str = "test-owner-valid-token"
    timeout_seconds: float = 15.0

    @model_validator(mode="after")
    def _validate_config(self) -> ExtremeTestConfig:
        if self.num_agents < 1:
            raise ValueError("num_agents must be >= 1")
        if not self.scopes:
            self.scopes = TestScope.all_scopes()
        return self


class TestCaseExecution(BaseModel):
    """Outcome of a single generated or executed test case."""

    __test__ = False

    test_id: str
    scope: TestScope
    name: str
    target: str
    passed: bool
    duration_ms: float = 0.0
    assertions_checked: int = 1
    error_message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class GeneratedTestArtifact(BaseModel):
    """Executable test or page object artifact synthesized from target inspection."""

    name: str
    scope: TestScope
    file_name: str
    language: str = "python"
    content: str
    target_reference: str = ""


class AgentWorkSlice(BaseModel):
    """Slice of testing work assigned by the orchestrator to a single worker agent."""

    agent_id: str
    agent_index: int
    scopes: list[TestScope] = Field(default_factory=list)
    module_paths: list[str] = Field(default_factory=list)
    endpoints: list[APIEndpointSpec] = Field(default_factory=list)
    screens: list[DOMScreenSpec] = Field(default_factory=list)
    system_flows: list[SystemFlowSpec] = Field(default_factory=list)
    scanners: list[str] = Field(default_factory=list)


class AgentExecutionReport(BaseModel):
    """Report produced by a single worker agent after executing its assigned slice."""

    agent_id: str
    scopes: list[TestScope] = Field(default_factory=list)
    test_cases: list[TestCaseExecution] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    artifacts: list[GeneratedTestArtifact] = Field(default_factory=list)
    duration_ms: float = 0.0
    summary: str = ""

    @property
    def total_tests(self) -> int:
        return len(self.test_cases)

    @property
    def passed_tests(self) -> int:
        return sum(1 for tc in self.test_cases if tc.passed)

    @property
    def failed_tests(self) -> int:
        return sum(1 for tc in self.test_cases if not tc.passed)


class ScopeSummary(BaseModel):
    """Aggregated metrics for one testing scope."""

    scope: TestScope
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    findings_count: int = 0
    artifacts_count: int = 0


class ExtremeTestReport(BaseModel):
    """Consolidated report from the multi-agent extreme testing orchestrator."""

    target: str
    authorized_by: str
    ownership: str = "owned"
    offline: bool = True
    num_agents: int
    scopes_executed: list[TestScope] = Field(default_factory=list)
    agent_assignments: list[AgentWorkSlice] = Field(default_factory=list)
    agent_reports: list[AgentExecutionReport] = Field(default_factory=list)
    scope_summaries: dict[str, ScopeSummary] = Field(default_factory=dict)
    test_cases: list[TestCaseExecution] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    artifacts: list[GeneratedTestArtifact] = Field(default_factory=list)
    security_gate_verdict: GateVerdict | None = None
    executive_summary: str = ""
    audit_event_ids: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_ms: float = 0.0

    @property
    def total_tests(self) -> int:
        return len(self.test_cases)

    @property
    def passed_tests(self) -> int:
        return sum(1 for tc in self.test_cases if tc.passed)

    @property
    def failed_tests(self) -> int:
        return sum(1 for tc in self.test_cases if not tc.passed)

    def findings_by_severity(self, severity: Severity) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity and not f.is_suppressed]

    def has_critical_or_high(self) -> bool:
        return any(f.severity in (Severity.CRITICAL, Severity.HIGH) and not f.is_suppressed for f in self.findings)

    def to_markdown(self) -> str:
        """Render the consolidated report as clean, structured Markdown."""
        lines: list[str] = [
            f"# Extreme Application Test Report: `{self.target}`",
            "",
            f"- **Authorized By**: `{self.authorized_by}` ({self.ownership})",
            f"- **Execution Mode**: `{'offline' if self.offline else 'online'}`",
            f"- **Configured Agents**: `{self.num_agents}`",
            f"- **Scopes Executed**: `{', '.join(s.value for s in self.scopes_executed)}`",
            f"- **Total Tests Executed**: `{self.total_tests}` "
            f"(`{self.passed_tests}` passed, `{self.failed_tests}` failed)",
            f"- **Total Findings**: `{len(self.findings)}` "
            f"(Critical: `{len(self.findings_by_severity(Severity.CRITICAL))}`, "
            f"High: `{len(self.findings_by_severity(Severity.HIGH))}`, "
            f"Medium: `{len(self.findings_by_severity(Severity.MEDIUM))}`, "
            f"Low: `{len(self.findings_by_severity(Severity.LOW))}`)",
            f"- **Generated Test Artifacts**: `{len(self.artifacts)}`",
            "",
        ]

        if self.executive_summary:
            lines.extend(["## Executive Summary", "", self.executive_summary, ""])

        lines.extend(
            [
                "## Scope Breakdown",
                "",
                "| Scope | Total Tests | Passed | Failed | Findings | Artifacts |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for scope_key, summary in self.scope_summaries.items():
            lines.append(
                f"| `{scope_key}` | {summary.total_tests} | {summary.passed_tests} | "
                f"{summary.failed_tests} | {summary.findings_count} | {summary.artifacts_count} |"
            )
        lines.append("")

        lines.extend(
            [
                "## Multi-Agent Work Distribution",
                "",
                "| Agent ID | Assigned Scopes | Tests Run | Passed | Failed | Findings |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for rep in self.agent_reports:
            scopes_str = ", ".join(s.value for s in rep.scopes) or "idle"
            lines.append(
                f"| `{rep.agent_id}` | {scopes_str} | {rep.total_tests} | "
                f"{rep.passed_tests} | {rep.failed_tests} | {len(rep.findings)} |"
            )
        lines.append("")

        if self.security_gate_verdict is not None:
            lines.extend(
                [
                    "## Security Gate Verdict",
                    "",
                    f"- **Passed**: `{self.security_gate_verdict.passed}`",
                    f"- **Summary**: {self.security_gate_verdict.summary}",
                ]
            )
            for reason in self.security_gate_verdict.reasons:
                lines.append(f"  - {reason}")
            lines.append("")

        if self.findings:
            lines.extend(["## Findings and Remediation Suggestions", ""])
            for idx, finding in enumerate(self.findings, start=1):
                loc_str = "application"
                if finding.location:
                    loc_str = finding.location.file_path
                    if finding.location.line_start:
                        loc_str += f":{finding.location.line_start}"
                lines.append(
                    f"### {idx}. [{finding.severity.value.upper()}] {finding.title} (`{finding.rule_id}`)"
                )
                lines.append(f"- **Scanner / Runner**: `{finding.scanner}`")
                lines.append(f"- **Category**: `{finding.category.value}`")
                lines.append(f"- **Location**: `{loc_str}`")
                if finding.description:
                    lines.append(f"- **Description**: {finding.description}")
                if finding.remediation:
                    lines.append(f"- **Suggested Fix**: {finding.remediation.summary}")
                lines.append("")

        return "\n".join(lines)
