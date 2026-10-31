from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import Any

from faccoder_security.models import Finding, ScanMetadata, ScanResult
from faccoder_security.scanners.bandit import BanditScanner
from faccoder_security.scanners.base import BaseScanner
from faccoder_security.scanners.gitleaks import GitleaksScanner
from faccoder_security.scanners.osv import OSVScanner
from faccoder_security.scanners.pip_audit import PipAuditScanner
from faccoder_security.scanners.semgrep import SemgrepScanner
from faccoder_security.scanners.syft import SyftScanner
from faccoder_security.scanners.trivy import TrivyScanner


class MultiScannerEngine:
    """Unified engine to run multiple security scanners with deduplication."""

    def __init__(self) -> None:
        self.scanners: dict[str, BaseScanner] = {
            "semgrep": SemgrepScanner(),
            "bandit": BanditScanner(),
            "gitleaks": GitleaksScanner(),
            "osv-scanner": OSVScanner(),
            "pip-audit": PipAuditScanner(),
            "trivy": TrivyScanner(),
            "syft": SyftScanner(),
        }

    def register_scanner(self, name: str, scanner: BaseScanner) -> None:
        self.scanners[name.lower()] = scanner

    def scan(
        self,
        target_path: str | Path,
        enabled_scanners: list[str] | None = None,
        force_offline: bool = False,
        options: dict[str, Any] | None = None,
    ) -> ScanResult:
        start_time = time.perf_counter()
        target = Path(target_path)

        selected_names = [s.lower() for s in enabled_scanners] if enabled_scanners else list(self.scanners.keys())
        all_findings: list[Finding] = []

        for name in selected_names:
            scanner = self.scanners.get(name)
            if not scanner:
                continue
            with contextlib.suppress(Exception):
                res = scanner.scan(target, options=options, force_offline_fallback=force_offline)
                all_findings.extend(res.findings)

        deduplicated = self._deduplicate(all_findings)
        duration = round(time.perf_counter() - start_time, 4)

        metadata = ScanMetadata(
            scanner="multi-scanner-engine",
            version="1.0.0",
            target_path=str(target),
            duration_seconds=duration,
            success=True,
        )

        return ScanResult(
            scanner="multi-scanner-engine",
            target_path=str(target),
            findings=deduplicated,
            metadata=metadata,
        )

    def _deduplicate(self, findings: list[Finding]) -> list[Finding]:
        seen: set[str] = set()
        unique: list[Finding] = []

        for f in findings:
            loc_key = ""
            if f.location:
                loc_key = f"{f.location.file_path}:{f.location.line_start}"
            key = f"{f.category.value}:{f.cve_id or f.rule_id}:{loc_key}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(f)

        return unique
