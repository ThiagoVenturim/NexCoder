"""Tests for human approval tokens with dry-run support and CLI machine governance."""

from __future__ import annotations

import pytest
from nexcoder_control.approval.machines import MachineApprovalManager
from nexcoder_control.approval.target_gate import (
    TargetAuthorizationGate,
    TargetNotAuthorizedError,
    normalize_target,
)
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


class TestTargetAuthorizationGate:
    def test_refuses_unmarked_target_and_logs_audit(self, tmp_path) -> None:
        gate = TargetAuthorizationGate()
        target = tmp_path / "unmarked_repo"
        target.mkdir()

        with pytest.raises(TargetNotAuthorizedError, match="USAGE_POLICY.md"):
            gate.verify_target(target, mode="security_scan", owned_target=False, authorized_by="bob")

        denied_events = gate.audit_log.query(event_type="target.authorization.denied")
        assert len(denied_events) == 1
        evt = denied_events[0]
        assert evt.actor == "bob"
        assert evt.action == "security_scan"
        assert evt.resource == normalize_target(target)
        assert evt.details["status"] == "denied"
        assert evt.details["owned_target"] is False

        valid, _msg = gate.audit_log.verify_integrity()
        assert valid is True

    def test_passes_marked_target_and_logs_authorizer_when_and_target(self, tmp_path) -> None:
        gate = TargetAuthorizationGate()
        target = tmp_path / "owned_repo"
        target.mkdir()

        rec = gate.verify_target(
            target,
            mode="security_scan",
            owned_target=True,
            authorized_by="alice",
        )
        assert rec.authorized_by == "alice"
        assert rec.ownership == "owned"
        assert rec.target == normalize_target(target)
        assert rec.authorized_at is not None

        granted_events = gate.audit_log.query(event_type="target.authorization.granted")
        assert len(granted_events) == 1
        evt = granted_events[0]
        assert evt.actor == "alice"
        assert evt.action == "security_scan"
        assert evt.resource == normalize_target(target)
        assert evt.details["authorized_by"] == "alice"
        assert evt.details["target"] == normalize_target(target)
        assert "authorized_at" in evt.details

    def test_pre_registered_owned_target_and_revocation(self, tmp_path) -> None:
        gate = TargetAuthorizationGate()
        target = "https://staging.example.com"

        gate.mark_owned_target(target, authorized_by="platform-team")
        assert gate.is_target_authorized(target) is True

        rec = gate.verify_target(target, mode="web_capture")
        assert rec.authorized_by == "platform-team"

        gate.revoke_target(target, revoked_by="security-officer")
        assert gate.is_target_authorized(target) is False

        with pytest.raises(TargetNotAuthorizedError):
            gate.verify_target(target, mode="web_capture")

    def test_approval_token_authorizes_once_and_never_logs_secret(self, tmp_path) -> None:
        gate = TargetAuthorizationGate()
        target = tmp_path / "partner_repo"
        target.mkdir()
        norm = normalize_target(target)

        _tok_rec, raw_secret = gate.token_manager.issue_token(
            action_name="security_scan",
            target_resource=norm,
            approver="ciso",
        )

        rec = gate.verify_target(target, mode="security_scan", approval_token=raw_secret)
        assert rec.authorized_by == "ciso"
        assert rec.ownership == "authorized"

        # Single-use token cannot be reused
        with pytest.raises(TargetNotAuthorizedError):
            gate.verify_target(target, mode="security_scan", approval_token=raw_secret)

        # Ensure raw token secret never appears in any audit event
        for evt in gate.audit_log.query(limit=50):
            serialized = evt.model_dump_json()
            assert raw_secret not in serialized

    def test_no_secrets_in_audit_log_on_grant_or_denial(self, tmp_path) -> None:
        gate = TargetAuthorizationGate()
        target = "https://admin:SuperSecretPass99!@internal.example.com/app"
        sensitive_meta = {
            "api_key": "sk-proj-supersecretapikey123456789",
            "password": "PlaintextPassword123!",
            "nested": {
                "auth_header": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secretpayload",
                "aws": "AKIA1234567890ABCDEF",
                "note": "token=inline_secret_value_987654",
            },
        }

        with pytest.raises(TargetNotAuthorizedError):
            gate.verify_target(
                target,
                mode="security_scan",
                owned_target=False,
                metadata=sensitive_meta,
            )

        gate.verify_target(
            target,
            mode="security_scan",
            owned_target=True,
            authorized_by="sec-ops",
            metadata=sensitive_meta,
        )

        events = gate.audit_log.query(limit=20)
        assert len(events) == 2
        for evt in events:
            dump = evt.model_dump_json()
            assert "SuperSecretPass99!" not in dump
            assert "sk-proj-supersecretapikey123456789" not in dump
            assert "PlaintextPassword123!" not in dump
            assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secretpayload" not in dump
            assert "AKIA1234567890ABCDEF" not in dump
            assert "inline_secret_value_987654" not in dump
            assert "[REDACTED]" in dump
