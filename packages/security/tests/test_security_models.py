from faccoder_security.models import (
    Finding,
    FindingCategory,
    Location,
    ScanMetadata,
    ScanResult,
    Severity,
)


def test_severity_ordering():
    assert Severity.CRITICAL > Severity.HIGH
    assert Severity.HIGH > Severity.MEDIUM
    assert Severity.MEDIUM > Severity.LOW
    assert Severity.LOW > Severity.INFO
    assert Severity.HIGH >= Severity.HIGH
    assert Severity.LOW <= Severity.MEDIUM
    assert Severity.from_str("CRITICAL") == Severity.CRITICAL
    assert Severity.from_str("warning") == Severity.MEDIUM
    assert Severity.from_str("error") == Severity.HIGH


def test_scan_result_filtering():
    f1 = Finding(
        id="f1",
        scanner="semgrep",
        rule_id="r1",
        title="SQL Injection",
        severity=Severity.HIGH,
        category=FindingCategory.SAST,
        location=Location(file_path="app.py", line_start=10),
    )
    f2 = Finding(
        id="f2",
        scanner="bandit",
        rule_id="r2",
        title="Info note",
        severity=Severity.INFO,
        category=FindingCategory.SAST,
        location=Location(file_path="app.py", line_start=20),
    )
    f3 = Finding(
        id="f3",
        scanner="gitleaks",
        rule_id="r3",
        title="Suppressed",
        severity=Severity.CRITICAL,
        category=FindingCategory.SECRET,
        is_suppressed=True,
    )

    res = ScanResult(
        scanner="test-suite",
        target_path=".",
        findings=[f1, f2, f3],
        metadata=ScanMetadata(scanner="test-suite", target_path="."),
    )

    assert res.total_findings(include_suppressed=False) == 2
    assert res.total_findings(include_suppressed=True) == 3
    assert len(res.by_severity(Severity.HIGH)) == 1
    assert len(res.by_severity(Severity.CRITICAL)) == 0  # suppressed
    assert res.has_high_or_critical() is True
