"""Tamper-evident, cryptographically chained, append-only audit logger."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AuditSeverity = Literal["info", "warning", "error", "critical"]


class AuditEvent(BaseModel):
    """Immutable audit record containing cryptographic parent link."""

    event_id: str
    sequence_no: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    actor: str
    action: str
    resource: str
    severity: AuditSeverity = "info"
    prev_hash: str
    event_hash: str
    details: dict[str, Any] = Field(default_factory=dict)


def compute_event_hash(
    sequence_no: int,
    timestamp: datetime,
    event_type: str,
    actor: str,
    action: str,
    resource: str,
    severity: str,
    prev_hash: str,
    details: dict[str, Any],
) -> str:
    """Compute deterministic SHA-256 digest of audit event fields."""
    canonical_details = json.dumps(details, sort_keys=True, separators=(",", ":"), default=str)
    raw = (
        f"{sequence_no}|{timestamp.isoformat()}|{event_type}|{actor}|"
        f"{action}|{resource}|{severity}|{prev_hash}|{canonical_details}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AppendOnlyAuditLog:
    """Thread-safe append-only audit log with SHA-256 blockchain-style chaining."""

    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(
        self,
        db_url: str | None = None,
        engine: Any = None,
        auto_persist: bool = True,
    ) -> None:
        self._events: list[AuditEvent] = []
        self._lock = threading.Lock()
        self._engine: Any = None
        self._table: Any = None

        target_url = db_url
        if target_url is None and engine is None:
            target_url = os.environ.get("DB_URL") or os.environ.get("NEXCODER_DB_URL")

        if auto_persist and (target_url is not None or engine is not None):
            from nexcoder_core.store.db import create_db_engine, get_metadata, init_db
            from sqlalchemy import select

            self._engine = engine or create_db_engine(target_url)
            self._metadata = get_metadata()
            init_db(self._engine)
            self._table = self._metadata.tables["audit_events"]

            # Load existing events in sequence order
            with self._engine.connect() as conn:
                stmt = select(self._table).order_by(self._table.c.sequence_no.asc())
                rows = conn.execute(stmt).fetchall()
                for r in rows:
                    details = json.loads(r.details_json) if isinstance(r.details_json, str) else (r.details_json or {})
                    ts = r.timestamp
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                    evt = AuditEvent(
                        event_id=r.event_id,
                        sequence_no=r.sequence_no,
                        timestamp=ts,
                        event_type=r.event_type,
                        actor=r.actor,
                        action=r.action,
                        resource=r.resource,
                        severity=r.severity,
                        prev_hash=r.prev_hash,
                        event_hash=r.event_hash,
                        details=details,
                    )
                    self._events.append(evt)

    def record_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        resource: str,
        severity: AuditSeverity = "info",
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Append a new verified tamper-evident event to the audit ledger."""
        event_details = details or {}
        now = datetime.now(UTC)

        with self._lock:
            seq = len(self._events) + 1
            prev_hash = self._events[-1].event_hash if self._events else self.GENESIS_HASH

            event_hash = compute_event_hash(
                sequence_no=seq,
                timestamp=now,
                event_type=event_type,
                actor=actor,
                action=action,
                resource=resource,
                severity=severity,
                prev_hash=prev_hash,
                details=event_details,
            )

            event = AuditEvent(
                event_id=f"evt_{seq}_{event_hash[:12]}",
                sequence_no=seq,
                timestamp=now,
                event_type=event_type,
                actor=actor,
                action=action,
                resource=resource,
                severity=severity,
                prev_hash=prev_hash,
                event_hash=event_hash,
                details=event_details,
            )
            self._events.append(event)

            if self._engine is not None and self._table is not None:
                with self._engine.begin() as conn:
                    insert_stmt = self._table.insert().values(
                        event_id=event.event_id,
                        sequence_no=event.sequence_no,
                        timestamp=event.timestamp,
                        event_type=event.event_type,
                        actor=event.actor,
                        action=event.action,
                        resource=event.resource,
                        severity=event.severity,
                        prev_hash=event.prev_hash,
                        event_hash=event.event_hash,
                        details_json=json.dumps(event.details, sort_keys=True, default=str),
                    )
                    conn.execute(insert_stmt)

            return event

    def verify_integrity(self) -> tuple[bool, str]:
        """Verify cryptographic hash chaining from genesis to current tip.

        Returns (is_valid, message).
        """
        with self._lock:
            events = list(self._events)

        expected_prev = self.GENESIS_HASH
        for idx, evt in enumerate(events):
            expected_seq = idx + 1
            if evt.sequence_no != expected_seq:
                return False, f"Broken sequence at index {idx}: expected {expected_seq}, got {evt.sequence_no}"

            if evt.prev_hash != expected_prev:
                return (
                    False,
                    f"Hash chain broken at sequence {evt.sequence_no}: "
                    f"expected prev_hash {expected_prev}, got {evt.prev_hash}",
                )

            recomputed = compute_event_hash(
                sequence_no=evt.sequence_no,
                timestamp=evt.timestamp,
                event_type=evt.event_type,
                actor=evt.actor,
                action=evt.action,
                resource=evt.resource,
                severity=evt.severity,
                prev_hash=evt.prev_hash,
                details=evt.details,
            )
            if recomputed != evt.event_hash:
                return False, f"Tampered event payload at sequence {evt.sequence_no}: hash mismatch"

            expected_prev = evt.event_hash

        return True, f"Ledger integrity verified: {len(events)} events intact"

    def query(
        self,
        event_type: str | None = None,
        actor: str | None = None,
        severity: AuditSeverity | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Query events matching optional criteria in reverse chronological order."""
        with self._lock:
            filtered = list(self._events)

        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]
        if actor:
            filtered = [e for e in filtered if e.actor == actor]
        if severity:
            filtered = [e for e in filtered if e.severity == severity]
        if since:
            filtered = [e for e in filtered if e.timestamp >= since]

        return list(reversed(filtered[-limit:]))

    def record_security_review(
        self,
        *,
        actor: str,
        target: str,
        mode: str = "security_review",
        findings_count: int = 0,
        severity_counts: dict[str, int] | None = None,
        passed_gate: bool = True,
        disclosure_mode: str = "responsible",
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Record a completed security review in the audit log with secrets redacted."""
        from nexcoder_control.approval.target_gate import redact_secrets

        safe_details = redact_secrets(details or {})
        safe_target = str(redact_secrets(target))
        payload: dict[str, Any] = {
            "target": safe_target,
            "mode": mode,
            "findings_count": findings_count,
            "severity_counts": dict(severity_counts or {}),
            "passed_gate": passed_gate,
            "disclosure_mode": disclosure_mode,
            "exploit_published": False,
        }
        if isinstance(safe_details, dict):
            payload.update(safe_details)
            payload["exploit_published"] = False

        sev: AuditSeverity = "warning" if not passed_gate or findings_count > 0 else "info"
        return self.record_event(
            event_type="security.review.completed",
            actor=actor.strip() or "security-reviewer",
            action=mode,
            resource=safe_target,
            severity=sev,
            details=payload,
        )

    def record_runtime_monitor_event(
        self,
        *,
        actor: str = "runtime-monitor",
        action: str,
        resource: str,
        blocked: bool,
        rule_id: str,
        reason: str,
        severity: AuditSeverity = "warning",
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Record a runtime security monitor inspection or block event with secrets redacted."""
        from nexcoder_control.approval.target_gate import redact_secrets

        safe_details = redact_secrets(details or {})
        safe_resource = str(redact_secrets(resource))
        event_type = "security.monitor.blocked" if blocked else "security.monitor.inspected"
        payload: dict[str, Any] = {
            "blocked": blocked,
            "rule_id": rule_id,
            "reason": str(redact_secrets(reason)),
        }
        if isinstance(safe_details, dict):
            payload.update(safe_details)

        return self.record_event(
            event_type=event_type,
            actor=actor.strip() or "runtime-monitor",
            action=action,
            resource=safe_resource,
            severity=severity,
            details=payload,
        )

