"""Approval tokens for high-risk actions and CLI machine governance."""

from nexcoder_control.approval.machines import (
    CLIMachine,
    MachineApprovalManager,
    MachineStatus,
)
from nexcoder_control.approval.target_gate import (
    TargetAuthorizationGate,
    TargetAuthorizationRecord,
    TargetNotAuthorizedError,
    TargetOwnership,
    normalize_target,
    redact_secrets,
)
from nexcoder_control.approval.tokens import (
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
    "TargetAuthorizationGate",
    "TargetAuthorizationRecord",
    "TargetNotAuthorizedError",
    "TargetOwnership",
    "normalize_target",
    "redact_secrets",
]
