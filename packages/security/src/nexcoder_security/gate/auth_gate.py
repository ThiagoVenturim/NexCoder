"""Single authorization gate for active target scans and tests (Issue #106)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nexcoder_control.approval import (
    AuthorizationDocument,
    AuthorizationGateBlockedError,
    TargetAuthorizationGate,
    TargetAuthorizationRecord,
    TargetNotAuthorizedError,
    generate_keypair,
    is_local_or_owned_target,
    load_authorization_document,
    sign_authorization_document,
    verify_signed_document,
)
from nexcoder_control.metering.audit import AppendOnlyAuditLog


def gate_active_scan(
    target: str | Path,
    action: str = "security_scan",
    *,
    authorization_document: AuthorizationDocument | str | Path | dict[str, Any] | None = None,
    owned_target: bool = False,
    authorized_by: str | None = None,
    target_gate: TargetAuthorizationGate | None = None,
    audit_log: AppendOnlyAuditLog | None = None,
    trusted_public_keys: list[str] | set[str] | None = None,
    require_signed_document: bool = False,
    metadata: dict[str, Any] | None = None,
) -> TargetAuthorizationRecord:
    """Single point of gate for active scans, tests, or probes against any target.

    Hard block + fail-closed: default NEGAR.
    If no valid authorization is present, raises TargetNotAuthorizedError
    and records the denial in the control plane AppendOnlyAuditLog.
    """
    effective_log = audit_log or (target_gate.audit_log if target_gate is not None else AppendOnlyAuditLog())
    effective_gate = target_gate or TargetAuthorizationGate(
        audit_log=effective_log,
        trusted_public_keys=trusted_public_keys,
    )
    if trusted_public_keys:
        for k in trusted_public_keys:
            effective_gate.add_trusted_public_key(k)

    is_local = is_local_or_owned_target(target)
    must_require_doc = require_signed_document or (not is_local and not effective_gate.is_target_authorized(target))

    return effective_gate.verify_target(
        target=target,
        mode=action,
        owned_target=owned_target,
        authorized_by=authorized_by,
        authorization_document=authorization_document,
        require_signed_document=must_require_doc,
        metadata=metadata,
    )


__all__ = [
    "AuthorizationDocument",
    "AuthorizationGateBlockedError",
    "TargetAuthorizationGate",
    "TargetAuthorizationRecord",
    "TargetNotAuthorizedError",
    "gate_active_scan",
    "generate_keypair",
    "is_local_or_owned_target",
    "load_authorization_document",
    "sign_authorization_document",
    "verify_signed_document",
]
