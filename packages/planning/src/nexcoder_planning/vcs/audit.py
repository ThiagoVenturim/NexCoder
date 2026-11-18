"""Audit logging for VCS and repository management operations."""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from nexcoder_planning.vcs.models import AuditRecord

logger = logging.getLogger(__name__)


class VCSAuditLogger:
    """Thread-safe in-memory and structured audit logger for repository operations."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    def record(
        self,
        provider: str,
        action: str,
        resource_type: str,
        resource_id: str = "",
        actor: str = "nexcoder",
        success: bool = True,
        error_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        """Record an audited event, sanitizing any sensitive parameters."""
        sanitized_details = self._sanitize_details(details or {})
        rec = AuditRecord(
            id=str(uuid.uuid4()),
            timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            provider=provider,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor=actor,
            success=success,
            error_message=error_message,
            details=sanitized_details,
        )
        self._records.append(rec)
        log_level = logging.INFO if success else logging.WARNING
        logger.log(
            log_level,
            "VCS Audit [%s] %s on %s:%s (success=%s)",
            provider,
            action,
            resource_type,
            resource_id,
            success,
        )
        return rec

    def list_records(
        self,
        provider: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        """Query audit log records with optional filters."""
        results: list[AuditRecord] = []
        for rec in reversed(self._records):
            if provider and rec.provider != provider:
                continue
            if action and rec.action != action:
                continue
            if resource_type and rec.resource_type != resource_type:
                continue
            results.append(rec)
            if len(results) >= limit:
                break
        return results

    def clear(self) -> None:
        """Clear recorded entries (primarily for testing)."""
        self._records.clear()

    @staticmethod
    def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
        """Strip sensitive credentials (tokens, secrets, passwords, PATs) from audit data."""
        sensitive_keys = {
            "token",
            "pat",
            "password",
            "secret",
            "authorization",
            "private_token",
            "bearer",
            "key",
        }
        sanitized: dict[str, Any] = {}
        for k, v in details.items():
            k_lower = k.lower()
            if any(s in k_lower for s in sensitive_keys):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = VCSAuditLogger._sanitize_details(v)
            else:
                sanitized[k] = v
        return sanitized


# Global audit logger instance
_GLOBAL_AUDIT_LOGGER = VCSAuditLogger()


def get_vcs_audit_logger() -> VCSAuditLogger:
    """Return the global audit logger instance for VCS actions."""
    return _GLOBAL_AUDIT_LOGGER
