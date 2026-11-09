"""Approval tokens for high-risk actions and CLI machine governance."""

from faccoder_control.approval.machines import (
    CLIMachine,
    MachineApprovalManager,
    MachineStatus,
)
from faccoder_control.approval.tokens import (
    ApprovalRequiredError,
    ApprovalTokenManager,
    ApprovalTokenRecord,
)

__all__ = [
    "ApprovalRequiredError",
    "ApprovalTokenManager",
    "ApprovalTokenRecord",
    "CLIMachine",
    "MachineApprovalManager",
    "MachineStatus",
]
