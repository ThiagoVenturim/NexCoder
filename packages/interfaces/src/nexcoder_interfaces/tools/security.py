from __future__ import annotations

from pathlib import Path
from typing import Any


def security_scan(
    path: str = ".",
    policy: str = "default",
    force_offline: bool = True,
    owned_target: bool = False,
    authorized_by: str = "owner",
    approval_token: str | None = None,
    audit_log: Any | None = None,
    target_gate: Any | None = None,
) -> dict[str, Any]:
    """Execute multi-scanner security analysis and evaluate release gate verdict."""
    try:
        from nexcoder_control.approval import TargetNotAuthorizedError
        from nexcoder_security.gate import GatePolicy, SecurityGateEvaluator
        from nexcoder_security.scanners import MultiScannerEngine
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Security package not available: {exc}",
        }

    target = Path(path).resolve()
    engine = MultiScannerEngine(target_gate=target_gate, audit_log=audit_log)
    try:
        scan_result = engine.scan(
            target,
            force_offline=force_offline,
            owned_target=owned_target,
            authorized_by=authorized_by,
            approval_token=approval_token,
        )
    except TargetNotAuthorizedError as exc:
        return {
            "status": "rejected",
            "authorized": False,
            "target_path": str(target),
            "reason": str(exc),
        }

    evaluator = SecurityGateEvaluator()
    gate_policy = GatePolicy(max_high=0, max_critical=0) if policy == "strict" else GatePolicy()
    verdict = evaluator.evaluate(scan_result, gate_policy)

    return {
        "status": "success",
        "authorized": True,
        "authorized_by": authorized_by,
        "target_path": str(target),
        "scanner": scan_result.metadata.scanner if scan_result.metadata else "multi-scanner",
        "total_findings": len(scan_result.findings),
        "has_high_or_critical": scan_result.has_high_or_critical(),
        "passed_gate": verdict.passed,
        "verdict_reason": verdict.summary,
        "findings": [
            {
                "id": f.id,
                "rule_id": f.rule_id,
                "title": f.title,
                "severity": f.severity.value,
                "category": f.category.value,
                "location": f.location.model_dump() if f.location else None,
            }
            for f in scan_result.findings
        ],
    }


def security_review(
    path: str = ".",
    owned_target: bool = False,
    authorized_by: str = "owner",
    approval_token: str | None = None,
    enable_runtime_monitor: bool = False,
    oss_contribution_mode: bool = False,
    audit_log: Any | None = None,
    target_gate: Any | None = None,
) -> dict[str, Any]:
    """Execute responsible-disclosure security review (prompt injection, SQLi, data leakage, general security)."""
    try:
        from nexcoder_control.approval import TargetNotAuthorizedError
        from nexcoder_security.review import SecurityReviewEngine
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Security package not available: {exc}",
        }

    target = Path(path).resolve()
    engine = SecurityReviewEngine(target_gate=target_gate, audit_log=audit_log)
    try:
        report = engine.review(
            target_path=target,
            owned_target=owned_target,
            authorized_by=authorized_by,
            approval_token=approval_token,
            enable_runtime_monitor=enable_runtime_monitor,
            oss_contribution_mode=oss_contribution_mode,
        )
    except TargetNotAuthorizedError as exc:
        return {
            "status": "rejected",
            "authorized": False,
            "target_path": str(target),
            "reason": str(exc),
        }

    return {
        "status": "success",
        "authorized": True,
        "authorized_by": report.authorized_by,
        "target_path": report.target_path,
        "disclosure_mode": report.disclosure_mode,
        "exploit_published": report.exploit_published,
        "total_findings": report.total_findings,
        "passed_gate": report.passed_gate,
        "severity_counts": report.severity_counts,
        "category_counts": report.category_counts,
        "findings": [item.model_dump(mode="json") for item in report.findings],
    }


def security_report(
    project: str = "nexcoder-platform",
    period: str = "2026-Q4",
    policy: str = "default",
    transport: str = "offline",
    nexdash_url: str = "http://127.0.0.1:8080",
    output_html_path: str | None = None,
) -> dict[str, Any]:
    """Convert security scanner findings and gate coverage into a NexDash security posture dashboard."""
    try:
        from nexcoder_core.reports import NexDashValidationError
        from nexcoder_security.gate import GatePolicy
        from nexcoder_security.reports import generate_security_dashboard
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Security reporting module not available: {exc}",
        }

    gate_policy = GatePolicy.production(require_sbom=True) if policy == "strict" else GatePolicy(require_sbom=True)
    try:
        metrics, bundle = generate_security_dashboard(
            project=project,
            period=period,
            policy=gate_policy,
            transport=transport,  # type: ignore[arg-type]
            nexdash_url=nexdash_url,
        )
    except NexDashValidationError as exc:
        return {
            "status": "error",
            "message": str(exc),
        }

    if output_html_path:
        out_path = Path(output_html_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(bundle.html, encoding="utf-8")

    return {
        "status": "success",
        "model_id": bundle.model_id,
        "transport": bundle.transport,
        "dashboard_id": bundle.dashboard_id,
        "title": bundle.title,
        "subtitle": bundle.subtitle,
        "metrics": metrics.model_dump(),
        "kpis": [k.model_dump() for k in bundle.kpis],
        "charts": [c.model_dump() for c in bundle.charts],
        "csp_header": bundle.csp_header,
        "html": bundle.html,
    }


def run_security_test_campaign(
    target: str = ".",
    test_types: list[str] | None = None,
    agent_count: int = 3,
    allowed_scope: list[str] | None = None,
    max_cost_usd: float = 5.0,
    max_duration_seconds: float = 120.0,
    owned_target: bool = False,
    authorized_by: str = "owner",
    authorization_document: Any | None = None,
    require_signed_document: bool = False,
    dry_run: bool = True,
    audit_log: Any | None = None,
    target_gate: Any | None = None,
) -> dict[str, Any]:
    """Execute multi-agent test campaign with target authorization and budget limits (Issue #71)."""
    try:
        from nexcoder_control.approval import TargetNotAuthorizedError
        from nexcoder_security.campaign import (
            CampaignBudget,
            CampaignConfig,
            SecurityTestCampaignEngine,
            TestType,
        )
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Security campaign package not available: {exc}",
        }

    parsed_types: list[TestType] = []
    if test_types:
        for t in test_types:
            try:
                parsed_types.append(TestType.from_str(t))
            except ValueError as exc:
                return {"status": "error", "message": str(exc)}
    else:
        parsed_types = [TestType.UNIT, TestType.API, TestType.SECURITY]

    budget = CampaignBudget(
        max_cost_usd=max_cost_usd,
        max_duration_seconds=max_duration_seconds,
    )
    config = CampaignConfig(
        target=target,
        test_types=parsed_types,
        agent_count=agent_count,
        allowed_scope=allowed_scope or ["*"],
        budget=budget,
        owned_target=owned_target,
        authorized_by=authorized_by,
        authorization_document=authorization_document,
        require_signed_document=require_signed_document,
        dry_run=dry_run,
    )

    engine = SecurityTestCampaignEngine(
        audit_log=audit_log,
        target_gate=target_gate,
    )

    try:
        report = engine.run_campaign(config, raise_on_auth_failure=False)
    except TargetNotAuthorizedError as exc:
        return {
            "status": "rejected",
            "authorized": False,
            "target": target,
            "reason": str(exc),
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Campaign failed: {exc}",
        }

    if report.status == "rejected":
        return {
            "status": "rejected",
            "authorized": False,
            "target": target,
            "reason": report.metadata.get("rejection_reason", "Target authorization denied"),
        }

    return {
        "status": report.status.value,
        "authorized": True,
        "campaign_id": report.campaign_id,
        "target": report.target,
        "authorized_by": report.authorized_by,
        "agent_count": report.agent_count,
        "test_types": [t.value for t in report.test_types],
        "total_tests_run": report.total_tests_run,
        "total_passed": report.total_passed,
        "total_failed": report.total_failed,
        "severity_counts": report.severity_counts,
        "duration_seconds": report.duration_seconds,
        "actual_cost_usd": report.actual_cost_usd,
        "findings_count": len(report.findings),
        "findings": [
            {
                "id": f.id,
                "test_type": f.test_type.value,
                "agent_id": f.agent_id,
                "title": f.title,
                "severity": f.severity.value,
                "category": f.category,
                "target_ref": f.target_ref,
                "description": f.description,
                "steps_to_reproduce": f.steps_to_reproduce,
                "remediation_suggestion": f.remediation_suggestion,
            }
            for f in report.findings
        ],
    }


def get_security_test_campaign(campaign_id: str) -> dict[str, Any]:
    """Retrieve campaign status and findings by ID."""
    try:
        from nexcoder_security.campaign import get_global_registry
    except ImportError as exc:
        return {"status": "error", "message": f"Security package not available: {exc}"}

    registry = get_global_registry()
    report = registry.get(campaign_id)
    if report is None:
        return {"status": "not_found", "message": f"Campaign '{campaign_id}' not found"}

    return {
        "status": "success",
        "campaign": report.to_dict(),
    }


def export_security_test_report(
    campaign_id: str,
    format: str = "json",
    output_path: str | None = None,
) -> dict[str, Any]:
    """Export a campaign report to JSON, Markdown, or HTML."""
    try:
        from nexcoder_security.campaign import get_global_registry
    except ImportError as exc:
        return {"status": "error", "message": f"Security package not available: {exc}"}

    registry = get_global_registry()
    report = registry.get(campaign_id)
    if report is None:
        return {"status": "not_found", "message": f"Campaign '{campaign_id}' not found"}

    fmt = format.lower()
    if fmt == "json":
        content = report.to_json()
    elif fmt in ("markdown", "md"):
        content = report.to_markdown()
    elif fmt in ("html", "htm"):
        content = report.to_html()
    else:
        return {"status": "error", "message": f"Unsupported format '{format}'. Use 'json', 'markdown', or 'html'."}

    if output_path:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        return {
            "status": "success",
            "campaign_id": campaign_id,
            "format": fmt,
            "output_path": str(out),
        }

    return {
        "status": "success",
        "campaign_id": campaign_id,
        "format": fmt,
        "content": content,
    }
