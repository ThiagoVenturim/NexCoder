"""Models for security and quality test campaign orchestration, control plane, and reporting."""

from __future__ import annotations

import enum
import html as html_lib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from nexcoder_security.models import Severity


class TestType(enum.StrEnum):
    """Supported test types for campaign execution."""

    __test__ = False

    UNIT = "unit"
    SYSTEM = "system"
    PROCESS = "process"
    DOM = "dom"
    API = "api"
    SECURITY = "security"

    @classmethod
    def from_str(cls, val: str) -> TestType:
        norm = val.strip().lower()
        mapping = {
            "unit": cls.UNIT,
            "unitario": cls.UNIT,
            "system": cls.SYSTEM,
            "sistema": cls.SYSTEM,
            "process": cls.PROCESS,
            "processo": cls.PROCESS,
            "dom": cls.DOM,
            "ui": cls.DOM,
            "api": cls.API,
            "endpoint": cls.API,
            "security": cls.SECURITY,
            "seguranca": cls.SECURITY,
        }
        if norm not in mapping:
            valid = ", ".join(t.value for t in cls)
            raise ValueError(f"Unknown test type '{val}'. Valid types are: {valid}")
        return mapping[norm]


class CampaignStatus(enum.StrEnum):
    """Lifecycle statuses for a security test campaign."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    REJECTED = "rejected"
    BUDGET_EXCEEDED = "budget_exceeded"
    FAILED = "failed"


class CampaignBudget(BaseModel):
    """Spending, duration and request constraints for a test campaign."""

    max_cost_usd: float = Field(default=5.0, ge=0.0, description="Spending limit in USD.")
    max_duration_seconds: float = Field(default=120.0, ge=1.0, description="Execution timeout in seconds.")
    max_requests: int = Field(default=1000, ge=1, description="Maximum test requests allowed.")
    currency: str = Field(default="USD", description="Currency identifier.")


class CampaignConfig(BaseModel):
    """Specification of target, scope, agent capacity, test types, and budget."""

    campaign_id: str = Field(default_factory=lambda: f"camp_{uuid.uuid4().hex[:12]}")
    target: str = Field(..., description="Target repository path, directory, or endpoint URL.")
    allowed_scope: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Allowed paths, submodules, or resource patterns.",
    )
    agent_count: int = Field(default=3, ge=1, le=10, description="Number of parallel testing agents.")
    test_types: list[TestType] = Field(
        default_factory=lambda: [TestType.UNIT, TestType.API, TestType.SECURITY],
        description="List of test types to exercise.",
    )
    budget: CampaignBudget = Field(default_factory=CampaignBudget, description="Budget limits.")
    owned_target: bool = Field(default=False, description="Confirm target is owned by operator.")
    authorized_by: str = Field(default="", description="Identity of authorizer/owner.")
    authorization_document: Any | None = Field(default=None, description="Signed authorization document.")
    require_signed_document: bool = Field(default=False, description="Require cryptographic signature.")
    dry_run: bool = Field(default=True, description="Enforce offline deterministic testing.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestFinding(BaseModel):
    """Specific vulnerability, defect, or compliance gap found during a campaign."""

    __test__ = False

    id: str = Field(default_factory=lambda: f"TF-{uuid.uuid4().hex[:8].upper()}")
    campaign_id: str
    test_type: TestType
    agent_id: str
    title: str
    severity: Severity = Severity.MEDIUM
    category: str = "general"
    target_ref: str = "general:1"
    description: str = ""
    steps_to_reproduce: list[str] = Field(default_factory=list)
    reproduction_snippet: str | None = None
    remediation_suggestion: str = ""
    diff_patch: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def format_reproduction_guide(self) -> str:
        """Format step-by-step reproduction instructions."""
        if not self.steps_to_reproduce:
            return "No reproduction steps provided."
        lines = [f"{idx}. {step}" for idx, step in enumerate(self.steps_to_reproduce, start=1)]
        if self.reproduction_snippet:
            lines.append("\nReproduction snippet:")
            lines.append("```")
            lines.append(self.reproduction_snippet)
            lines.append("```")
        return "\n".join(lines)


class AgentExecutionResult(BaseModel):
    """Summary of tests executed by an individual specialist test agent."""

    agent_id: str
    test_type: TestType
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    duration_seconds: float = 0.0
    cost_usd: float = 0.0
    findings: list[TestFinding] = Field(default_factory=list)
    status: str = "success"
    error_message: str | None = None


class CampaignReport(BaseModel):
    """Consolidated test campaign report with findings, reproduction steps, and fixes."""

    campaign_id: str
    target: str
    status: CampaignStatus
    authorized_by: str
    authorized_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ownership: str = "owned"
    scope: list[str] = Field(default_factory=list)
    agent_count: int = 1
    test_types: list[TestType] = Field(default_factory=list)
    budget_limit_usd: float = 0.0
    actual_cost_usd: float = 0.0
    duration_seconds: float = 0.0
    total_tests_run: int = 0
    total_passed: int = 0
    total_failed: int = 0
    severity_counts: dict[str, int] = Field(default_factory=dict)
    findings: list[TestFinding] = Field(default_factory=list)
    agent_results: list[AgentExecutionResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to standard serializable dictionary."""
        return json.loads(self.model_dump_json())

    def to_json(self, indent: int = 2) -> str:
        """Export report as formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        """Export report as structured Markdown document."""
        lines = [
            f"# Security and Quality Test Campaign Report: {self.campaign_id}",
            "",
            "## Summary",
            f"- **Target**: `{self.target}`",
            f"- **Status**: `{self.status.value.upper()}`",
            f"- **Authorized By**: {self.authorized_by} ({self.ownership})",
            f"- **Authorized At**: {self.authorized_at.isoformat()}",
            f"- **Test Types**: {', '.join(t.value for t in self.test_types)}",
            f"- **Agents**: {self.agent_count}",
            f"- **Duration**: {self.duration_seconds:.2f}s (budget: max {self.budget_limit_usd} USD)",
            f"- **Cost**: ${self.actual_cost_usd:.4f} USD",
            f"- **Total Tests Run**: {self.total_tests_run} (Passed: {self.total_passed}, Failed: {self.total_failed})",
            "",
            "## Findings by Severity",
        ]

        for sev in ("critical", "high", "medium", "low", "info"):
            cnt = self.severity_counts.get(sev, 0)
            lines.append(f"- **{sev.capitalize()}**: {cnt}")

        lines.append("")
        lines.append("## Detailed Findings")

        if not self.findings:
            lines.append("No defects or vulnerabilities detected.")
        else:
            for idx, finding in enumerate(self.findings, start=1):
                lines.extend(
                    [
                        f"### {idx}. [{finding.severity.value.upper()}] {finding.title} ({finding.id})",
                        f"- **Type**: `{finding.test_type.value}` | **Category**: `{finding.category}`",
                        f"- **Location**: `{finding.target_ref}` | **Agent**: `{finding.agent_id}`",
                        f"- **Description**: {finding.description}",
                        "",
                        "#### Steps to Reproduce",
                    ]
                )
                if finding.steps_to_reproduce:
                    for s_idx, step in enumerate(finding.steps_to_reproduce, start=1):
                        lines.append(f"{s_idx}. {step}")
                else:
                    lines.append("Direct source code analysis or contract validation.")

                if finding.reproduction_snippet:
                    lines.append("")
                    lines.append("```python")
                    lines.append(finding.reproduction_snippet)
                    lines.append("```")

                lines.extend(
                    [
                        "",
                        "#### Remediation Suggestion",
                        finding.remediation_suggestion or "Apply defensive validation and contract checks.",
                    ]
                )

                if finding.diff_patch:
                    lines.extend(
                        [
                            "",
                            "#### Suggested Fix Patch",
                            "```diff",
                            finding.diff_patch,
                            "```",
                        ]
                    )
                lines.append("")

        lines.extend(
            [
                "## Agent Execution Metrics",
                "| Agent ID | Test Type | Run | Passed | Failed | Duration | Cost | Status |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for res in self.agent_results:
            lines.append(
                f"| {res.agent_id} | {res.test_type.value} | {res.tests_run} | {res.tests_passed} | "
                f"{res.tests_failed} | {res.duration_seconds:.2f}s | ${res.cost_usd:.4f} | {res.status} |"
            )
        lines.append("")
        return "\n".join(lines)

    def to_html(self) -> str:
        """Export report as self-contained HTML report with NexDash styling."""
        esc = html_lib.escape
        escaped_target = esc(self.target)
        escaped_status = esc(self.status.value.upper())

        status_class = "status-ok"
        if self.status in (CampaignStatus.FAILED, CampaignStatus.REJECTED):
            status_class = "status-danger"
        elif self.status == CampaignStatus.BUDGET_EXCEEDED:
            status_class = "status-warning"

        findings_rows = []
        for f in self.findings:
            sev_class = esc(f"badge-{f.severity.value}")
            steps_html = "<ol>" + "".join(f"<li>{esc(str(s))}</li>" for s in f.steps_to_reproduce) + "</ol>"
            snippet_html = f"<pre><code>{esc(f.reproduction_snippet)}</code></pre>" if f.reproduction_snippet else ""
            findings_rows.append(
                f"""<tr>
                    <td><code>{esc(str(f.id))}</code></td>
                    <td><span class="badge {sev_class}">{esc(f.severity.value.upper())}</span></td>
                    <td><b>{esc(f.title)}</b><br><small>{esc(f.description)}</small></td>
                    <td><code>{esc(f.target_ref)}</code></td>
                    <td>{steps_html}{snippet_html}</td>
                    <td>{esc(f.remediation_suggestion)}</td>
                </tr>"""
            )

        findings_table = "\n".join(findings_rows) if findings_rows else "<tr><td colspan='6'>No findings</td></tr>"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NexCoder Campaign Report: {esc(str(self.campaign_id))}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0; padding: 24px; background: #0f172a; color: #f8fafc;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  .header {{
    display: flex; justify-content: space-between; align-items: center;
    border-bottom: 1px solid #334155; padding-bottom: 16px; margin-bottom: 24px;
  }}
  .status-badge {{
    font-size: 14px; padding: 6px 14px; border-radius: 9999px;
    font-weight: 700; text-transform: uppercase;
  }}
  .status-ok {{ background: #065f46; color: #34d399; }}
  .status-warning {{ background: #78350f; color: #fbbf24; }}
  .status-danger {{ background: #7f1d1d; color: #f87171; }}
  .grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px; margin-bottom: 24px;
  }}
  .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; }}
  .card h4 {{ margin: 0 0 8px 0; color: #94a3b8; font-size: 13px; text-transform: uppercase; }}
  .card p {{ margin: 0; font-size: 22px; font-weight: 700; color: #f8fafc; }}
  table {{
    width: 100%; border-collapse: collapse; margin-top: 16px;
    background: #1e293b; border-radius: 8px; overflow: hidden;
  }}
  th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid #334155; font-size: 14px; }}
  th {{ background: #0f172a; color: #94a3b8; font-size: 12px; text-transform: uppercase; }}
  .badge {{ padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; }}
  .badge-critical {{ background: #7f1d1d; color: #fca5a5; }}
  .badge-high {{ background: #991b1b; color: #fecaca; }}
  .badge-medium {{ background: #854d0e; color: #fef08a; }}
  .badge-low {{ background: #1e3a8a; color: #bfdbfe; }}
  .badge-info {{ background: #1f2937; color: #d1d5db; }}
  pre {{ background: #0f172a; padding: 8px; border-radius: 4px; overflow-x: auto; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1 style="margin:0 0 8px 0;">Test Campaign: {esc(str(self.campaign_id))}</h1>
      <span style="color:#94a3b8;">
        Target: <code>{escaped_target}</code> | Authorized by: <b>{esc(self.authorized_by)}</b>
      </span>
    </div>
    <span class="status-badge {status_class}">{escaped_status}</span>
  </div>

  <div class="grid">
    <div class="card"><h4>Tests Run</h4><p>{self.total_tests_run}</p></div>
    <div class="card"><h4>Passed</h4><p style="color:#34d399;">{self.total_passed}</p></div>
    <div class="card"><h4>Failed</h4><p style="color:#f87171;">{self.total_failed}</p></div>
    <div class="card"><h4>Total Findings</h4><p>{len(self.findings)}</p></div>
    <div class="card"><h4>Duration</h4><p>{self.duration_seconds:.2f}s</p></div>
    <div class="card"><h4>Cost (USD)</h4><p>${self.actual_cost_usd:.4f}</p></div>
  </div>

  <h2>Findings, Reproduction & Remediation</h2>
  <table>
    <thead>
      <tr>
        <th>ID</th>
        <th>Severity</th>
        <th>Title</th>
        <th>Target Ref</th>
        <th>Steps to Reproduce</th>
        <th>Remediation Suggestion</th>
      </tr>
    </thead>
    <tbody>
      {findings_table}
    </tbody>
  </table>
</div>
</body>
</html>
"""
        return html

    def export(self, file_path: str | Path, format: str = "json") -> str:
        """Export report to disk in the chosen format (json, markdown, html)."""
        path = Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        fmt = format.lower()
        if fmt in ("json", "js"):
            content = self.to_json()
        elif fmt in ("markdown", "md"):
            content = self.to_markdown()
        elif fmt in ("html", "htm"):
            content = self.to_html()
        else:
            raise ValueError(f"Unsupported export format '{format}'. Use 'json', 'markdown', or 'html'.")
        path.write_text(content, encoding="utf-8")
        return str(path)
