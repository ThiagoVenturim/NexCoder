from __future__ import annotations

import abc
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faccoder_security.models import Finding, ScanMetadata, ScanResult


class BaseScanner(abc.ABC):
    """Abstract base class for security scanners."""

    def __init__(self, executable_name: str, name: str | None = None) -> None:
        self.executable_name = executable_name
        self.name = name or executable_name

    def is_available(self) -> bool:
        """Check if the external scanner CLI binary is available on PATH."""
        return shutil.which(self.executable_name) is not None

    @abc.abstractmethod
    def scan(
        self,
        target_path: str | Path,
        options: dict[str, Any] | None = None,
        force_offline_fallback: bool = False,
    ) -> ScanResult:
        """Execute scan against target directory or file.

        If external binary is missing or force_offline_fallback=True,
        must perform offline heuristic/fallback scan.
        """
        ...

    def _create_result(
        self,
        target_path: str | Path,
        findings: list[Finding],
        start_time: float,
        success: bool = True,
        error_message: str | None = None,
        version: str = "1.0.0-fallback",
        is_fallback: bool = False,
    ) -> ScanResult:
        duration = time.perf_counter() - start_time
        meta = ScanMetadata(
            scanner=self.name,
            version=version,
            target_path=str(target_path),
            duration_seconds=round(duration, 4),
            timestamp=datetime.now(UTC).isoformat(),
            success=success,
            error_message=error_message,
            is_fallback=is_fallback,
        )
        return ScanResult(
            scanner=self.name,
            target_path=str(target_path),
            findings=findings,
            metadata=meta,
            fallback_scanners=[self.name] if is_fallback else [],
        )
