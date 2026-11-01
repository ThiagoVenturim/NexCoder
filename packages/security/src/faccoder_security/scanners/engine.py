from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from faccoder_security.models import Finding, SBOMDocument, ScanMetadata, ScanResult
from faccoder_security.scanners.bandit import BanditScanner
from faccoder_security.scanners.base import BaseScanner
from faccoder_security.scanners.gitleaks import GitleaksScanner
from faccoder_security.scanners.osv import OSVScanner
from faccoder_security.scanners.pip_audit import PipAuditScanner
from faccoder_security.scanners.semgrep import SemgrepScanner
from faccoder_security.scanners.syft import SyftScanner
from faccoder_security.scanners.trivy import TrivyScanner

logger = logging.getLogger(__name__)


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
        scanner_errors: list[str] = []
        fallback_scanners: list[str] = []
        generated_sbom: SBOMDocument | None = None

        for name in selected_names:
            scanner = self.scanners.get(name)
            if not scanner:
                continue
            try:
                res = scanner.scan(target, options=options, force_offline_fallback=force_offline)
                all_findings.extend(res.findings)
                if res.metadata:
                    if not res.metadata.success:
                        err_msg = res.metadata.error_message or "Unknown scanner failure"
                        scanner_errors.append(f"{name}: {err_msg}")
                    if res.metadata.is_fallback:
                        fallback_scanners.append(name)
                if isinstance(scanner, SyftScanner):
                    try:
                        generated_sbom = scanner.generate_sbom(target, force_offline=force_offline)
                    except Exception as s_exc:
                        logger.exception("Syft SBOM generation failed: %s", s_exc)
                        scanner_errors.append(f"syft-sbom: {s_exc}")
            except Exception as exc:
                logger.exception("Scanner '%s' failed during execution: %s", name, exc)
                scanner_errors.append(f"{name}: {exc}")

        deduplicated = self._deduplicate(all_findings)
        duration = round(time.perf_counter() - start_time, 4)

        success = len(scanner_errors) == 0
        error_msg = "; ".join(scanner_errors) if scanner_errors else None

        metadata = ScanMetadata(
            scanner="multi-scanner-engine",
            version="1.0.0",
            target_path=str(target),
            duration_seconds=duration,
            success=success,
            error_message=error_msg,
            is_fallback=bool(fallback_scanners),
        )

        return ScanResult(
            scanner="multi-scanner-engine",
            target_path=str(target),
            findings=deduplicated,
            metadata=metadata,
            errors=scanner_errors,
            fallback_scanners=fallback_scanners,
            sbom=generated_sbom,
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
