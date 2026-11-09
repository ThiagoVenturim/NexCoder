"""CLI machine and device approval management (fail-closed access governance)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from nexcoder_control.auth.base import ForbiddenError

MachineStatus = Literal["pending", "approved", "rejected", "revoked"]


class CLIMachine(BaseModel):
    """Registered CLI workstation or runner identity."""

    machine_id: str
    hostname: str
    platform: str = "unknown"
    client_version: str = "0.1.0"
    registered_by: str = "anonymous"
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: MachineStatus = "pending"
    approved_by: str | None = None
    approved_at: datetime | None = None
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_approved(self) -> bool:
        return self.status == "approved"


class MachineApprovalManager:
    """Manages CLI machine registration, admin approval, and fail-closed authorization."""

    def __init__(self) -> None:
        self._machines: dict[str, CLIMachine] = {}
        self._lock = threading.Lock()

    def register_machine(
        self,
        machine_id: str,
        hostname: str,
        platform: str = "unknown",
        client_version: str = "0.1.0",
        registered_by: str = "anonymous",
        metadata: dict[str, Any] | None = None,
    ) -> CLIMachine:
        """Register a new CLI workstation in 'pending' status."""
        clean_id = machine_id.strip()
        if not clean_id:
            raise ValueError("machine_id cannot be empty")

        now = datetime.now(UTC)
        with self._lock:
            existing = self._machines.get(clean_id)
            if existing:
                existing.hostname = hostname
                existing.platform = platform
                existing.client_version = client_version
                existing.last_seen_at = now
                return existing.model_copy()

            machine = CLIMachine(
                machine_id=clean_id,
                hostname=hostname,
                platform=platform,
                client_version=client_version,
                registered_by=registered_by,
                registered_at=now,
                status="pending",
                last_seen_at=now,
                metadata=metadata or {},
            )
            self._machines[clean_id] = machine
            return machine.model_copy()

    def approve_machine(self, machine_id: str, approver: str) -> CLIMachine:
        """Approve a CLI machine for execution access."""
        with self._lock:
            m = self._machines.get(machine_id)
            if not m:
                raise KeyError(f"Machine '{machine_id}' not found")
            m.status = "approved"
            m.approved_by = approver
            m.approved_at = datetime.now(UTC)
            return m.model_copy()

    def reject_machine(self, machine_id: str, approver: str) -> CLIMachine:
        """Reject a CLI machine registration."""
        with self._lock:
            m = self._machines.get(machine_id)
            if not m:
                raise KeyError(f"Machine '{machine_id}' not found")
            m.status = "rejected"
            m.approved_by = approver
            m.approved_at = datetime.now(UTC)
            return m.model_copy()

    def revoke_machine(self, machine_id: str, approver: str) -> CLIMachine:
        """Revoke a previously approved CLI machine."""
        with self._lock:
            m = self._machines.get(machine_id)
            if not m:
                raise KeyError(f"Machine '{machine_id}' not found")
            m.status = "revoked"
            m.approved_by = approver
            m.approved_at = datetime.now(UTC)
            return m.model_copy()

    def verify_machine(self, machine_id: str) -> CLIMachine:
        """Verify machine approval status; fails closed if not approved."""
        with self._lock:
            m = self._machines.get(machine_id)
            if not m:
                raise ForbiddenError(f"CLI machine '{machine_id}' is not registered")
            if m.status != "approved":
                raise ForbiddenError(f"CLI machine '{machine_id}' is not approved (current status: '{m.status}')")
            m.last_seen_at = datetime.now(UTC)
            return m.model_copy()

    def get_machine(self, machine_id: str) -> CLIMachine | None:
        with self._lock:
            m = self._machines.get(machine_id)
            return m.model_copy() if m else None

    def list_machines(self, status: MachineStatus | None = None) -> list[CLIMachine]:
        with self._lock:
            if status is None:
                return [m.model_copy() for m in self._machines.values()]
            return [m.model_copy() for m in self._machines.values() if m.status == status]
