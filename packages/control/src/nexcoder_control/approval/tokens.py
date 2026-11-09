"""Short-lived human approval tokens with dry-run support for high-risk actions."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from nexcoder_control.auth.base import ForbiddenError


class ApprovalRequiredError(ForbiddenError):
    """Raised when an operation requires valid human approval token."""

    def __init__(self, message: str = "High-risk operation requires human approval token") -> None:
        super().__init__(message=message, status_code=403)


class ApprovalTokenRecord(BaseModel):
    """Metadata of a generated single-use human approval token (secret is hashed)."""

    token_id: str
    action_name: str
    target_resource: str
    approver: str
    hashed_secret: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    is_consumed: bool = False
    consumed_at: datetime | None = None
    dry_run_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at


class ApprovalTokenManager:
    """Manages creation, verification, dry-run simulation, and consumption of human tokens."""

    def __init__(self, default_ttl_minutes: int = 15) -> None:
        self.default_ttl_minutes = default_ttl_minutes
        self._tokens: dict[str, ApprovalTokenRecord] = {}  # token_id -> record
        self._hash_to_id: dict[str, str] = {}  # hashed_secret -> token_id
        self._lock = threading.Lock()

    def issue_token(
        self,
        action_name: str,
        target_resource: str,
        approver: str,
        ttl_minutes: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ApprovalTokenRecord, str]:
        """Issue a short-lived single-use approval token. Returns (record, raw_secret)."""
        clean_action = action_name.strip()
        clean_resource = target_resource.strip()
        if not clean_action or not clean_resource:
            raise ValueError("action_name and target_resource cannot be empty")

        token_id = f"apr_{secrets.token_hex(8)}"
        raw_secret = f"fc_apr_{token_id}_{secrets.token_urlsafe(32)}"
        hashed = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()

        ttl = ttl_minutes if ttl_minutes is not None else self.default_ttl_minutes
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=ttl)

        record = ApprovalTokenRecord(
            token_id=token_id,
            action_name=clean_action,
            target_resource=clean_resource,
            approver=approver,
            hashed_secret=hashed,
            created_at=now,
            expires_at=expires_at,
            metadata=metadata or {},
        )

        with self._lock:
            self._tokens[token_id] = record
            self._hash_to_id[hashed] = token_id

        return record, raw_secret

    def verify_and_consume(
        self,
        raw_token: str,
        action_name: str,
        target_resource: str,
        dry_run: bool = False,
    ) -> ApprovalTokenRecord:
        """Verify token authenticity, scope, expiration, and consume single-use token.

        If dry_run is True:
            Validates token without consuming it, allowing pre-flight impact simulation.
        If dry_run is False:
            Marks token consumed in a single atomic operation; subsequent attempts fail.
        """
        clean_token = raw_token.strip()
        if not clean_token:
            raise ApprovalRequiredError("Approval token cannot be empty")

        computed_hash = hashlib.sha256(clean_token.encode("utf-8")).hexdigest()

        with self._lock:
            # Timing-safe search across stored token hashes
            matched_id: str | None = None
            for stored_hash, tid in self._hash_to_id.items():
                if hmac.compare_digest(stored_hash, computed_hash):
                    matched_id = tid
                    break

            if not matched_id or matched_id not in self._tokens:
                raise ApprovalRequiredError("Invalid approval token")

            record = self._tokens[matched_id]

            if record.is_consumed:
                raise ApprovalRequiredError(
                    f"Approval token '{record.token_id}' has already been consumed at {record.consumed_at}"
                )

            if record.is_expired():
                raise ApprovalRequiredError(f"Approval token '{record.token_id}' expired at {record.expires_at}")

            if record.action_name != action_name or record.target_resource != target_resource:
                raise ApprovalRequiredError(
                    f"Approval token target mismatch (expected '{record.action_name}' on '{record.target_resource}', "
                    f"attempted '{action_name}' on '{target_resource}')"
                )

            if dry_run:
                record.dry_run_count += 1
                return record.model_copy()

            # Atomic consumption
            record.is_consumed = True
            record.consumed_at = datetime.now(UTC)
            return record.model_copy()

    def get_token(self, token_id: str) -> ApprovalTokenRecord | None:
        with self._lock:
            rec = self._tokens.get(token_id)
            return rec.model_copy() if rec else None
