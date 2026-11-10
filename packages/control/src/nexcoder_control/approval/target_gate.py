"""Target ownership and authorization gate for scanning and testing modes."""

from __future__ import annotations

import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from nexcoder_control.approval.tokens import ApprovalRequiredError, ApprovalTokenManager
from nexcoder_control.auth.base import ForbiddenError
from nexcoder_control.metering.audit import AppendOnlyAuditLog

TargetOwnership = Literal["owned", "authorized"]

_SECRET_KEY_FRAGMENTS = (
    "secret",
    "token",
    "password",
    "passwd",
    "pwd",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
    "authorization",
    "auth_header",
    "bearer",
    "client_secret",
)

_SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"fc_apr_[A-Za-z0-9_-]+"),
    re.compile(r"fc_[A-Za-z0-9]+_[A-Za-z0-9_-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)(?:password|passwd|secret|api_key|apikey|token)\s*[:=]\s*['\"]?[^\s'\";,]+"),
    re.compile(r"://[^/\s:@]+:[^/\s@]+@"),
)


def _redact_string(value: str) -> str:
    """Redact secret patterns embedded inside string values."""
    redacted = value
    for pattern in _SECRET_VALUE_PATTERNS:
        if pattern.pattern == r"://[^/\s:@]+:[^/\s@]+@":
            redacted = pattern.sub("://[REDACTED]@", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redact_secrets(data: Any) -> Any:
    """Recursively redact sensitive keys and secret patterns from audit payloads."""
    if data is None:
        return {}
    if isinstance(data, str):
        return _redact_string(data)
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for k, v in data.items():
            key_str = str(k)
            key_lower = key_str.lower()
            if any(frag in key_lower for frag in _SECRET_KEY_FRAGMENTS):
                sanitized[key_str] = "[REDACTED]"
            else:
                sanitized[key_str] = redact_secrets(v)
        return sanitized
    if isinstance(data, list):
        return [redact_secrets(item) for item in data]
    if isinstance(data, tuple):
        return [redact_secrets(item) for item in data]
    return data


def normalize_target(target: str | Path) -> str:
    """Normalize a filesystem path or URL target identifier."""
    if isinstance(target, Path):
        return _redact_string(str(target.resolve()))
    raw = str(target).strip()
    if not raw:
        raise ValueError("Target cannot be empty")
    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https", "file", "ssh", "git"):
        return _redact_string(raw)
    return _redact_string(str(Path(raw).resolve()))


class TargetNotAuthorizedError(ForbiddenError):
    """Raised when a scan or test mode runs against an unmarked or unauthorized target."""

    def __init__(self, target: str, mode: str = "scan", reason: str | None = None) -> None:
        detail = reason or (
            f"Target '{target}' is not marked as owned or explicitly authorized for mode '{mode}'. "
            "Per USAGE_POLICY.md, testing and scanning modes require the target to be marked as owned "
            "(owned_target=True or registered in TargetAuthorizationGate) or accompanied by a valid approval token."
        )
        super().__init__(message=detail, status_code=403)
        self.target = target
        self.mode = mode


class TargetAuthorizationRecord(BaseModel):
    """Audit-backed authorization record for an owned or approved scan/test target."""

    target: str
    authorized_by: str
    ownership: TargetOwnership = "owned"
    authorized_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: str = "scan"
    approval_token_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TargetAuthorizationGate:
    """Enforces USAGE_POLICY.md target ownership rules and logs decisions to AppendOnlyAuditLog."""

    def __init__(
        self,
        audit_log: AppendOnlyAuditLog | None = None,
        token_manager: ApprovalTokenManager | None = None,
    ) -> None:
        self.audit_log = audit_log if audit_log is not None else AppendOnlyAuditLog()
        self.token_manager = token_manager if token_manager is not None else ApprovalTokenManager()
        self._targets: dict[str, TargetAuthorizationRecord] = {}
        self._lock = threading.Lock()

    def mark_owned_target(
        self,
        target: str | Path,
        authorized_by: str,
        ownership: TargetOwnership = "owned",
        mode: str = "scan",
        metadata: dict[str, Any] | None = None,
    ) -> TargetAuthorizationRecord:
        """Register a target as owned or explicitly authorized and record in audit log."""
        clean_actor = authorized_by.strip()
        if not clean_actor:
            raise ValueError("authorized_by cannot be empty")

        norm_target = normalize_target(target)
        safe_meta = redact_secrets(metadata or {})
        now = datetime.now(UTC)

        record = TargetAuthorizationRecord(
            target=norm_target,
            authorized_by=clean_actor,
            ownership=ownership,
            authorized_at=now,
            mode=mode,
            metadata=safe_meta,
        )

        with self._lock:
            self._targets[norm_target] = record

        self.audit_log.record_event(
            event_type="target.marked_owned",
            actor=clean_actor,
            action="mark_owned",
            resource=norm_target,
            severity="info",
            details={
                "target": norm_target,
                "authorized_by": clean_actor,
                "authorized_at": now.isoformat(),
                "ownership": ownership,
                "mode": mode,
                "metadata": safe_meta,
            },
        )
        return record.model_copy()

    def revoke_target(self, target: str | Path, revoked_by: str = "admin") -> None:
        """Remove a previously registered target authorization."""
        norm_target = normalize_target(target)
        with self._lock:
            self._targets.pop(norm_target, None)

        self.audit_log.record_event(
            event_type="target.authorization.revoked",
            actor=revoked_by.strip() or "admin",
            action="revoke_target",
            resource=norm_target,
            severity="warning",
            details={"target": norm_target, "revoked_by": revoked_by.strip() or "admin"},
        )

    def is_target_authorized(self, target: str | Path) -> bool:
        """Return True if the target is currently pre-registered as owned/authorized."""
        norm_target = normalize_target(target)
        with self._lock:
            return norm_target in self._targets

    def list_authorized_targets(self) -> list[TargetAuthorizationRecord]:
        """List all pre-registered owned/authorized targets."""
        with self._lock:
            return [r.model_copy() for r in self._targets.values()]

    def verify_target(
        self,
        target: str | Path,
        mode: str = "scan",
        *,
        owned_target: bool = False,
        authorized_by: str | None = None,
        approval_token: str | None = None,
        dry_run: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> TargetAuthorizationRecord:
        """Verify that a target is marked as owned or authorized before running a scan/test.

        Records every granted or denied check in the AppendOnlyAuditLog (with secrets redacted)
        and raises TargetNotAuthorizedError if the target is not marked as owned or authorized.
        """
        norm_target = normalize_target(target)
        safe_meta = redact_secrets(metadata or {})
        clean_actor = (authorized_by or "").strip()
        now = datetime.now(UTC)

        # 1. Check approval token if supplied
        if approval_token is not None:
            try:
                # Try matching normalized target first, then raw string target
                try:
                    tok_record = self.token_manager.verify_and_consume(
                        raw_token=approval_token,
                        action_name=mode,
                        target_resource=norm_target,
                        dry_run=dry_run,
                    )
                except ApprovalRequiredError:
                    raw_target_str = _redact_string(str(target).strip())
                    if raw_target_str != norm_target:
                        tok_record = self.token_manager.verify_and_consume(
                            raw_token=approval_token,
                            action_name=mode,
                            target_resource=raw_target_str,
                            dry_run=dry_run,
                        )
                    else:
                        raise
            except ApprovalRequiredError as exc:
                actor_name = clean_actor or "unverified"
                self.audit_log.record_event(
                    event_type="target.authorization.denied",
                    actor=actor_name,
                    action=mode,
                    resource=norm_target,
                    severity="warning",
                    details={
                        "target": norm_target,
                        "authorized_by": actor_name,
                        "attempted_at": now.isoformat(),
                        "mode": mode,
                        "status": "denied",
                        "reason": str(exc),
                        "metadata": safe_meta,
                    },
                )
                raise TargetNotAuthorizedError(
                    target=norm_target,
                    mode=mode,
                    reason=(
                        f"Target '{norm_target}' authorization failed for mode '{mode}': {exc}. "
                        "Per USAGE_POLICY.md, scans and tests require a valid approval token or owned_target=True."
                    ),
                ) from exc

            actor_name = clean_actor or tok_record.approver
            record = TargetAuthorizationRecord(
                target=norm_target,
                authorized_by=actor_name,
                ownership="authorized",
                authorized_at=now,
                mode=mode,
                approval_token_id=tok_record.token_id,
                metadata=safe_meta,
            )
            self.audit_log.record_event(
                event_type="target.authorization.granted",
                actor=actor_name,
                action=mode,
                resource=norm_target,
                severity="info",
                details={
                    "target": norm_target,
                    "authorized_by": actor_name,
                    "authorized_at": now.isoformat(),
                    "ownership": "authorized",
                    "approval_token_id": tok_record.token_id,
                    "mode": mode,
                    "status": "authorized",
                    "metadata": safe_meta,
                },
            )
            return record

        # 2. Check pre-registered owned/authorized targets
        with self._lock:
            existing = self._targets.get(norm_target)

        if existing is not None:
            actor_name = clean_actor or existing.authorized_by
            record = TargetAuthorizationRecord(
                target=norm_target,
                authorized_by=actor_name,
                ownership=existing.ownership,
                authorized_at=now,
                mode=mode,
                metadata={**existing.metadata, **safe_meta},
            )
            self.audit_log.record_event(
                event_type="target.authorization.granted",
                actor=actor_name,
                action=mode,
                resource=norm_target,
                severity="info",
                details={
                    "target": norm_target,
                    "authorized_by": actor_name,
                    "authorized_at": now.isoformat(),
                    "ownership": existing.ownership,
                    "mode": mode,
                    "status": "authorized",
                    "metadata": record.metadata,
                },
            )
            return record

        # 3. Check explicit owned_target mark
        if owned_target:
            actor_name = clean_actor or "owner"
            record = TargetAuthorizationRecord(
                target=norm_target,
                authorized_by=actor_name,
                ownership="owned",
                authorized_at=now,
                mode=mode,
                metadata=safe_meta,
            )
            self.audit_log.record_event(
                event_type="target.authorization.granted",
                actor=actor_name,
                action=mode,
                resource=norm_target,
                severity="info",
                details={
                    "target": norm_target,
                    "authorized_by": actor_name,
                    "authorized_at": now.isoformat(),
                    "ownership": "owned",
                    "mode": mode,
                    "status": "authorized",
                    "metadata": safe_meta,
                },
            )
            return record

        # 4. Unmarked target -> refuse and record in audit log
        actor_name = clean_actor or "unverified"
        refusal_reason = (
            f"Target '{norm_target}' is not marked as owned or authorized for mode '{mode}'. "
            "Per USAGE_POLICY.md, testing and scanning modes only run against owned targets "
            "(pass owned_target=True / --owned-target or register via TargetAuthorizationGate) "
            "or with explicit owner authorization."
        )
        self.audit_log.record_event(
            event_type="target.authorization.denied",
            actor=actor_name,
            action=mode,
            resource=norm_target,
            severity="warning",
            details={
                "target": norm_target,
                "authorized_by": clean_actor or None,
                "attempted_at": now.isoformat(),
                "owned_target": False,
                "mode": mode,
                "status": "denied",
                "reason": refusal_reason,
                "metadata": safe_meta,
            },
        )
        raise TargetNotAuthorizedError(target=norm_target, mode=mode, reason=refusal_reason)
