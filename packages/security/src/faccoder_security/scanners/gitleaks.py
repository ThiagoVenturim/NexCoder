from __future__ import annotations

import contextlib
import json
import math
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from faccoder_security.models import Finding, FindingCategory, Location, Remediation, Severity
from faccoder_security.scanners.base import BaseScanner


class GitleaksScanner(BaseScanner):
    """Wrapper and offline regex/entropy fallback scanner for Gitleaks."""

    def __init__(self, executable_name: str = "gitleaks") -> None:
        super().__init__(executable_name=executable_name, name="gitleaks")

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
                cmd = [
                    self.executable_name,
                    "detect",
                    "--no-git",
                    "--source",
                    str(target),
                    "--report-format",
                    "json",
                    "--exit-code",
                    "0",
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
                if proc.stdout.strip():
                    raw_json = json.loads(proc.stdout)
                    return self._parse_gitleaks_json(raw_json, target, start_time)

        return self._offline_scan(target, start_time)

    def _parse_gitleaks_json(self, items: list[dict[str, Any]], target: Path, start_time: float) -> Any:
        findings: list[Finding] = []
        for item in items:
            rule_id = item.get("RuleID", "generic-secret")
            desc = item.get("Description", "Secret detected")
            loc = Location(
                file_path=item.get("File", str(target)),
                line_start=item.get("StartLine"),
                line_end=item.get("EndLine"),
                snippet=item.get("Match", "secret redacted"),
            )
            finding = Finding(
                id=f"gitleaks-{len(findings) + 1}",
                scanner=self.name,
                rule_id=rule_id,
                title=f"Secret found: {desc}",
                description=f"Potential secret matched rule {rule_id}",
                severity=Severity.CRITICAL,
                category=FindingCategory.SECRET,
                location=loc,
                cwe_ids=["CWE-798"],
                remediation=Remediation(
                    summary="Revoke the secret immediately and move credentials to secure environment variables."
                ),
                raw_data=item,
            )
            findings.append(finding)

        return self._create_result(target, findings, start_time, version="gitleaks-cli")

    def _offline_scan(self, target: Path, start_time: float) -> Any:
        findings: list[Finding] = []
        patterns = [
            ("aws-access-key-id", r"(?i)\b(AKIA[0-9A-Z]{16})\b", "AWS Access Key ID", Severity.CRITICAL),
            (
                "private-key",
                r"-----BEGIN (RSA|OPENSSH|EC|PGP|DSA)? ?PRIVATE KEY-----",
                "Private Key block",
                Severity.CRITICAL,
            ),
            (
                "generic-api-key",
                r"""(?i)(?:api_key|apikey|secret_key|access_token)\s*[:=]\s*["']([A-Za-z0-9_\-]{24,})["']""",
                "Hardcoded API key or secret token",
                Severity.HIGH,
            ),
            (
                "jwt-token",
                r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
                "JSON Web Token (JWT)",
                Severity.HIGH,
            ),
        ]

        # Ignore virtualenvs, git directories, tests mocks
        ignore_dirs = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules"}

        if target.is_file():
            files = [target]
        else:
            files = [p for p in target.rglob("*") if p.is_file() and not any(part in ignore_dirs for part in p.parts)]

        for file_path in files:
            # Skip binary extensions
            if file_path.suffix.lower() in {".png", ".jpg", ".exe", ".dll", ".so", ".whl", ".pyc"}:
                continue
            with contextlib.suppress(Exception):
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                lines = text.splitlines()
                for line_num, line in enumerate(lines, start=1):
                    for rule_id, regex, desc, sev in patterns:
                        match = re.search(regex, line)
                        if match:
                            secret_snippet = match.group(0)
                            # Mask middle of secret in snippet
                            if len(secret_snippet) > 8:
                                masked = secret_snippet[:3] + "..." + secret_snippet[-3:]
                            else:
                                masked = "***"
                            findings.append(
                                Finding(
                                    id=f"gitleaks-offline-{len(findings) + 1}",
                                    scanner=self.name,
                                    rule_id=f"gitleaks.{rule_id}",
                                    title=f"Secret detected: {desc}",
                                    description=f"Potential secret pattern '{desc}' detected at line {line_num}",
                                    severity=sev,
                                    category=FindingCategory.SECRET,
                                    location=Location(
                                        file_path=str(file_path),
                                        line_start=line_num,
                                        line_end=line_num,
                                        snippet=f"Match: {masked}",
                                    ),
                                    cwe_ids=["CWE-798"],
                                    remediation=Remediation(
                                        summary="Revoke key, remove from source code, and use environment variables."
                                    ),
                                )
                            )

        return self._create_result(target, findings, start_time, version="gitleaks-offline-engine")

    @staticmethod
    def shannon_entropy(data: str) -> float:
        """Calculate Shannon entropy to detect high-randomness strings."""
        if not data:
            return 0.0
        entropy = 0.0
        length = len(data)
        frequencies: dict[str, int] = {}
        for char in data:
            frequencies[char] = frequencies.get(char, 0) + 1
        for count in frequencies.values():
            p_x = count / length
            entropy += -p_x * math.log2(p_x)
        return entropy
