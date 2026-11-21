"""Offline integration tests for SecurityTestCampaignEngine, target gate, and budgets (Issue #71)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from nexcoder_control.approval import (
    TargetAuthorizationGate,
    TargetNotAuthorizedError,
    generate_keypair,
    sign_authorization_document,
)
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_security.campaign import (
    CampaignBudget,
    CampaignConfig,
    CampaignRegistry,
    CampaignStatus,
    SecurityTestCampaignEngine,
    TestType,
)
from nexcoder_security.cli import main as cli_main


@pytest.fixture
def keypair() -> tuple[str, str]:
    return generate_keypair()


@pytest.fixture
def signed_auth_file(tmp_path: Path, keypair: tuple[str, str]) -> Path:
    priv, pub = keypair
    now = datetime.now(UTC)
    doc_data = {
        "target": "https://api.internal.local",
        "scope": ["security_test_campaign", "security_scan"],
        "authorized_by": "SecOps Director (Diana)",
        "contact": "secops@internal.local",
        "valid_from": (now - timedelta(hours=1)).isoformat(),
        "valid_until": (now + timedelta(hours=12)).isoformat(),
        "public_key": pub,
    }
    signed = sign_authorization_document(doc_data, private_key=priv, public_key=pub)
    f = tmp_path / "valid_auth.yaml"
    signed.save(f)
    return f


class TestCampaignEngine:
    def test_campaign_fails_closed_when_target_unauthorized(self) -> None:
        audit = AppendOnlyAuditLog()
        gate = TargetAuthorizationGate(audit_log=audit)
        engine = SecurityTestCampaignEngine(audit_log=audit, target_gate=gate)

        config = CampaignConfig(
            target="https://external-target.com",
            test_types=[TestType.API, TestType.SECURITY],
            owned_target=False,
            authorized_by="",
        )

        with pytest.raises(TargetNotAuthorizedError):
            engine.run_campaign(config, raise_on_auth_failure=True)

        denials = audit.query(event_type="target.authorization.denied")
        assert len(denials) == 1

        # Also test non-raising mode returns rejected report
        rejected_report = engine.run_campaign(config, raise_on_auth_failure=False)
        assert rejected_report.status == CampaignStatus.REJECTED

    def test_campaign_runs_with_owned_target(self, tmp_path: Path) -> None:
        # Create minimal repo structure
        app_file = tmp_path / "app.py"
        app_file.write_text("def hello() -> str:\n    return 'world'\n", encoding="utf-8")

        audit = AppendOnlyAuditLog()
        registry = CampaignRegistry()
        engine = SecurityTestCampaignEngine(audit_log=audit, registry=registry)

        config = CampaignConfig(
            target=str(tmp_path),
            test_types=[TestType.UNIT, TestType.SYSTEM],
            agent_count=2,
            owned_target=True,
            authorized_by="Lead Dev (Alice)",
        )

        report = engine.run_campaign(config)

        assert report.status == CampaignStatus.COMPLETED
        assert report.authorized_by == "Lead Dev (Alice)"
        assert report.total_tests_run >= 2
        assert report.agent_count == 2
        assert len(report.agent_results) == 2

        # Verify audit entries
        starts = audit.query(event_type="test_campaign.started")
        assert len(starts) == 1
        assert starts[0].actor == "Lead Dev (Alice)"

        completes = audit.query(event_type="test_campaign.completed")
        assert len(completes) == 1
        assert completes[0].details["status"] == "completed"

        # Verify registry entry
        stored = registry.get(report.campaign_id)
        assert stored is not None
        assert stored.campaign_id == report.campaign_id

    def test_campaign_runs_with_ed25519_signed_document(
        self, signed_auth_file: Path, keypair: tuple[str, str]
    ) -> None:
        _priv, pub = keypair
        audit = AppendOnlyAuditLog()
        engine = SecurityTestCampaignEngine(
            audit_log=audit,
            trusted_public_keys=[pub],
        )

        config = CampaignConfig(
            target="https://api.internal.local",
            test_types=[TestType.API, TestType.SECURITY],
            agent_count=2,
            authorization_document=signed_auth_file,
            require_signed_document=True,
        )

        report = engine.run_campaign(config)
        assert report.status == CampaignStatus.COMPLETED
        assert report.authorized_by == "SecOps Director (Diana)"
        assert report.ownership == "authorized"

        # Verify audit entry for cryptographic grant
        grants = audit.query(event_type="target.authorization.granted")
        assert len(grants) == 1
        assert grants[0].actor == "SecOps Director (Diana)"

    def test_campaign_rejects_expired_signed_document(
        self, tmp_path: Path, keypair: tuple[str, str]
    ) -> None:
        priv, pub = keypair
        now = datetime.now(UTC)
        doc_data = {
            "target": "https://api.internal.local",
            "scope": ["security_test_campaign"],
            "authorized_by": "Expired Lead",
            "contact": "expired@internal.local",
            "valid_from": (now - timedelta(days=5)).isoformat(),
            "valid_until": (now - timedelta(days=1)).isoformat(),
            "public_key": pub,
        }
        signed = sign_authorization_document(doc_data, private_key=priv, public_key=pub)
        exp_file = tmp_path / "expired_auth.yaml"
        signed.save(exp_file)

        audit = AppendOnlyAuditLog()
        engine = SecurityTestCampaignEngine(audit_log=audit, trusted_public_keys=[pub])
        config = CampaignConfig(
            target="https://api.internal.local",
            authorization_document=exp_file,
            require_signed_document=True,
        )

        with pytest.raises(TargetNotAuthorizedError, match="expired"):
            engine.run_campaign(config)

    def test_campaign_budget_cost_limit_enforcement(self, tmp_path: Path) -> None:
        audit = AppendOnlyAuditLog()
        engine = SecurityTestCampaignEngine(audit_log=audit)

        # Budget of practically zero USD ($0.0001)
        budget = CampaignBudget(max_cost_usd=0.0001, max_duration_seconds=60.0)
        config = CampaignConfig(
            target=str(tmp_path),
            test_types=[TestType.UNIT, TestType.API, TestType.SECURITY],
            budget=budget,
            owned_target=True,
            authorized_by="Budget Manager",
        )

        report = engine.run_campaign(config)
        assert report.status == CampaignStatus.BUDGET_EXCEEDED

        budget_events = audit.query(event_type="test_campaign.budget_exceeded")
        assert len(budget_events) >= 1

    def test_cli_campaign_command(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        target_dir = tmp_path / "test_repo"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "test_file.py").write_text("def ping() -> str: return 'pong'\n", encoding="utf-8")

        # 1. Rejected when unauthorized
        ret_fail = cli_main(
            ["campaign", str(target_dir), "--authorized-by", "nobody"]
        )
        assert ret_fail == 1

        # 2. Succeeded with owned-target
        report_out = tmp_path / "cli_report.md"
        ret_ok = cli_main(
            [
                "campaign",
                str(target_dir),
                "--owned-target",
                "--authorized-by",
                "Alice",
                "--markdown",
                "--output",
                str(report_out),
            ]
        )
        assert ret_ok == 0
        assert report_out.exists()
        content = report_out.read_text(encoding="utf-8")
        assert "Security and Quality Test Campaign Report" in content
        assert "Alice" in content
