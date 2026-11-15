"""Audit integration for server exposure, hardening, and data masking operations."""

from __future__ import annotations

from typing import Any

from nexcoder_control.metering.audit import AppendOnlyAuditLog


def audit_server_action(
    action: str,
    resource: str,
    details: dict[str, Any] | None = None,
    audit_log: AppendOnlyAuditLog | None = None,
    actor: str = "nexcoder-security",
) -> None:
    """Record an exposure, hardening, or masking event into the append-only cryptographic audit log."""
    log = audit_log or AppendOnlyAuditLog()
    event_details = details or {}
    log.record_event(
        event_type=f"server_{action}",
        actor=actor,
        action=action,
        resource=resource,
        severity="info",
        details=event_details,
    )
