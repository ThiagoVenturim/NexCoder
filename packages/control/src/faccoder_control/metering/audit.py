"""Tamper-evident, cryptographically chained, append-only audit logger."""

from __future__ import annotations

import hashlib
import json
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

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = threading.Lock()

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
