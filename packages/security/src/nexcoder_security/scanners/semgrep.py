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


class SemgrepScanner(BaseScanner):
    """Wrapper and offline fallback scanner for Semgrep."""

    def __init__(self, executable_name: str = "semgrep") -> None:
        super().__init__(executable_name=executable_name, name="semgrep")

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
                cmd = [self.executable_name, "scan", "--json", "--quiet", str(target)]
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
                if proc.returncode in (0, 1):
                    raw_json = json.loads(proc.stdout)
                    return self._parse_semgrep_json(raw_json, target, start_time)
            except Exception as exc:
                logger.warning(
                    "Scanner '%s' CLI execution failed, falling back to heuristic engine: %s",
                    self.name,
                    exc,
                )

        return self._offline_scan(target, start_time)

    def _parse_semgrep_json(self, data: dict[str, Any], target: Path, start_time: float) -> Any:
        findings: list[Finding] = []
        for result in data.get("results", []):
            rule_id = result.get("check_id", "semgrep.rule")
            extra = result.get("extra", {})
            message = extra.get("message", "Semgrep finding")
            severity_str = extra.get("severity", "WARNING")
            metadata = extra.get("metadata", {})
            cwe = metadata.get("cwe", [])
            if isinstance(cwe, str):
                cwe = [cwe]

            loc = Location(
                file_path=result.get("path", str(target)),
                line_start=result.get("start", {}).get("line"),
                line_end=result.get("end", {}).get("line"),
                column_start=result.get("start", {}).get("col"),
                column_end=result.get("end", {}).get("col"),
                snippet=extra.get("lines"),
            )

            finding = Finding(
                id=f"semgrep-{len(findings) + 1}",
                scanner=self.name,
                rule_id=rule_id,
                title=rule_id.split(".")[-1].replace("-", " ").title(),
                description=message,
                severity=Severity.from_str(severity_str),
                category=FindingCategory.SAST,
                location=loc,
                cwe_ids=cwe,
                raw_data=result,
            )
            findings.append(finding)

        return self._create_result(target, findings, start_time, version="semgrep-cli", is_fallback=False)

    def _offline_scan(self, target: Path, start_time: float) -> Any:
        findings: list[Finding] = []
        rules = [
            (
                "python.security.injection.exec-detected",
                r"\b(exec|eval)\s*\(",
                "Use of dangerous dynamic execution (eval/exec)",
                Severity.HIGH,
                ["CWE-95"],
            ),
            (
                "python.security.injection.shell-true",
                r"subprocess\.\w+\(.*shell\s*=\s*True.*\)",
                "Subprocess execution with shell=True invites command injection",
                Severity.CRITICAL,
                ["CWE-78"],
            ),
            (
                "python.security.sqli.raw-string-format",
                r"\.execute\s*\(\s*f?[\"'].*%(s|d).*[\"']\s*%",
                "Direct string formatting in SQL query execution (potential SQLi)",
                Severity.HIGH,
                ["CWE-89"],
            ),
            (
                "python.security.insecure-deserialization.pickle",
                r"pickle\.(loads|load)\s*\(",
                "Untrusted deserialization with pickle",
                Severity.HIGH,
                ["CWE-502"],
            ),
        ]

        files_to_scan = [target] if target.is_file() else list(target.rglob("*.py"))
        for file_path in files_to_scan:
            with contextlib.suppress(Exception):
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()
                for rule_id, pattern, desc, sev, cwes in rules:
                    for line_idx, line in enumerate(lines, start=1):
                        if re.search(pattern, line):
                            finding = Finding(
                                id=f"semgrep-offline-{len(findings) + 1}",
                                scanner=self.name,
                                rule_id=rule_id,
                                title=desc,
                                description=f"{desc} detected at line {line_idx}",
                                severity=sev,
                                category=FindingCategory.SAST,
                                location=Location(
                                    file_path=str(file_path),
                                    line_start=line_idx,
                                    line_end=line_idx,
                                    snippet=line.strip(),
                                ),
                                cwe_ids=cwes,
                                remediation=Remediation(
                                    summary="Refactor to avoid dynamic evaluation or parameterized queries."
                                ),
                            )
                            findings.append(finding)

        return self._create_result(target, findings, start_time, version="semgrep-offline-engine", is_fallback=True)
