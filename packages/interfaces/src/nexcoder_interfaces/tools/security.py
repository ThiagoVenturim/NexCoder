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
