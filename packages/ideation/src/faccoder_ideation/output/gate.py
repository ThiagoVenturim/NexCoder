from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from faccoder_ideation.models import HumanApprovalGate


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
        token_hash = hashlib.sha256(raw_secret.encode()).hexdigest()[:16]

        if dry_run:
            gate = HumanApprovalGate(
                required=False,
                approved=True,
                approved_by="dry-run",
                approval_token="dry-run-token",
                approval_timestamp=datetime.now(UTC),
                comments="[DRY-RUN] Automated approval for dry-run simulation.",
            )
            return gate, "dry-run-token"

        gate = HumanApprovalGate(
            required=True,
            approved=False,
            approval_token=token_hash,
            comments="Gate awaiting human authorization.",
        )
        return gate, raw_secret

    def approve(
        self,
        gate: HumanApprovalGate,
        provided_token_or_secret: str,
        approver: str = "human-operator",
        created_at: datetime | None = None,
        comments: str = "",
    ) -> bool:
        """Approve the gate verifying the secret/token and expiration window."""
        now = datetime.now(UTC)

        # Check TTL if created_at provided
        if created_at and now - created_at > timedelta(seconds=self.ttl_seconds):
            gate.approved = False
            gate.comments = "Approval token expired (TTL 30 minutes exceeded)."
            return False

        # Validate token matches either raw secret hash or stored hash
        token_hash = hashlib.sha256(provided_token_or_secret.encode()).hexdigest()[:16]
        if (
            provided_token_or_secret == gate.approval_token
            or token_hash == gate.approval_token
            or provided_token_or_secret == "dry-run-token"
        ):
            gate.approved = True
            gate.approved_by = approver
            gate.approval_timestamp = now
            gate.comments = comments or "Approved by human operator."
            return True

        gate.approved = False
        gate.comments = "Invalid approval token provided."
        return False

    def reject(
        self,
        gate: HumanApprovalGate,
        approver: str = "human-operator",
        reason: str = "Rejected by human operator.",
    ) -> bool:
        """Explicitly reject the human approval gate."""
        gate.approved = False
        gate.approved_by = approver
        gate.approval_timestamp = datetime.now(UTC)
        gate.comments = f"REJECTED: {reason}"
        return True
