from faccoder_security.gate import GatePolicy, SecurityGateEvaluator
from faccoder_security.models import (
    Finding,
    FindingCategory,
    SBOMComponent,
    SBOMDocument,
    ScanMetadata,
    ScanResult,
    Severity,
)
from faccoder_security.scanners.base import BaseScanner
from faccoder_security.scanners.engine import MultiScannerEngine


def test_security_gate_blocks_critical_and_high():
    f_crit = Finding(
        id="c1",
        scanner="semgrep",
        rule_id="r1",
        title="Critical vuln",
        severity=Severity.CRITICAL,
        category=FindingCategory.SAST,
    )
    f_high = Finding(
        id="h1",
        scanner="bandit",
        rule_id="r2",
        title="High vuln",
        severity=Severity.HIGH,
        category=FindingCategory.SAST,
    )

    res = ScanResult(
        scanner="multi",
        target_path=".",
        findings=[f_crit, f_high],
        metadata=ScanMetadata(scanner="multi", target_path="."),
    )

    evaluator = SecurityGateEvaluator()
    verdict = evaluator.evaluate(res)
    assert verdict.passed is False
    assert len(verdict.blocking_findings) == 2
    assert "Release BLOCKED" in verdict.summary
    assert len(verdict.reasons) >= 2


def test_security_gate_passes_clean_or_low_findings():
    f_low = Finding(
        id="l1",
        scanner="semgrep",
        rule_id="r3",
        title="Low note",
        severity=Severity.LOW,
        category=FindingCategory.SAST,
    )
    res = ScanResult(
        scanner="multi",
        target_path=".",
        findings=[f_low],
        metadata=ScanMetadata(scanner="multi", target_path="."),
    )

    evaluator = SecurityGateEvaluator()
    verdict = evaluator.evaluate(res)
    assert verdict.passed is True
    assert len(verdict.blocking_findings) == 0
    assert "Release APPROVED" in verdict.summary


def test_security_gate_allowed_cves_and_rules():
    f_cve = Finding(
        id="cve1",
        scanner="osv-scanner",
        rule_id="GHSA-test",
        title="Known issue in legacy lib",
        severity=Severity.HIGH,
        category=FindingCategory.SCA,
        cve_id="CVE-2023-9999",
    )
    res = ScanResult(
        scanner="multi",
        target_path=".",
        findings=[f_cve],
        metadata=ScanMetadata(scanner="multi", target_path="."),
    )

    policy = GatePolicy(allowed_cves=["CVE-2023-9999"])
    evaluator = SecurityGateEvaluator(default_policy=policy)
    verdict = evaluator.evaluate(res)
    assert verdict.passed is True


def test_security_gate_blocks_on_secrets():
    f_secret = Finding(
        id="s1",
        scanner="gitleaks",
        rule_id="generic-secret",
        title="Secret detected",
        severity=Severity.HIGH,
        category=FindingCategory.SECRET,
    )
    res = ScanResult(
        scanner="multi",
        target_path=".",
        findings=[f_secret],
        metadata=ScanMetadata(scanner="multi", target_path="."),
    )

    evaluator = SecurityGateEvaluator()
    verdict = evaluator.evaluate(res)
    assert verdict.passed is False
    assert any("secrets" in r.lower() for r in verdict.reasons)


def test_security_gate_fail_closed_on_scanner_error():
    # Zero findings, but scanner crashed/errored
    res = ScanResult(
        scanner="semgrep",
        target_path=".",
        findings=[],
        metadata=ScanMetadata(
            scanner="semgrep",
            target_path=".",
            success=False,
            error_message="Semgrep syntax error parsing rules",
        ),
        errors=["Semgrep syntax error parsing rules"],
    )

    evaluator = SecurityGateEvaluator()
    verdict = evaluator.evaluate(res)
    assert verdict.passed is False
    assert "Release BLOCKED" in verdict.summary
    assert any("fail-closed" in r for r in verdict.reasons)


def test_security_gate_fail_closed_engine_exception(tmp_path):
    class CrashingScanner(BaseScanner):
        def __init__(self):
            super().__init__(executable_name="crash", name="crash")

        def scan(self, target_path, options=None, force_offline_fallback=False):
            raise RuntimeError("Unexpected internal crash in scanner binary execution")

    engine = MultiScannerEngine()
    engine.register_scanner("crash", CrashingScanner())

    scan_res = engine.scan(tmp_path, enabled_scanners=["crash"])
    assert scan_res.has_errors() is True
    assert len(scan_res.errors) >= 1

    evaluator = SecurityGateEvaluator()
    verdict = evaluator.evaluate(scan_res)
    assert verdict.passed is False
    assert "Release BLOCKED" in verdict.summary
    assert any("fail-closed" in r for r in verdict.reasons)


def test_security_gate_require_sbom():
    policy = GatePolicy(require_sbom=True)
    evaluator = SecurityGateEvaluator(default_policy=policy)

    clean_res = ScanResult(
        scanner="multi",
        target_path=".",
        findings=[],
        metadata=ScanMetadata(scanner="multi", target_path=".", success=True),
    )

    # 1. Missing SBOM blocks release
    verdict_missing = evaluator.evaluate(clean_res, policy=policy)
    assert verdict_missing.passed is False
    assert "Release BLOCKED" in verdict_missing.summary
    assert any("require_sbom" in r for r in verdict_missing.reasons)

    # 2. Empty SBOM blocks release
    empty_sbom = SBOMDocument(format="cyclonedx", components=[], raw_content="")
    verdict_empty = evaluator.evaluate(clean_res, policy=policy, sbom=empty_sbom)
    assert verdict_empty.passed is False

    # 3. Valid SBOM approves release
    valid_sbom = SBOMDocument(
        format="cyclonedx",
        components=[SBOMComponent(name="requests", version="2.32.0")],
        raw_content='{"bomFormat": "CycloneDX"}',
    )
    verdict_valid = evaluator.evaluate(clean_res, policy=policy, sbom=valid_sbom)
    assert verdict_valid.passed is True
    assert "Release APPROVED" in verdict_valid.summary


def test_gate_production_policy_preset():
    prod_policy = GatePolicy.production(require_sbom=True)
    assert prod_policy.name == "production"
    assert prod_policy.allow_fallbacks is False
    assert prod_policy.max_critical == 0
    assert prod_policy.max_high == 0
    assert prod_policy.require_sbom is True
    assert prod_policy.block_on_secrets is True


def test_security_gate_blocks_fallbacks_in_production():
    prod_policy = GatePolicy.production(require_sbom=False)
    evaluator = SecurityGateEvaluator(default_policy=prod_policy)

    fallback_res = ScanResult(
        scanner="semgrep",
        target_path=".",
        findings=[],
        metadata=ScanMetadata(scanner="semgrep", target_path=".", success=True, is_fallback=True),
        fallbacks=["semgrep"],
    )

    # In production policy (allow_fallbacks=False), fallback scans must BLOCK release
    verdict = evaluator.evaluate(fallback_res, policy=prod_policy)
    assert verdict.passed is False
    assert "Release BLOCKED" in verdict.summary
    assert any("Fallback heuristic scans not permitted" in r for r in verdict.reasons)

    # In default policy (allow_fallbacks=True), fallback scans are permitted
    default_policy = GatePolicy(allow_fallbacks=True, require_sbom=False)
    verdict_allowed = evaluator.evaluate(fallback_res, policy=default_policy)
    assert verdict_allowed.passed is True
    assert "Release APPROVED" in verdict_allowed.summary
