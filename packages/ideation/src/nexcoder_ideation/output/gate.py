from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime

from faccoder_ideation.models import GateStatus, HumanApprovalGate


class HumanGateManager:
    """Manager for b85 human approval tokens and authorization before planning layer handoff."""

    def __init__(self, ttl_seconds: float = 1800.0) -> None:
        self.ttl_seconds = ttl_seconds

    def create_gate(
        self,
        idea_id: str,
        dry_run: bool = False,
    ) -> tuple[HumanApprovalGate, str]:
        """Generate a new human approval gate with an ephemeral cryptographic token."""
        raw_secret = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
        now = time.time()

        if dry_run:
            gate = HumanApprovalGate(
                required=False,
                status=GateStatus.APPROVED,
                token_hash=token_hash,
                created_at=now,
                expires_at=now + self.ttl_seconds,
                consumed=True,
                approved=True,
                approved_by="dry-run",
                approval_timestamp=datetime.now(UTC),
                comments="[DRY-RUN] Automated approval for dry-run simulation.",
            )
            return gate, raw_secret

        gate = HumanApprovalGate(
            required=True,
            status=GateStatus.PENDING,
            token_hash=token_hash,
            created_at=now,
            expires_at=now + self.ttl_seconds,
            consumed=False,
            approved=False,
            comments="Gate awaiting human authorization.",
        )
        return gate, raw_secret

    def approve(
        self,
        gate: HumanApprovalGate,
        provided_token: str,
        approver: str = "human-operator",
        comments: str = "",
        current_time: float | None = None,
    ) -> bool:
        """Approve the gate verifying the secret/token and expiration window."""
        now_ts = current_time if current_time is not None else time.time()
        now_dt = datetime.now(UTC)

        # 1. Reject empty or insecure placeholder tokens
        if not provided_token or provided_token.strip() == "dry-run-token":
            gate.approved = False
            gate.comments = "Invalid approval token provided."
            return False

        # 2. Strict lifecycle check: status MUST be PENDING and NOT consumed
        if gate.consumed or gate.status != GateStatus.PENDING:
            gate.approved = False
            gate.comments = "Approval token has already been consumed or is not pending."
            return False

        # 3. Check expiration timestamp
        if now_ts > gate.expires_at:
            gate.status = GateStatus.EXPIRED
            gate.consumed = True
            gate.approved = False
            gate.comments = "Approval token expired (TTL exceeded)."
            return False

        candidate = str(provided_token).strip()

        # 4. Strictly reject if the user passes the token_hash itself (must provide raw token)
        if hmac.compare_digest(candidate, gate.token_hash):
            gate.approved = False
            gate.comments = "Provided token cannot be the stored hash."
            return False

        # 5. Timing-safe validation via full SHA-256 hash and hmac.compare_digest
        candidate_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(gate.token_hash, candidate_hash):
            gate.approved = False
            gate.comments = "Invalid approval token provided."
            return False

        # 6. Successfully approve and mark consumed strictly for single use
        gate.consumed = True
        gate.status = GateStatus.APPROVED
        gate.approved = True
        gate.approved_by = approver
        gate.approval_timestamp = now_dt
        gate.comments = comments or "Approved by human operator."
        return True

    def reject(
        self,
        gate: HumanApprovalGate,
        approver: str = "human-operator",
        reason: str = "Rejected by human operator.",
    ) -> bool:
        """Explicitly reject the human approval gate."""
        gate.consumed = True
        gate.status = GateStatus.REJECTED
        gate.approved = False
        gate.approved_by = approver
        gate.approval_timestamp = datetime.now(UTC)
        gate.comments = f"REJECTED: {reason}"
        return True
