from __future__ import annotations

import contextlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from faccoder_security.models import Finding, FindingCategory, Location, Remediation, Severity
from faccoder_security.scanners.base import BaseScanner


class OSVScanner(BaseScanner):
    """Wrapper and offline dependency vulnerability scanner for OSV-Scanner."""

    def __init__(self, executable_name: str = "osv-scanner") -> None:
        super().__init__(executable_name=executable_name, name="osv-scanner")

    def scan(
        self,
        target_path: str | Path,
        options: dict[str, Any] | None = None,
        force_offline_fallback: bool = False,
    ) -> Any:
        start_time = time.perf_counter()
        target = Path(target_path)

        if not force_offline_fallback and self.is_available():
            with contextlib.suppress(Exception):
                cmd = [self.executable_name, "--format", "json", "-r", str(target)]
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
                if proc.stdout.strip():
                    raw_json = json.loads(proc.stdout)
                    return self._parse_osv_json(raw_json, target, start_time)

        return self._offline_scan(target, start_time)

    def _parse_osv_json(self, data: dict[str, Any], target: Path, start_time: float) -> Any:
        findings: list[Finding] = []
        for res in data.get("results", []):
            source = res.get("source", {}).get("path", str(target))
            for pkg in res.get("packages", []):
                pkg_info = pkg.get("package", {})
                pkg_name = pkg_info.get("name", "unknown")
                pkg_ver = pkg_info.get("version", "")
                for vuln in pkg.get("vulnerabilities", []):
                    vuln_id = vuln.get("id", "GHSA-xxxx-xxxx")
                    aliases = vuln.get("aliases", [])
                    cve = next((a for a in aliases if a.startswith("CVE-")), None)
                    summary = vuln.get("summary", f"Vulnerability in {pkg_name}")
                    details = vuln.get("details", "")

                    sev_level = Severity.HIGH
                    for s in vuln.get("severity", []):
                        score = s.get("score")
                        if score and isinstance(score, str) and "CVSS" in score:
                            sev_level = Severity.CRITICAL

                    loc = Location(file_path=source, snippet=f"{pkg_name}=={pkg_ver}")
                    finding = Finding(
                        id=f"osv-{len(findings) + 1}",
                        scanner=self.name,
                        rule_id=vuln_id,
                        title=f"{pkg_name}: {summary}",
                        description=details or summary,
                        severity=sev_level,
                        category=FindingCategory.SCA,
                        location=loc,
                        cve_id=cve,
                        remediation=Remediation(
                            summary=f"Upgrade {pkg_name} to a fixed version.",
                            references=[f"https://osv.dev/vulnerability/{vuln_id}"],
                        ),
                        raw_data=vuln,
                    )
                    findings.append(finding)

        return self._create_result(target, findings, start_time, version="osv-cli")

    def _offline_scan(self, target: Path, start_time: float) -> Any:
        findings: list[Finding] = []
        known_vulns: dict[str, list[dict[str, Any]]] = {
            "requests": [
                {
                    "max_vuln_version": "2.31.0",
                    "cve": "CVE-2023-32681",
                    "id": "GHSA-j8r2-6x86-q33q",
                    "title": "Requests Proxy-Authorization header leak",
                    "severity": Severity.MEDIUM,
                    "fixed_in": "2.32.0",
                }
            ],
            "urllib3": [
                {
                    "max_vuln_version": "1.26.17",
                    "cve": "CVE-2023-45803",
                    "id": "GHSA-v845-jxx5-vc9f",
                    "title": "urllib3 request body leak on redirect",
                    "severity": Severity.HIGH,
                    "fixed_in": "1.26.18",
                }
            ],
            "django": [
                {
                    "max_vuln_version": "3.2.19",
                    "cve": "CVE-2023-36053",
                    "id": "GHSA-jhwh-59hd-875v",
                    "title": "Potential ReDoS in EmailValidator",
                    "severity": Severity.HIGH,
                    "fixed_in": "3.2.20",
                }
            ],
            "cryptography": [
                {
                    "max_vuln_version": "41.0.5",
                    "cve": "CVE-2023-49083",
                    "id": "GHSA-jfhm-5ghh-2f97",
                    "title": "NULL dereference in PKCS7 parsing",
                    "severity": Severity.HIGH,
                    "fixed_in": "41.0.6",
                }
            ],
        }

        req_files = [target] if target.is_file() else list(target.rglob("*requirements*.txt"))
        for rfile in req_files:
            with contextlib.suppress(Exception):
                lines = rfile.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line_idx, line in enumerate(lines, start=1):
                    line_clean = line.strip().split("#")[0].strip()
                    m = re.match(r"^([a-zA-Z0-9_\-]+)\s*==\s*([0-9a-zA-Z\.\-]+)", line_clean)
                    if m:
                        pkg_name = m.group(1).lower()
                        pkg_ver = m.group(2)
                        if pkg_name in known_vulns:
                            for v in known_vulns[pkg_name]:
                                finding = Finding(
                                    id=f"osv-offline-{len(findings) + 1}",
                                    scanner=self.name,
                                    rule_id=v["id"],
                                    title=f"{pkg_name} {pkg_ver}: {v['title']}",
                                    description=f"Known vulnerability {v['cve']} in {pkg_name} < {v['fixed_in']}",
                                    severity=v["severity"],
                                    category=FindingCategory.SCA,
                                    location=Location(
                                        file_path=str(rfile),
                                        line_start=line_idx,
                                        snippet=line_clean,
                                    ),
                                    cve_id=v["cve"],
                                    remediation=Remediation(
                                        summary=f"Upgrade {pkg_name} to version {v['fixed_in']} or newer.",
                                        recommended_version=v["fixed_in"],
                                    ),
                                )
                                findings.append(finding)

        return self._create_result(target, findings, start_time, version="osv-offline-engine")
