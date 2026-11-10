from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from nexcoder_control.approval import (
    TargetAuthorizationGate,
    TargetAuthorizationRecord,
)
from nexcoder_control.metering.audit import AppendOnlyAuditLog

from nexcoder_security.models import Finding, SBOMDocument, ScanMetadata, ScanResult
from nexcoder_security.scanners.bandit import BanditScanner
from nexcoder_security.scanners.base import BaseScanner
from nexcoder_security.scanners.gitleaks import GitleaksScanner
from nexcoder_security.scanners.osv import OSVScanner
from nexcoder_security.scanners.pip_audit import PipAuditScanner
from nexcoder_security.scanners.semgrep import SemgrepScanner
from nexcoder_security.scanners.syft import SyftScanner
from nexcoder_security.scanners.trivy import TrivyScanner


class MultiScannerEngine:
    """Unified engine to run multiple security scanners with deduplication and target ownership gating."""

    def __init__(
        self,
        target_gate: TargetAuthorizationGate | None = None,
        audit_log: AppendOnlyAuditLog | None = None,
    ) -> None:
        if target_gate is not None:
            self.target_gate = target_gate
            self.audit_log = audit_log if audit_log is not None else target_gate.audit_log
        else:
            self.audit_log = audit_log if audit_log is not None else AppendOnlyAuditLog()
            self.target_gate = TargetAuthorizationGate(audit_log=self.audit_log)

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

    def authorize_target(
        self,
        target_path: str | Path,
        authorized_by: str = "owner",
        metadata: dict[str, Any] | None = None,
    ) -> TargetAuthorizationRecord:
        """Mark a target path as owned or explicitly authorized for scanning."""
        return self.target_gate.mark_owned_target(
            target=target_path,
            authorized_by=authorized_by,
            mode="security_scan",
            metadata=metadata,
        )

    def scan(
        self,
        target_path: str | Path,
        enabled_scanners: list[str] | None = None,
        force_offline: bool = False,
        options: dict[str, Any] | None = None,
        *,
        owned_target: bool = False,
        authorized_by: str = "owner",
        approval_token: str | None = None,
    ) -> ScanResult:
        self.target_gate.verify_target(
            target=target_path,
            mode="security_scan",
            owned_target=owned_target,
            authorized_by=authorized_by,
            approval_token=approval_token,
            metadata=options,
        )
        start_time = time.perf_counter()
        target = Path(target_path)

        selected_names = [s.lower() for s in enabled_scanners] if enabled_scanners else list(self.scanners.keys())
        all_findings: list[Finding] = []
        scanner_errors: list[str] = []
        fallbacks_used: list[str] = []
        generated_sbom: SBOMDocument | None = None

        for name in selected_names:
            scanner = self.scanners.get(name)
            if not scanner:
                continue
            try:
                res = scanner.scan(target, options=options, force_offline_fallback=force_offline)
                all_findings.extend(res.findings)
                if res.has_fallbacks():
                    fallbacks_used.extend(res.fallbacks or [name])
                if res.metadata and not res.metadata.success:
                    err_msg = res.metadata.error_message or "Unknown scanner failure"
                    scanner_errors.append(f"{name}: {err_msg}")
                if isinstance(scanner, SyftScanner):
                    try:
                        generated_sbom = scanner.generate_sbom(target, force_offline=force_offline)
                    except Exception as s_exc:
                        scanner_errors.append(f"syft-sbom: {s_exc}")
            except Exception as exc:
                scanner_errors.append(f"{name}: {exc}")

        deduplicated = self._deduplicate(all_findings)
        duration = round(time.perf_counter() - start_time, 4)

        success = len(scanner_errors) == 0
        error_msg = "; ".join(scanner_errors) if scanner_errors else None

        unique_fallbacks = list(dict.fromkeys(fallbacks_used))

        metadata = ScanMetadata(
            scanner="multi-scanner-engine",
            version="1.0.0",
            target_path=str(target),
            duration_seconds=duration,
            success=success,
            error_message=error_msg,
            is_fallback=len(unique_fallbacks) > 0,
        )

        return ScanResult(
            scanner="multi-scanner-engine",
            target_path=str(target),
            findings=deduplicated,
            metadata=metadata,
            errors=scanner_errors,
            sbom=generated_sbom,
            fallbacks=unique_fallbacks,
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
