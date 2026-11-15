from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from nexcoder_control.approval import (
    TargetAuthorizationGate,
    TargetAuthorizationRecord,
    redact_secrets,
)
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from pydantic import BaseModel, Field, model_validator

from nexcoder_security.agents.fixer import SecurityFixerAgent, SurgicalPatch
from nexcoder_security.agents.review_agents import (
    AppSecGeneralAgent,
    DataLeakageAgent,
    PromptInjectionAgent,
    SpecialistReviewResult,
    SQLInjectionAgent,
)
from nexcoder_security.gate.evaluator import SecurityGateEvaluator
from nexcoder_security.gate.policy import GatePolicy, GateVerdict
from nexcoder_security.models import Finding
from nexcoder_security.monitor import (
    MonitorInspectionResult,
    RuntimeMonitorConfig,
    RuntimeSecurityMonitor,
)
from nexcoder_security.scanners.engine import MultiScannerEngine

DEFAULT_REVIEW_SCANNERS = [
    "prompt-injection",
    "sql-injection",
    "data-leakage",
    "general-security",
]

_EXPLOIT_PAYLOAD_MARKERS = re.compile(
    r"(?i)(?:<script\b[^>]*>.*?</script>|;\s*rm\s+-rf\s+/|'\s*UNION\s+SELECT\s+NULL|--\s*exploit_poc)",
)


def sanitize_for_responsible_disclosure(text: str) -> str:
    """Redact secrets and strip weaponized exploit strings for responsible disclosure."""
    redacted = str(redact_secrets(text))
    return _EXPLOIT_PAYLOAD_MARKERS.sub("[REDACTED_PAYLOAD]", redacted)


class DisclosurePolicy(BaseModel):
    """Responsible disclosure policy governing security review outputs."""

    mode: Literal["responsible"] = "responsible"
    publish_exploit: bool = False
    private_channel_only: bool = True
    oss_contribution_mode: bool = False
    security_contact: str = "SECURITY.md / private security advisory"

    @model_validator(mode="after")
    def _enforce_no_exploit(self) -> DisclosurePolicy:
        if self.publish_exploit:
            raise ValueError(
                "Responsible disclosure policy strictly forbids publishing exploits (publish_exploit=True)."
            )
        return self


class ReviewFindingItem(BaseModel):
    """Actionable security review finding with file:line, severity, and remediation."""

    id: str
    rule_id: str
    title: str
    category: str
    severity: str
    file_path: str
    line: int
    location: str
    description: str
    how_to_fix: str
    diff_patch: str | None = None
    cwe_ids: list[str] = Field(default_factory=list)


class SecurityReviewReport(BaseModel):
    """Consolidated report from the security review pipeline."""

    target_path: str
    authorized_by: str
    ownership: str = "owned"
    disclosure_mode: Literal["responsible"] = "responsible"
    exploit_published: bool = False
    oss_contribution_mode: bool = False
    disclosure_guidance: str = (
        "Responsible disclosure enforced: report findings defensively to the owner or private security channel; "
        "never publish active exploit payloads."
    )
    total_findings: int = 0
    severity_counts: dict[str, int] = Field(default_factory=dict)
    category_counts: dict[str, int] = Field(default_factory=dict)
    findings: list[ReviewFindingItem] = Field(default_factory=list)
    passed_gate: bool = True
    gate_verdict: GateVerdict
    specialist_reports: dict[str, SpecialistReviewResult] = Field(default_factory=dict)
    patches: list[SurgicalPatch] = Field(default_factory=list)
    monitor_enabled: bool = False
    monitor_inspections: list[MonitorInspectionResult] = Field(default_factory=list)

    def to_markdown(self) -> str:
        """Render a responsible-disclosure Markdown security review report."""
        lines = [
            f"# Security Review Report: {Path(self.target_path).name or self.target_path}",
            "",
            f"- **Target**: `{self.target_path}`",
            f"- **Authorized By**: `{self.authorized_by}` ({self.ownership})",
            f"- **Gate Verdict**: `{'PASSED' if self.passed_gate else 'BLOCKED'}`",
            f"- **Disclosure Mode**: `{self.disclosure_mode}` (Exploit published: `{self.exploit_published}`)",
            f"- **Total Findings**: `{self.total_findings}`",
            "",
            "## Findings (file:line, severity, remediation)",
            "",
        ]
        if not self.findings:
            lines.append("No security findings detected.")
        else:
            for idx, item in enumerate(self.findings, start=1):
                lines.append(
                    f"{idx}. **[{item.severity.upper()}] {item.title}** (`{item.location}`, rule `{item.rule_id}`)"
                )
                lines.append(f"   - **Category**: `{item.category}`")
                lines.append(f"   - **Issue**: {item.description}")
                lines.append(f"   - **How to Fix**: {item.how_to_fix}")
        lines.append("")
        lines.append("## Responsible Disclosure Notice")
        lines.append(self.disclosure_guidance)
        return "\n".join(lines) + "\n"


class SecurityReviewEngine:
    """Orchestrates authorized security reviews across prompt injection, SQLi, data leakage, and general security."""

    def __init__(
        self,
        *,
        target_gate: TargetAuthorizationGate | None = None,
        audit_log: AppendOnlyAuditLog | None = None,
        monitor: RuntimeSecurityMonitor | None = None,
        disclosure_policy: DisclosurePolicy | None = None,
    ) -> None:
        if target_gate is not None:
            self.target_gate = target_gate
            self.audit_log = audit_log if audit_log is not None else target_gate.audit_log
        else:
            self.audit_log = audit_log if audit_log is not None else AppendOnlyAuditLog()
            self.target_gate = TargetAuthorizationGate(audit_log=self.audit_log)

        self.scanner_engine = MultiScannerEngine(target_gate=self.target_gate, audit_log=self.audit_log)
        self.monitor = monitor
        self.disclosure_policy = disclosure_policy or DisclosurePolicy()
        self.specialists = {
            "prompt_injection": PromptInjectionAgent(),
            "sql_injection": SQLInjectionAgent(),
            "data_leakage": DataLeakageAgent(),
            "general_security": AppSecGeneralAgent(),
        }
        self.fixer = SecurityFixerAgent()
        self.gate_evaluator = SecurityGateEvaluator()

    def authorize_target(
        self,
        target_path: str | Path,
        authorized_by: str = "owner",
        metadata: dict[str, Any] | None = None,
    ) -> TargetAuthorizationRecord:
        """Mark a target path as owned/authorized for security review."""
        return self.target_gate.mark_owned_target(
            target=target_path,
            authorized_by=authorized_by,
            mode="security_review",
            metadata=metadata,
        )

    def review(
        self,
        target_path: str | Path,
        *,
        owned_target: bool = False,
        authorized_by: str = "owner",
        approval_token: str | None = None,
        include_standard_scanners: bool = False,
        enabled_scanners: list[str] | None = None,
        force_offline: bool = True,
        gate_policy: GatePolicy | None = None,
        enable_runtime_monitor: bool = False,
        runtime_samples: list[dict[str, Any]] | None = None,
        oss_contribution_mode: bool = False,
    ) -> SecurityReviewReport:
        """Execute full security review over an owned or authorized target."""
        # 1. Verify target ownership/authorization via control-plane gate
        auth_record = self.target_gate.verify_target(
            target=target_path,
            mode="security_review",
            owned_target=owned_target,
            authorized_by=authorized_by,
            approval_token=approval_token,
            metadata={
                "oss_contribution_mode": oss_contribution_mode,
                "disclosure_mode": self.disclosure_policy.mode,
            },
        )

        # 2. Select scanners
        if enabled_scanners is not None:
            scanners_to_run = enabled_scanners
        elif include_standard_scanners:
            scanners_to_run = list(self.scanner_engine.scanners.keys())
        else:
            scanners_to_run = list(DEFAULT_REVIEW_SCANNERS)

        scan_result = self.scanner_engine.scan(
            target_path=target_path,
            enabled_scanners=scanners_to_run,
            force_offline=force_offline,
            owned_target=True,
            authorized_by=auth_record.authorized_by,
        )

        # 3. Run specialist agents and surgical fixer
        specialist_reports: dict[str, SpecialistReviewResult] = {}
        for key, agent in self.specialists.items():
            specialist_reports[key] = agent.analyze(scan_result.findings, offline=force_offline)

        fixer_result = self.fixer.analyze(scan_result.findings, offline=force_offline)

        # 4. Optional runtime monitor inspection
        active_monitor = self.monitor
        if active_monitor is None and enable_runtime_monitor:
            active_monitor = RuntimeSecurityMonitor(
                config=RuntimeMonitorConfig(enabled=True, block_on_detection=True),
                audit_log=self.audit_log,
            )

        monitor_results: list[MonitorInspectionResult] = []
        if active_monitor is not None and active_monitor.config.enabled and runtime_samples:
            for sample in runtime_samples:
                if "prompt" in sample:
                    res = active_monitor.inspect_prompt(
                        str(sample["prompt"]),
                        system_prompt=sample.get("system_prompt"),
                        external_data=sample.get("external_data"),
                        actor=auth_record.authorized_by,
                        raise_on_block=False,
                    )
                    monitor_results.append(res)
                if "tool_name" in sample:
                    res = active_monitor.inspect_tool_call(
                        str(sample["tool_name"]),
                        sample.get("arguments", {}),
                        actor=auth_record.authorized_by,
                        raise_on_block=False,
                    )
                    monitor_results.append(res)

        # 5. Evaluate release gate
        active_policy = gate_policy or GatePolicy(name="security-review", max_critical=0, max_high=0)
        verdict = self.gate_evaluator.evaluate(scan_result, policy=active_policy, sbom=scan_result.sbom)

        # 6. Build sanitized ReviewFindingItem list (responsible disclosure)
        items: list[ReviewFindingItem] = []
        sev_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        cat_counts: dict[str, int] = {}

        for f in scan_result.findings:
            items.append(self._to_review_item(f))
            sev_key = f.severity.value
            sev_counts[sev_key] = sev_counts.get(sev_key, 0) + 1
            cat_key = f.category.value
            cat_counts[cat_key] = cat_counts.get(cat_key, 0) + 1

        guidance = (
            "OSS responsible disclosure active: report security findings privately via the upstream project's "
            "SECURITY.md or private security advisory channel; never open a public issue containing an exploit."
            if (oss_contribution_mode or self.disclosure_policy.oss_contribution_mode)
            else (
                "Responsible disclosure enforced: report findings with file:line, severity, and remediation only; "
                "never publish active exploit payloads."
            )
        )

        # 7. Record completed security review in control-plane audit log
        self.audit_log.record_security_review(
            actor=auth_record.authorized_by,
            target=auth_record.target,
            mode="security_review",
            findings_count=len(items),
            severity_counts=sev_counts,
            passed_gate=verdict.passed,
            disclosure_mode="responsible",
            details={
                "category_counts": cat_counts,
                "oss_contribution_mode": oss_contribution_mode or self.disclosure_policy.oss_contribution_mode,
                "monitor_enabled": active_monitor is not None and active_monitor.config.enabled,
                "monitor_inspections_count": len(monitor_results),
            },
        )

        return SecurityReviewReport(
            target_path=str(Path(target_path)),
            authorized_by=auth_record.authorized_by,
            ownership=auth_record.ownership,
            disclosure_mode="responsible",
            exploit_published=False,
            oss_contribution_mode=oss_contribution_mode or self.disclosure_policy.oss_contribution_mode,
            disclosure_guidance=guidance,
            total_findings=len(items),
            severity_counts=sev_counts,
            category_counts=cat_counts,
            findings=items,
            passed_gate=verdict.passed,
            gate_verdict=verdict,
            specialist_reports=specialist_reports,
            patches=fixer_result.patches,
            monitor_enabled=active_monitor is not None and active_monitor.config.enabled,
            monitor_inspections=monitor_results,
        )

    @staticmethod
    def _to_review_item(finding: Finding) -> ReviewFindingItem:
        file_p = finding.location.file_path if finding.location else "general"
        line_no = finding.location.line_start if finding.location and finding.location.line_start is not None else 1
        loc_str = f"{file_p}:{line_no}"
        fix_str = sanitize_for_responsible_disclosure(finding.how_to_fix)
        desc_str = sanitize_for_responsible_disclosure(finding.description or finding.title)
        patch_str = (
            sanitize_for_responsible_disclosure(finding.remediation.diff_patch)
            if finding.remediation and finding.remediation.diff_patch
            else None
        )
        return ReviewFindingItem(
            id=finding.id,
            rule_id=finding.rule_id,
            title=sanitize_for_responsible_disclosure(finding.title),
            category=finding.category.value,
            severity=finding.severity.value,
            file_path=file_p,
            line=line_no,
            location=loc_str,
            description=desc_str,
            how_to_fix=fix_str,
            diff_patch=patch_str,
            cwe_ids=list(finding.cwe_ids),
        )


def run_security_review(
    target_path: str | Path,
    *,
    owned_target: bool = False,
    authorized_by: str = "owner",
    approval_token: str | None = None,
    target_gate: TargetAuthorizationGate | None = None,
    audit_log: AppendOnlyAuditLog | None = None,
    enable_runtime_monitor: bool = False,
    runtime_samples: list[dict[str, Any]] | None = None,
    oss_contribution_mode: bool = False,
    include_standard_scanners: bool = False,
) -> SecurityReviewReport:
    """Run a complete responsible-disclosure security review on an owned or authorized target."""
    engine = SecurityReviewEngine(target_gate=target_gate, audit_log=audit_log)
    return engine.review(
        target_path=target_path,
        owned_target=owned_target,
        authorized_by=authorized_by,
        approval_token=approval_token,
        include_standard_scanners=include_standard_scanners,
        enable_runtime_monitor=enable_runtime_monitor,
        runtime_samples=runtime_samples,
        oss_contribution_mode=oss_contribution_mode,
    )
