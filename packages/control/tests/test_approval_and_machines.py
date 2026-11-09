"""Tests for human approval tokens with dry-run support and CLI machine governance."""

from __future__ import annotations

import pytest
from nexcoder_control.approval.machines import MachineApprovalManager
from nexcoder_control.approval.tokens import ApprovalRequiredError, ApprovalTokenManager
from nexcoder_control.auth.base import ForbiddenError


class TestApprovalTokens:
    def test_issue_and_consume_token(self, approval_manager: ApprovalTokenManager) -> None:
        record, raw_token = approval_manager.issue_token(
            action_name="git_force_push",
            target_resource="repo:nexcoder/main",
            approver="lead_engineer",
            ttl_minutes=15,
        )
        assert raw_token.startswith("fc_apr_")
        assert not record.is_consumed

        # Consume token
        consumed = approval_manager.verify_and_consume(
            raw_token=raw_token,
            action_name="git_force_push",
            target_resource="repo:nexcoder/main",
            dry_run=False,
        )
        assert consumed.is_consumed
        assert consumed.consumed_at is not None

        # Re-consuming the single-use token fails closed (HTTP 403)
        with pytest.raises(ApprovalRequiredError, match="already been consumed"):
            approval_manager.verify_and_consume(
                raw_token=raw_token,
                action_name="git_force_push",
                target_resource="repo:nexcoder/main",
                dry_run=False,
            )

    def test_dry_run_simulation_preserves_token(self, approval_manager: ApprovalTokenManager) -> None:
        record, raw_token = approval_manager.issue_token(
            action_name="db_migration",
            target_resource="db:production",
            approver="dba_lead",
            ttl_minutes=15,
        )

        # Dry run does not consume the single-use token
        preview1 = approval_manager.verify_and_consume(
            raw_token=raw_token,
            action_name="db_migration",
            target_resource="db:production",
            dry_run=True,
        )
        assert not preview1.is_consumed
        assert preview1.dry_run_count == 1

        preview2 = approval_manager.verify_and_consume(
            raw_token=raw_token,
            action_name="db_migration",
            target_resource="db:production",
            dry_run=True,
        )
        assert not preview2.is_consumed
        assert preview2.dry_run_count == 2

        # Final execution consumes it
        final = approval_manager.verify_and_consume(
            raw_token=raw_token,
            action_name="db_migration",
            target_resource="db:production",
            dry_run=False,
        )
        assert final.is_consumed

    def test_action_or_target_mismatch(self, approval_manager: ApprovalTokenManager) -> None:
        _, raw_token = approval_manager.issue_token(
            action_name="delete_index",
            target_resource="index:prod",
            approver="admin",
        )

        with pytest.raises(ApprovalRequiredError, match="target mismatch"):
            approval_manager.verify_and_consume(
                raw_token=raw_token,
                action_name="delete_index",
                target_resource="index:staging",  # Different target
            )


class TestCLIMachineApproval:
    def test_registration_and_approval_flow(self, machine_manager: MachineApprovalManager) -> None:
        # 1. Register machine -> status "pending"
        machine = machine_manager.register_machine(
            machine_id="workstation_99",
            hostname="devbox-01",
            platform="linux",
            client_version="0.1.0",
            registered_by="alice",
        )
        assert machine.status == "pending"

        # 2. Verification fails closed while pending
        with pytest.raises(ForbiddenError, match="is not approved"):
            machine_manager.verify_machine("workstation_99")

        # 3. Admin approves
        approved = machine_manager.approve_machine("workstation_99", approver="admin")
        assert approved.status == "approved"

        # 4. Verification succeeds once approved
        verified = machine_manager.verify_machine("workstation_99")
        assert verified.is_approved

    def test_revoke_machine(self, machine_manager: MachineApprovalManager) -> None:
        machine_manager.register_machine("box_2", "laptop-02")
        machine_manager.approve_machine("box_2", approver="admin")

        revoked = machine_manager.revoke_machine("box_2", approver="security_team")
        assert revoked.status == "revoked"

        with pytest.raises(ForbiddenError, match="is not approved"):
            machine_manager.verify_machine("box_2")
