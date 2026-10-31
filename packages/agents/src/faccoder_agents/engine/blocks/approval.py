from __future__ import annotations

from typing import Any

from faccoder_agents.engine.blocks.base import BaseBlock
from faccoder_agents.engine.models import (
    ApprovalRequest,
    ApprovalStatus,
    BlockResult,
    BlockStatus,
)


class HumanApprovalBlock(BaseBlock):
    """Gates execution behind human confirmation with dry-run support, state isolation, and block binding."""

    def __init__(
        self,
        name: str,
        action_name: str,
        description: str = "",
        ttl_seconds: float = 1800.0,  # 30 minutes default
        payload_keys: list[str] | None = None,
    ) -> None:
        super().__init__(name=name, block_type="human_approval")
        self.action_name = action_name
        self.description = description or f"Approval required for '{action_name}'"
        self.ttl_seconds = ttl_seconds
        self.payload_keys = payload_keys or []

    def _extract_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self.payload_keys:
            return data.copy()
        return {k: data[k] for k in self.payload_keys if k in data}

    def execute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        context = context or {}
        metadata = state.get("metadata", {})
        data = state.get("data", {})
        inputs = state.get("inputs", {})

        is_dry_run = bool(metadata.get("dry_run") or context.get("dry_run"))
        payload = self._extract_payload(data)

        # 1. Dry run handling: Generate preview and mark as DRY_RUN
        if is_dry_run:
            req, _ = ApprovalRequest.create(
                action_name=self.action_name,
                block_name=self.name,
                description=f"[DRY-RUN] {self.description}",
                payload=payload,
                status=ApprovalStatus.DRY_RUN,
            )
            state_dict = req.to_state_dict()
            return BlockResult(
                block_name=self.name,
                status=BlockStatus.DRY_RUN,
                approval_request=req,
                updates={
                    "approval": state_dict,
                    f"approval_{self.name}": state_dict,
                    "_dry_run_preview": payload,
                },
                message=f"Dry run passed for '{self.action_name}' without external side-effects",
            )

        # 2. Gate check: look for candidate token in inputs, data or context
        candidate_token = (
            inputs.get(f"approval_token_{self.name}")
            or inputs.get("approval_token")
            or data.get(f"approval_token_{self.name}")
            or data.get("approval_token")
            or context.get("approval_token")
        )

        existing_approval_dict = (
            state.get(f"approval_{self.name}") or state.get("approvals", {}).get(self.name) or state.get("approval")
        )

        existing_req: ApprovalRequest | None = None
        if existing_approval_dict:
            try:
                existing_req = ApprovalRequest.model_validate(existing_approval_dict)
            except Exception:
                existing_req = None

        if candidate_token:
            if existing_req is None:
                return BlockResult(
                    block_name=self.name,
                    status=BlockStatus.FAILURE,
                    error="Approval token provided, but no active approval request was found in state.",
                    message="Unexpected approval token",
                )

            # Block binding check: ensure token was generated specifically for this block
            if existing_req.block_name and existing_req.block_name != self.name:
                return BlockResult(
                    block_name=self.name,
                    status=BlockStatus.FAILURE,
                    error=(
                        f"Approval token is bound to block '{existing_req.block_name}' "
                        f"(action: '{existing_req.action_name}'), cannot approve block '{self.name}'."
                    ),
                    message="Block binding mismatch",
                )

            if existing_req.action_name != self.action_name:
                return BlockResult(
                    block_name=self.name,
                    status=BlockStatus.FAILURE,
                    error=(
                        f"Approval token is bound to action '{existing_req.action_name}', "
                        f"cannot approve action '{self.action_name}'."
                    ),
                    message="Action binding mismatch",
                )

            # Lifecycle check: Accept only requests with status PENDING, reject already used/consumed
            if existing_req.consumed or existing_req.status == ApprovalStatus.APPROVED:
                return BlockResult(
                    block_name=self.name,
                    status=BlockStatus.REJECTED,
                    approval_request=existing_req,
                    error=f"Approval token for '{self.action_name}' has already been consumed.",
                    message="Token already consumed",
                )

            if existing_req.status != ApprovalStatus.PENDING:
                return BlockResult(
                    block_name=self.name,
                    status=BlockStatus.REJECTED,
                    approval_request=existing_req,
                    error=(
                        f"Approval request for '{self.action_name}' is not in PENDING status "
                        f"(current: {existing_req.status.value})."
                    ),
                    message="Invalid lifecycle state",
                )

            if existing_req.is_expired():
                existing_req.status = ApprovalStatus.EXPIRED
                state_dict = existing_req.to_state_dict()
                return BlockResult(
                    block_name=self.name,
                    status=BlockStatus.REJECTED,
                    approval_request=existing_req,
                    error=f"Approval token for '{self.action_name}' has expired.",
                    message="Approval token expired",
                    updates={"approval": state_dict, f"approval_{self.name}": state_dict},
                )

            # Timing-safe token validation
            if not existing_req.matches_token(str(candidate_token)):
                return BlockResult(
                    block_name=self.name,
                    status=BlockStatus.FAILURE,
                    error="Provided approval token does not match active request token.",
                    message="Invalid approval token",
                )

            # Valid and approved: consume token and update lifecycle
            existing_req.status = ApprovalStatus.APPROVED
            existing_req.consumed = True
            state_dict = existing_req.to_state_dict()

            return BlockResult(
                block_name=self.name,
                status=BlockStatus.SUCCESS,
                approval_request=existing_req,
                message=f"Action '{self.action_name}' approved by human operator.",
                updates={"approval": state_dict, f"approval_{self.name}": state_dict},
            )

        # 3. No token provided: create a pending approval request and pause/wait
        req, raw_token = ApprovalRequest.create(
            action_name=self.action_name,
            block_name=self.name,
            description=self.description,
            payload=payload,
            ttl_seconds=self.ttl_seconds,
            status=ApprovalStatus.PENDING,
        )
        state_dict = req.to_state_dict()
        return BlockResult(
            block_name=self.name,
            status=BlockStatus.WAITING_APPROVAL,
            approval_request=req,
            updates={"approval": state_dict, f"approval_{self.name}": state_dict},
            message=f"Execution halted: waiting for approval token for '{self.action_name}'.",
        )
