from __future__ import annotations

from pathlib import Path
from typing import Any


def security_scan(
    path: str = ".",
    policy: str = "default",
    force_offline: bool = True,
) -> dict[str, Any]:
    """Execute multi-scanner security analysis and evaluate release gate verdict."""
    try:
        from nexcoder_security.gate import GatePolicy, SecurityGateEvaluator
        from nexcoder_security.scanners import MultiScannerEngine
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Security package not available: {exc}",
        }

    target = Path(path).resolve()
    engine = MultiScannerEngine()
    scan_result = engine.scan(target, force_offline=force_offline)

    evaluator = SecurityGateEvaluator()
    gate_policy = GatePolicy(max_high=0, max_critical=0) if policy == "strict" else GatePolicy()
    verdict = evaluator.evaluate(scan_result, gate_policy)

    return {
        "status": "success",
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
