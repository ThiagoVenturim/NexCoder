from __future__ import annotations

from typing import Any, Literal

from nexcoder_interfaces.testing.models import ALL_TEST_TYPES, SecurityTestRunConfig, TestType
from nexcoder_interfaces.testing.service import GLOBAL_SECURITY_TEST_SERVICE, SecurityTestService


def trigger_security_tests(
    path: str = ".",
    test_types: list[str] | None = None,
    num_agents: int = 4,
    budget_limit: float = 50.0,
    budget_currency: str = "USD",
    owned_target: bool = False,
    authorized_by: str = "owner",
    approval_token: str | None = None,
    offline: bool = True,
    service: SecurityTestService | None = None,
) -> dict[str, Any]:
    """Dispatch multi-agent extreme testing (unit, system, process, DOM, API, security) for an authorized target.

    Enforces target authorization gate per USAGE_POLICY.md. If target is not marked as owned or accompanied
    by a valid approval token, returns status 'rejected'. Generates terminal cards and report notes for NexHub.
    """
    svc = service or GLOBAL_SECURITY_TEST_SERVICE
    valid_types: list[TestType] = []
    if test_types:
        for t in test_types:
            clean = t.lower().strip()
            if clean in ALL_TEST_TYPES:
                valid_types.append(clean)  # type: ignore[arg-type]
    if not valid_types:
        valid_types = list(ALL_TEST_TYPES)

    config = SecurityTestRunConfig(
        target_path=path,
        test_types=valid_types,
        num_agents=max(1, num_agents),
        budget_limit=max(0.01, float(budget_limit)),
        budget_currency=budget_currency,
        owned_target=owned_target,
        authorized_by=authorized_by,
        approval_token=approval_token,
        offline=offline,
    )

    record = svc.dispatch_run(config)
    return {
        "status": record.status,
        "run_id": record.run_id,
        "authorized": record.authorized,
        "authorized_by": record.authorized_by,
        "target_path": record.target_path,
        "test_types": record.config.test_types,
        "num_agents": len(record.agents),
        "budget": {
            "limit": record.config.budget_limit,
            "currency": record.config.budget_currency,
            "spent": record.budget_spent,
            "exceeded": record.budget_spent > record.config.budget_limit,
        },
        "progress_percent": record.progress_percent,
        "total_findings": record.total_findings,
        "passed_gate": record.passed_gate,
        "summary": record.summary,
        "rejection_reason": record.rejection_reason,
        "agents": [
            {
                "agent_id": a.id,
                "title": a.title,
                "role": a.role,
                "assigned_types": a.assigned_types,
                "state": a.state,
                "findings_count": a.findings_count,
                "logs": a.logs[-10:],
            }
            for a in record.agents
        ],
        "canvas": record.canvas.model_dump(),
        "findings": [f.model_dump() for f in record.findings],
    }


def get_security_test_status(
    run_id: str,
    service: SecurityTestService | None = None,
) -> dict[str, Any]:
    """Retrieve execution status, per-agent logs, and progress for an active or completed test run."""
    svc = service or GLOBAL_SECURITY_TEST_SERVICE
    record = svc.get_run(run_id)
    if not record:
        return {
            "status": "not_found",
            "run_id": run_id,
            "message": f"Test run '{run_id}' not found in registry.",
        }

    return {
        "status": record.status,
        "run_id": record.run_id,
        "target_path": record.target_path,
        "progress_percent": record.progress_percent,
        "budget_spent": record.budget_spent,
        "total_findings": record.total_findings,
        "passed_gate": record.passed_gate,
        "summary": record.summary,
        "agents": [
            {
                "agent_id": a.id,
                "title": a.title,
                "role": a.role,
                "assigned_types": a.assigned_types,
                "state": a.state,
                "findings_count": a.findings_count,
                "recent_logs": a.logs[-10:],
            }
            for a in record.agents
        ],
    }


def get_security_test_canvas(
    run_id: str,
    service: SecurityTestService | None = None,
) -> dict[str, Any]:
    """Retrieve full NexHub canvas payload (cards, markdown notes, connections) for visualization."""
    svc = service or GLOBAL_SECURITY_TEST_SERVICE
    record = svc.get_run(run_id)
    if not record:
        return {
            "status": "not_found",
            "run_id": run_id,
            "message": f"Test run '{run_id}' not found in registry.",
        }

    return {
        "status": "success",
        "run_id": record.run_id,
        "canvas": record.canvas.model_dump(),
    }


def verify_security_test_target(
    path: str = ".",
    owned_target: bool = False,
    authorized_by: str = "owner",
    approval_token: str | None = None,
    service: SecurityTestService | None = None,
) -> dict[str, Any]:
    """Preflight target verification to check whether workspace is authorized for extreme testing."""
    svc = service or GLOBAL_SECURITY_TEST_SERVICE
    return svc.verify_target(
        target_path=path,
        owned_target=owned_target,
        authorized_by=authorized_by,
        approval_token=approval_token,
    )


def cancel_security_test(
    run_id: str,
    service: SecurityTestService | None = None,
) -> dict[str, Any]:
    """Cancel an ongoing test run."""
    svc = service or GLOBAL_SECURITY_TEST_SERVICE
    cancelled = svc.cancel_run(run_id)
    return {
        "run_id": run_id,
        "cancelled": cancelled,
        "status": "cancelled" if cancelled else "unable_to_cancel",
    }


def export_security_test_report(
    run_id: str,
    format: Literal["markdown", "json"] = "markdown",
    service: SecurityTestService | None = None,
) -> dict[str, Any]:
    """Export the consolidated test and security report as Markdown or raw JSON."""
    svc = service or GLOBAL_SECURITY_TEST_SERVICE
    record = svc.get_run(run_id)
    if not record:
        return {
            "status": "not_found",
            "run_id": run_id,
            "message": f"Test run '{run_id}' not found in registry.",
        }

    from nexcoder_interfaces.testing.canvas import format_markdown_summary, format_remediation_note

    md_report = f"{format_markdown_summary(record)}\n\n{format_remediation_note(record)}"
    return {
        "status": "success",
        "run_id": record.run_id,
        "format": format,
        "content": md_report if format == "markdown" else record.model_dump(mode="json"),
    }
