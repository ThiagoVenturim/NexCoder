import json
from pathlib import Path

from faccoder_security.models import FindingCategory, Severity
from faccoder_security.scanners import (
    BanditScanner,
    GitleaksScanner,
    MultiScannerEngine,
    OSVScanner,
    PipAuditScanner,
    SemgrepScanner,
    SyftScanner,
    TrivyScanner,
)


def test_semgrep_offline_scan(tmp_path: Path):
    vuln_file = tmp_path / "vulnerable.py"
    vuln_file.write_text(
        """
import subprocess

def run_cmd(user_input):
    eval(user_input)
    subprocess.call(user_input, shell=True)
""",
        encoding="utf-8",
    )

    scanner = SemgrepScanner()
    res = scanner.scan(tmp_path, force_offline_fallback=True)
    assert res.metadata is not None
    assert res.metadata.success is True
    assert len(res.findings) >= 2
    rule_ids = {f.rule_id for f in res.findings}
    assert "python.security.injection.exec-detected" in rule_ids
    assert "python.security.injection.shell-true" in rule_ids
    assert res.has_high_or_critical() is True


def test_bandit_offline_scan(tmp_path: Path):
    vuln_file = tmp_path / "app.py"
    vuln_file.write_text(
        """
import subprocess

def test_fn():
    assert 1 == 1
    exec("print('dangerous')")
    subprocess.Popen("ls", shell=True)
""",
        encoding="utf-8",
    )

    scanner = BanditScanner()
    res = scanner.scan(vuln_file, force_offline_fallback=True)
    assert len(res.findings) >= 3
    rule_ids = {f.rule_id for f in res.findings}
    assert "bandit.B101" in rule_ids
    assert "bandit.B102" in rule_ids
    assert "bandit.B602" in rule_ids


def test_gitleaks_offline_scan(tmp_path: Path):
    secret_file = tmp_path / "config.py"
    secret_file.write_text(
        """
AWS_KEY = "AKIA1234567890ABCDEF"
RSA_KEY = "-----BEGIN RSA PRIVATE KEY-----"
api_key = "abcdef1234567890abcdef123456"
""",
        encoding="utf-8",
    )

    scanner = GitleaksScanner()
    res = scanner.scan(tmp_path, force_offline_fallback=True)
    assert len(res.findings) >= 3
    assert all(f.category == FindingCategory.SECRET for f in res.findings)
    assert any(f.severity == Severity.CRITICAL for f in res.findings)

    # Entropy test
    entropy_high = GitleaksScanner.shannon_entropy("8fA9xL!2#qZ91$kL09mN")
    entropy_low = GitleaksScanner.shannon_entropy("aaaaaaaaaaaaaaaaaaaa")
    assert entropy_high > entropy_low


def test_osv_offline_scan(tmp_path: Path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("requests==2.31.0\nurllib3==1.26.17\n", encoding="utf-8")

    scanner = OSVScanner()
    res = scanner.scan(tmp_path, force_offline_fallback=True)
    assert len(res.findings) >= 2
    cves = {f.cve_id for f in res.findings}
    assert "CVE-2023-32681" in cves
    assert "CVE-2023-45803" in cves


def test_pip_audit_offline_scan(tmp_path: Path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("jinja2==3.1.2\naiohttp==3.8.5\n", encoding="utf-8")

    scanner = PipAuditScanner()
    res = scanner.scan(tmp_path, force_offline_fallback=True)
    assert len(res.findings) >= 2
    cves = {f.cve_id for f in res.findings}
    assert "CVE-2024-22195" in cves
    assert "CVE-2023-47627" in cves


def test_trivy_offline_scan(tmp_path: Path):
    dfile = tmp_path / "Dockerfile"
    dfile.write_text(
        """
FROM python:latest
WORKDIR /app
COPY . .
CMD ["python", "app.py"]
""",
        encoding="utf-8",
    )

    scanner = TrivyScanner()
    res = scanner.scan(tmp_path, force_offline_fallback=True)
    assert len(res.findings) >= 2
    rule_ids = {f.rule_id for f in res.findings}
    assert "DS001" in rule_ids
    assert "DS002" in rule_ids


def test_syft_offline_sbom(tmp_path: Path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("pydantic==2.8.2\nfastapi==0.111.0\n", encoding="utf-8")

    scanner = SyftScanner()
    doc = scanner.generate_sbom(tmp_path, force_offline=True)
    assert doc.format == "cyclonedx-json"
    assert len(doc.components) == 2
    names = {c.name for c in doc.components}
    assert "pydantic" in names
    assert "fastapi" in names

    payload = json.loads(doc.raw_content)
    assert payload["bomFormat"] == "CycloneDX"
    assert payload["specVersion"] == "1.5"


def test_multi_scanner_engine_deduplication(tmp_path: Path):
    code_file = tmp_path / "vuln.py"
    code_file.write_text(
        """
import subprocess
eval("1+1")
AWS_KEY = "AKIA1234567890ABCDEF"
subprocess.call("ls", shell=True)
""",
        encoding="utf-8",
    )
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("requests==2.31.0\n", encoding="utf-8")

    engine = MultiScannerEngine()
    res = engine.scan(tmp_path, force_offline=True)
    assert res.metadata is not None
    assert res.metadata.scanner == "multi-scanner-engine"
    assert len(res.findings) > 0
    assert res.has_high_or_critical() is True
