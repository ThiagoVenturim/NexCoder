from __future__ import annotations

import ast
import contextlib
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from nexcoder_security.models import Finding, FindingCategory, Location, Remediation, Severity
from nexcoder_security.scanners.base import BaseScanner

logger = logging.getLogger(__name__)


class BanditScanner(BaseScanner):
    """Wrapper and offline fallback scanner for Bandit."""

    def __init__(self, executable_name: str = "bandit") -> None:
        super().__init__(executable_name=executable_name, name="bandit")

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
                cmd = [self.executable_name, "-r", str(target), "-f", "json", "-q"]
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
                if proc.stdout.strip():
                    raw_json = json.loads(proc.stdout)
                    return self._parse_bandit_json(raw_json, target, start_time)
            except Exception as exc:
                logger.warning(
                    "Scanner '%s' CLI execution failed, falling back to heuristic engine: %s",
                    self.name,
                    exc,
                )

        return self._offline_scan(target, start_time)

    def _parse_bandit_json(self, data: dict[str, Any], target: Path, start_time: float) -> Any:
        findings: list[Finding] = []
        for issue in data.get("results", []):
            sev_str = issue.get("issue_severity", "MEDIUM")
            rule_id = issue.get("test_id", "B000")
            cwe = issue.get("issue_cwe", {})
            cwe_id = f"CWE-{cwe.get('id')}" if cwe.get("id") else "CWE-Unknown"

            loc = Location(
                file_path=issue.get("filename", str(target)),
                line_start=issue.get("line_number"),
                line_end=issue.get("line_range", [issue.get("line_number")])[-1],
                snippet=issue.get("code", "").strip(),
            )

            finding = Finding(
                id=f"bandit-{len(findings) + 1}",
                scanner=self.name,
                rule_id=f"bandit.{rule_id}",
                title=issue.get("test_name", "Bandit Security Issue"),
                description=issue.get("issue_text", ""),
                severity=Severity.from_str(sev_str),
                category=FindingCategory.SAST,
                location=loc,
                cwe_ids=[cwe_id],
                remediation=Remediation(
                    summary=f"Refer to Bandit test {rule_id}",
                    references=[issue.get("more_info", "")],
                ),
                raw_data=issue,
            )
            findings.append(finding)

        return self._create_result(target, findings, start_time, version="bandit-cli", is_fallback=False)

    def _offline_scan(self, target: Path, start_time: float) -> Any:
        findings: list[Finding] = []
        files = [target] if target.is_file() else list(target.rglob("*.py"))

        for fpath in files:
            with contextlib.suppress(Exception):
                code = fpath.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(code, filename=str(fpath))

                for node in ast.walk(tree):
                    # B101: assert used
                    if isinstance(node, ast.Assert):
                        findings.append(
                            Finding(
                                id=f"bandit-offline-{len(findings) + 1}",
                                scanner=self.name,
                                rule_id="bandit.B101",
                                title="Use of assert detected",
                                description="Assert statements can be removed with Python -O flag",
                                severity=Severity.LOW,
                                category=FindingCategory.SAST,
                                location=Location(
                                    file_path=str(fpath),
                                    line_start=node.lineno,
                                    line_end=node.lineno,
                                ),
                                cwe_ids=["CWE-617"],
                                remediation=Remediation(summary="Replace assert with proper condition validation"),
                            )
                        )
                    # B102: exec used
                    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "exec":
                        findings.append(
                            Finding(
                                id=f"bandit-offline-{len(findings) + 1}",
                                scanner=self.name,
                                rule_id="bandit.B102",
                                title="Use of exec detected",
                                description="exec() allows arbitrary code execution",
                                severity=Severity.HIGH,
                                category=FindingCategory.SAST,
                                location=Location(
                                    file_path=str(fpath),
                                    line_start=node.lineno,
                                    line_end=node.lineno,
                                ),
                                cwe_ids=["CWE-78"],
                                remediation=Remediation(summary="Avoid dynamic code execution"),
                            )
                        )
                    # B602: subprocess shell=True
                    elif isinstance(node, ast.Call):
                        is_shell_true = any(
                            kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                            for kw in node.keywords
                        )
                        if is_shell_true:
                            findings.append(
                                Finding(
                                    id=f"bandit-offline-{len(findings) + 1}",
                                    scanner=self.name,
                                    rule_id="bandit.B602",
                                    title="subprocess call with shell=True identified",
                                    description="shell=True exposes application to shell injection attacks",
                                    severity=Severity.HIGH,
                                    category=FindingCategory.SAST,
                                    location=Location(
                                        file_path=str(fpath),
                                        line_start=node.lineno,
                                        line_end=node.lineno,
                                    ),
                                    cwe_ids=["CWE-78"],
                                    remediation=Remediation(summary="Pass command arguments as list with shell=False"),
                                )
                            )

        return self._create_result(target, findings, start_time, version="bandit-offline-ast", is_fallback=True)
