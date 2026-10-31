from __future__ import annotations

from faccoder_security.gate.policy import GatePolicy, GateVerdict
from faccoder_security.models import Finding, ScanResult, Severity


class SecurityGateEvaluator:
    """Evaluates scan results against configurable security gate policies to decide release blocking."""

    def __init__(self, default_policy: GatePolicy | None = None) -> None:
        self.default_policy = default_policy or GatePolicy()

    def evaluate(self, scan_result: ScanResult, policy: GatePolicy | None = None) -> GateVerdict:
        pol = policy or self.default_policy
        blocking: list[Finding] = []
        reasons: list[str] = []

        allowed_cve_set = set(pol.allowed_cves)
        allowed_rule_set = set(pol.allowed_rules)

        critical_count = 0
        high_count = 0
        medium_count = 0

        for f in scan_result.findings:
            if f.is_suppressed:
                continue

            # Check allowlists
            if f.cve_id and f.cve_id in allowed_cve_set:
                continue
            if f.rule_id in allowed_rule_set:
                continue

            # Secret check
            if pol.block_on_secrets and f.category.value == "secret":
                blocking.append(f)
                continue

            if f.severity == Severity.CRITICAL:
                critical_count += 1
                if critical_count > pol.max_critical:
                    blocking.append(f)
            elif f.severity == Severity.HIGH:
                high_count += 1
                if high_count > pol.max_high:
                    blocking.append(f)
            elif f.severity == Severity.MEDIUM and pol.max_medium is not None:
                medium_count += 1
                if medium_count > pol.max_medium:
                    blocking.append(f)

        passed = len(blocking) == 0

        if not passed:
            summary = f"Release BLOCKED by security gate '{pol.name}': {len(blocking)} blocking findings detected."
            if critical_count > pol.max_critical:
                reasons.append(f"Critical findings ({critical_count}) exceed threshold ({pol.max_critical}).")
            if high_count > pol.max_high:
                reasons.append(f"High findings ({high_count}) exceed threshold ({pol.max_high}).")
            if pol.max_medium is not None and medium_count > pol.max_medium:
                reasons.append(f"Medium findings ({medium_count}) exceed threshold ({pol.max_medium}).")
            if any(f.category.value == "secret" for f in blocking):
                reasons.append("Unsuppressed secrets detected in target repository/code.")
        else:
            summary = f"Release APPROVED by security gate '{pol.name}'."

        return GateVerdict(
            passed=passed,
            policy_name=pol.name,
            total_findings_evaluated=len(scan_result.findings),
            blocking_findings=blocking,
            summary=summary,
            reasons=reasons,
        )
