from __future__ import annotations

import contextlib
import json
import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from nexcoder_security.models import Finding, FindingCategory, Location, Remediation, Severity
from nexcoder_security.scanners.base import BaseScanner

logger = logging.getLogger(__name__)


class TrivyScanner(BaseScanner):
    """Wrapper and offline misconfig/container/fs scanner for Trivy."""

    def __init__(self, executable_name: str = "trivy") -> None:
        super().__init__(executable_name=executable_name, name="trivy")

    def scan(
        self,
        target_path: str | Path,
        options: dict[str, Any] | None = None,
        force_offline_fallback: bool = False,
    ) -> Any:
        start_time = time.perf_counter()
        target = Path(target_path)

        if not force_offline_fallback and self.is_available():
            try:
                cmd = [self.executable_name, "fs", "--format", "json", "-q", str(target)]
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
                if proc.stdout.strip():
                    raw_json = json.loads(proc.stdout)
                    return self._parse_trivy_json(raw_json, target, start_time)
            except Exception as exc:
                logger.warning(
                    "Scanner '%s' CLI execution failed, falling back to heuristic engine: %s",
                    self.name,
                    exc,
                )

        return self._offline_scan(target, start_time)

    def _parse_trivy_json(self, data: dict[str, Any], target: Path, start_time: float) -> Any:
        findings: list[Finding] = []
        for result in data.get("Results", []):
            target_file = result.get("Target", str(target))

            # Vulnerabilities
            for vuln in result.get("Vulnerabilities", []):
                vuln_id = vuln.get("VulnerabilityID", "VULN-001")
                pkg_name = vuln.get("PkgName", "package")
                sev_str = vuln.get("Severity", "UNKNOWN")
                loc = Location(file_path=target_file, snippet=f"{pkg_name} {vuln.get('InstalledVersion', '')}")
                findings.append(
                    Finding(
                        id=f"trivy-{len(findings) + 1}",
                        scanner=self.name,
                        rule_id=vuln_id,
                        title=f"{pkg_name}: {vuln.get('Title', vuln_id)}",
                        description=vuln.get("Description", ""),
                        severity=Severity.from_str(sev_str),
                        category=FindingCategory.SCA,
                        location=loc,
                        cve_id=vuln_id if vuln_id.startswith("CVE-") else None,
                        remediation=Remediation(
                            summary=f"Upgrade {pkg_name} to {vuln.get('FixedVersion', 'latest')}",
                            recommended_version=vuln.get("FixedVersion"),
                        ),
                        raw_data=vuln,
                    )
                )

            # Misconfigurations
            for misconf in result.get("Misconfigurations", []):
                rule_id = misconf.get("ID", "MISCONF-001")
                sev_str = misconf.get("Severity", "MEDIUM")
                findings.append(
                    Finding(
                        id=f"trivy-{len(findings) + 1}",
                        scanner=self.name,
                        rule_id=rule_id,
                        title=misconf.get("Title", "Misconfiguration detected"),
                        description=misconf.get("Description", ""),
                        severity=Severity.from_str(sev_str),
                        category=FindingCategory.IAC,
                        location=Location(file_path=target_file),
                        remediation=Remediation(summary=misconf.get("Resolution", "Fix configuration")),
                        raw_data=misconf,
                    )
                )

        return self._create_result(target, findings, start_time, version="trivy-cli", is_fallback=False)

    def _offline_scan(self, target: Path, start_time: float) -> Any:
        findings: list[Finding] = []
        dockerfiles = (
            [target] if target.is_file() and "dockerfile" in target.name.lower() else list(target.rglob("*Dockerfile*"))
        )

        for dfile in dockerfiles:
            with contextlib.suppress(Exception):
                lines = dfile.read_text(encoding="utf-8", errors="ignore").splitlines()
                has_user = False
                for line_idx, line in enumerate(lines, start=1):
                    clean = line.strip()
                    if re.match(r"^USER\s+", clean, re.IGNORECASE):
                        has_user = True
                    # Root or sudo or latest tag check
                    if re.match(r"^FROM\s+\S+:latest", clean, re.IGNORECASE):
                        findings.append(
                            Finding(
                                id=f"trivy-offline-{len(findings) + 1}",
                                scanner=self.name,
                                rule_id="DS001",
                                title="Container image tagged with :latest",
                                description="Using ':latest' tag avoids reproducible and secure builds.",
                                severity=Severity.MEDIUM,
                                category=FindingCategory.CONTAINER,
                                location=Location(
                                    file_path=str(dfile),
                                    line_start=line_idx,
                                    snippet=clean,
                                ),
                                remediation=Remediation(
                                    summary="Pin base image to a specific version digest or semantic version tag."
                                ),
                            )
                        )
                if not has_user and lines:
                    findings.append(
                        Finding(
                            id=f"trivy-offline-{len(findings) + 1}",
                            scanner=self.name,
                            rule_id="DS002",
                            title="Container runs as root user",
                            description="Dockerfile does not specify a non-root USER instruction.",
                            severity=Severity.HIGH,
                            category=FindingCategory.CONTAINER,
                            location=Location(file_path=str(dfile), line_start=1),
                            remediation=Remediation(
                                summary="Add 'USER nonroot' or create a dedicated application user."
                            ),
                        )
                    )

        return self._create_result(target, findings, start_time, version="trivy-offline", is_fallback=True)
