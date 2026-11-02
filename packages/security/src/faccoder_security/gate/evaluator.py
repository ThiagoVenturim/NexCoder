from __future__ import annotations

from faccoder_security.gate.policy import GatePolicy, GateVerdict
from faccoder_security.models import Finding, SBOMDocument, ScanResult, Severity


class SecurityGateEvaluator:
    """Evaluates scan results against configurable security gate policies to decide release blocking."""

    def __init__(self, default_policy: GatePolicy | None = None) -> None:
        self.default_policy = default_policy or GatePolicy()

    def evaluate(
        self,
        scan_result: ScanResult,
        policy: GatePolicy | None = None,
        sbom: SBOMDocument | None = None,
    ) -> GateVerdict:
        pol = policy or self.default_policy
        blocking: list[Finding] = []
        reasons: list[str] = []

        allowed_cve_set = set(pol.allowed_cves)
        allowed_rule_set = set(pol.allowed_rules)

        critical_count = 0
        high_count = 0
        medium_count = 0

        # Fail-closed check: any scanner failure or exception blocks the release
        has_scanner_errors = scan_result.has_errors()
        if has_scanner_errors:
            err_list = scan_result.errors or [
                scan_result.metadata.error_message
                if scan_result.metadata and scan_result.metadata.error_message
                else "Unspecified scanner failure"
            ]
            for err in err_list:
                reasons.append(f"Scanner failure detected (fail-closed enforced): {err}")

        # Check require_sbom requirement
        missing_sbom = False
        if pol.require_sbom:
            active_sbom = sbom or scan_result.sbom
            if not active_sbom or len(active_sbom.components) == 0 or not active_sbom.raw_content.strip():
                missing_sbom = True
                reasons.append("Policy require_sbom is enabled, but no valid SBOM document was generated or provided.")

        # Check fallback execution
        has_forbidden_fallbacks = False
        if not pol.allow_fallbacks and scan_result.fallback_scanners:
            has_forbidden_fallbacks = True
            for s in scan_result.fallback_scanners:
                reasons.append(f"Scanner '{s}' ran in fallback mode, but policy forbids fallback execution.")
        for s in pol.disallow_fallback_scanners:
            if s in scan_result.fallback_scanners or (
                scan_result.metadata and scan_result.metadata.scanner == s and scan_result.metadata.is_fallback
            ):
                has_forbidden_fallbacks = True
                reasons.append(f"Required scanner '{s}' ran only in fallback mode.")

        # Check findings against thresholds and allowlists
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

        if critical_count > pol.max_critical:
            reasons.append(f"Critical findings ({critical_count}) exceed threshold ({pol.max_critical}).")
        if high_count > pol.max_high:
            reasons.append(f"High findings ({high_count}) exceed threshold ({pol.max_high}).")
        if pol.max_medium is not None and medium_count > pol.max_medium:
            reasons.append(f"Medium findings ({medium_count}) exceed threshold ({pol.max_medium}).")
        if any(f.category.value == "secret" for f in blocking):
            reasons.append("Unsuppressed secrets detected in target repository/code.")

        passed = len(blocking) == 0 and not has_scanner_errors and not missing_sbom and not has_forbidden_fallbacks

        if not passed:
            details_count = len(blocking)
            if has_scanner_errors:
                summary = (
                    f"Release BLOCKED by security gate '{pol.name}': "
                    "scanner execution failed (fail-closed) or security thresholds breached."
                )
            elif missing_sbom:
                summary = (
                    f"Release BLOCKED by security gate '{pol.name}': "
                    "missing required SBOM or security thresholds breached."
                )
            elif has_forbidden_fallbacks:
                summary = (
                    f"Release BLOCKED by security gate '{pol.name}': "
                    "required scanner ran in fallback mode or security thresholds breached."
                )
            else:
                summary = f"Release BLOCKED by security gate '{pol.name}': {details_count} blocking findings detected."
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
