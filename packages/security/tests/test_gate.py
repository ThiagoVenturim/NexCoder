from faccoder_security.gate import GatePolicy, SecurityGateEvaluator
from faccoder_security.models import Finding, FindingCategory, ScanMetadata, ScanResult, Severity


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
