from faccoder_security.agents import (
    ASVSComplianceAgent,
    ComplianceStatus,
    DependencyAgent,
    SASTTriageAgent,
    SecretsAgent,
    SecurityFixerAgent,
    StrideCategory,
    ThreatModelAgent,
    TriageVerdict,
)
from faccoder_security.models import Finding, FindingCategory, Location, Remediation, Severity


def test_threat_model_agent():
    agent = ThreatModelAgent()
    target = {
        "name": "PaymentService",
        "components": ["Customer Frontend", "Payment API", "PostgreSQL DB"],
        "flows": ["Frontend -> API", "API -> DB"],
    }
    result = agent.analyze(target, offline=True)
    assert result.system_name == "PaymentService"
    assert len(result.components) == 3
    assert len(result.threats) > 0
    categories = {t.stride_category for t in result.threats}
    assert StrideCategory.INFORMATION_DISCLOSURE in categories
    assert StrideCategory.TAMPERING in categories
    assert StrideCategory.ELEVATION_OF_PRIVILEGE in categories


def test_sast_triage_agent():
    agent = SASTTriageAgent()
    f1 = Finding(
        id="f1",
        scanner="semgrep",
        rule_id="python.security.injection.shell-true",
        title="Command Injection",
        severity=Severity.CRITICAL,
        category=FindingCategory.SAST,
        location=Location(file_path="src/main.py", snippet="subprocess.call(cmd, shell=True)"),
    )
    f2 = Finding(
        id="f2",
        scanner="bandit",
        rule_id="bandit.B101",
        title="Assert used",
        severity=Severity.LOW,
        category=FindingCategory.SAST,
        location=Location(file_path="tests/test_app.py", snippet="assert 1 == 1"),
    )

    result = agent.analyze([f1, f2], offline=True)
    assert result.total_analyzed == 2
    assert result.true_positives == 1
    assert result.false_positives == 1
    assert result.triaged_findings[0].verdict == TriageVerdict.TRUE_POSITIVE
    assert result.triaged_findings[1].verdict == TriageVerdict.FALSE_POSITIVE


def test_dependency_agent():
    agent = DependencyAgent()
    f = Finding(
        id="f1",
        scanner="osv-scanner",
        rule_id="GHSA-1234",
        title="requests: Header leak",
        severity=Severity.HIGH,
        category=FindingCategory.SCA,
        location=Location(file_path="requirements.txt", snippet="requests==2.31.0"),
        cve_id="CVE-2023-32681",
        remediation=Remediation(summary="Upgrade requests", recommended_version="2.32.0"),
    )
    result = agent.analyze([f], offline=True)
    assert result.vulnerable_packages_count == 1
    adv = result.advisories[0]
    assert adv.package_name == "requests"
    assert adv.target_version == "2.32.0"
    assert "uv pip install" in adv.upgrade_command


def test_secrets_agent():
    agent = SecretsAgent()
    f = Finding(
        id="f1",
        scanner="gitleaks",
        rule_id="aws-access-key-id",
        title="Secret detected: AWS Access Key ID",
        severity=Severity.CRITICAL,
        category=FindingCategory.SECRET,
        location=Location(file_path="config.py", line_start=15),
    )
    result = agent.analyze([f], offline=True)
    assert result.secrets_detected == 1
    assert result.critical_exposures == 1
    steps = result.assessments[0].rotation_plan
    assert len(steps) >= 3
    assert "Revoke" in steps[0].action


def test_asvs_compliance_agent():
    agent = ASVSComplianceAgent()
    # Baseline clean check
    report = agent.analyze({"name": "CleanApp"}, offline=True)
    assert report.overall_status == ComplianceStatus.PASSED
    assert report.total_checks >= 9

    # Check with failing findings
    f = Finding(
        id="f1",
        scanner="semgrep",
        rule_id="sqli",
        title="SQL Injection",
        severity=Severity.HIGH,
        category=FindingCategory.SAST,
    )
    report_fail = agent.analyze({"name": "VulnerableApp", "findings": [f]}, offline=True)
    assert report_fail.overall_status == ComplianceStatus.FAILED
    assert report_fail.failed_checks >= 1


def test_security_fixer_agent():
    agent = SecurityFixerAgent()
    f1 = Finding(
        id="f1",
        scanner="semgrep",
        rule_id="python.security.injection.shell-true",
        title="Shell Injection",
        severity=Severity.CRITICAL,
        category=FindingCategory.SAST,
        location=Location(file_path="src/executor.py", line_start=25, snippet="subprocess.call(cmd, shell=True)"),
    )
    f2 = Finding(
        id="f2",
        scanner="gitleaks",
        rule_id="generic-secret",
        title="Secret detected: API Key",
        severity=Severity.HIGH,
        category=FindingCategory.SECRET,
        location=Location(file_path="src/api.py", line_start=5, snippet='API_KEY = "AKIA1234567890ABCDEF"'),
    )

    result = agent.analyze([f1, f2], offline=True)
    assert result.total_findings_considered == 2
    assert result.patches_generated == 2
    p1 = result.patches[0]
    assert "--- a/src/executor.py" in p1.diff_patch
    assert "shell=False" in p1.fixed_code
    p2 = result.patches[1]
    assert "os.environ.get" in p2.fixed_code
