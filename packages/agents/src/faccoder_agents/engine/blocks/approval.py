from __future__ import annotations

import time
from typing import Any

from faccoder_agents.engine.blocks.base import BaseBlock
from faccoder_agents.engine.models import (
    ApprovalRequest,
    ApprovalStatus,
    BlockResult,
    BlockStatus,
)


class HumanApprovalBlock(BaseBlock):
    """Gates execution behind human confirmation with dry-run support and expiring approval tokens."""

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
            req = ApprovalRequest(
                action_name=self.action_name,
                description=f"[DRY-RUN] {self.description}",
                payload=payload,
                status=ApprovalStatus.DRY_RUN,
            )
            return BlockResult(
                block_name=self.name,
                status=BlockStatus.DRY_RUN,
                approval_request=req,
                updates={"approval": req.model_dump(), "_dry_run_preview": payload},
                message=f"Dry run passed for '{self.action_name}' without external side-effects",
            )

        # 2. Gate check: look for candidate token in inputs, data or context
        candidate_token = (
            inputs.get("approval_token")
            or data.get("approval_token")
            or context.get("approval_token")
        )

        existing_approval_dict = state.get("approval")
        if existing_approval_dict:
            existing_req = ApprovalRequest.model_validate(existing_approval_dict)
        else:
            existing_req = None

        if candidate_token:
            if existing_req is None:
                return BlockResult(
                    block_name=self.name,
                    status=BlockStatus.FAILURE,
                    error="Approval token provided, but no active approval request was found in state.",
                    message="Unexpected approval token",
                )

            if not existing_req.matches_token(str(candidate_token)):
                return BlockResult(
                    block_name=self.name,
                    status=BlockStatus.FAILURE,
                    error="Provided approval token does not match active request token.",
                    message="Invalid approval token",
                )

            if existing_req.is_expired():
                existing_req.status = ApprovalStatus.EXPIRED
                return BlockResult(
                    block_name=self.name,
                    status=BlockStatus.REJECTED,
                    approval_request=existing_req,
                    error=f"Approval token for '{self.action_name}' has expired.",
                    message="Approval token expired",
                    updates={"approval": existing_req.model_dump()},
                )

            # Token matches and is active!
            existing_req.status = ApprovalStatus.APPROVED
            return BlockResult(
                block_name=self.name,
                status=BlockStatus.SUCCESS,
                approval_request=existing_req,
                message=f"Action '{self.action_name}' approved by human operator.",
                updates={"approval": existing_req.model_dump()},
            )

        # 3. No token provided: create a pending approval request and pause/wait
        req = ApprovalRequest(
            action_name=self.action_name,
            description=self.description,
            payload=payload,
            created_at=time.time(),
            expires_at=time.time() + self.ttl_seconds,
            status=ApprovalStatus.PENDING,
        )
        return BlockResult(
            block_name=self.name,
            status=BlockStatus.WAITING_APPROVAL,
            approval_request=req,
            updates={"approval": req.model_dump()},
            message=f"Execution halted: waiting for approval token for '{self.action_name}'.",
        )
