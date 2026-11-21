"""Approval tokens for high-risk actions, signed documents, and CLI machine governance."""

from nexcoder_control.approval.machines import (
    CLIMachine,
    MachineApprovalManager,
    MachineStatus,
)
from nexcoder_control.approval.signed_doc import (
    AuthorizationDocument,
    compute_scope_hash,
    create_canonical_payload,
    generate_keypair,
    is_local_or_owned_target,
    load_authorization_document,
    sign_authorization_document,
    verify_signed_document,
)
from nexcoder_control.approval.target_gate import (
    AuthorizationGateBlockedError,
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
    "AuthorizationDocument",
    "AuthorizationGateBlockedError",
    "CLIMachine",
    "MachineApprovalManager",
    "MachineStatus",
    "TargetAuthorizationGate",
    "TargetAuthorizationRecord",
    "TargetNotAuthorizedError",
    "TargetOwnership",
    "compute_scope_hash",
    "create_canonical_payload",
    "generate_keypair",
    "is_local_or_owned_target",
    "load_authorization_document",
    "normalize_target",
    "redact_secrets",
    "sign_authorization_document",
    "verify_signed_document",
]
