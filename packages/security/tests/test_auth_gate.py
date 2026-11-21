"""Offline tests for gate_active_scan, MultiScannerEngine auth-gate integration, and CI enforcement."""

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
from nexcoder_security.cli import main as cli_main
from nexcoder_security.gate import gate_active_scan
from nexcoder_security.scanners.engine import MultiScannerEngine

from scripts.check_auth_gate_enforcement import check_file
from scripts.check_auth_gate_enforcement import main as enforcement_main


@pytest.fixture
def keypair() -> tuple[str, str]:
    return generate_keypair()


@pytest.fixture
def signed_doc_file(tmp_path: Path, keypair: tuple[str, str]) -> Path:
    priv, pub = keypair
    now = datetime.now(UTC)
    doc_data = {
        "target": "https://api.example.com",
        "scope": ["security_scan", "active_scan", "sbom"],
        "authorized_by": "SecOps Lead (Bob)",
        "contact": "secops@example.com",
        "valid_from": (now - timedelta(hours=1)).isoformat(),
        "valid_until": (now + timedelta(hours=12)).isoformat(),
        "public_key": pub,
    }
    signed = sign_authorization_document(doc_data, private_key=priv, public_key=pub)
    file_path = tmp_path / "valid_auth.yaml"
    signed.save(file_path)
    return file_path


class TestActiveScanGate:
    def test_gate_active_scan_accepts_valid_doc(
        self, signed_doc_file: Path, keypair: tuple[str, str]
    ) -> None:
        _priv, pub = keypair
        audit = AppendOnlyAuditLog()
        rec = gate_active_scan(
            target="https://api.example.com",
            action="security_scan",
            authorization_document=signed_doc_file,
            audit_log=audit,
            trusted_public_keys=[pub],
        )
        assert rec.authorized_by == "SecOps Lead (Bob)"
        assert rec.ownership == "authorized"

        granted = audit.query(event_type="target.authorization.granted")
        assert len(granted) == 1
        assert granted[0].actor == "SecOps Lead (Bob)"

    def test_gate_active_scan_denies_without_doc_for_external_target(self) -> None:
        audit = AppendOnlyAuditLog()
        with pytest.raises(TargetNotAuthorizedError, match="requires a valid signed authorization document"):
            gate_active_scan(
                target="https://unauthorized-target.example.com",
                action="security_scan",
                audit_log=audit,
            )

        denied = audit.query(event_type="target.authorization.denied")
        assert len(denied) == 1
        assert denied[0].details["status"] == "denied"

    def test_gate_active_scan_denies_expired_doc(self, keypair: tuple[str, str]) -> None:
        priv, pub = keypair
        now = datetime.now(UTC)
        doc_data = {
            "target": "https://api.example.com",
            "scope": ["security_scan"],
            "authorized_by": "SecOps",
            "contact": "sec@example.com",
            "valid_from": (now - timedelta(days=5)).isoformat(),
            "valid_until": (now - timedelta(days=1)).isoformat(),
            "public_key": pub,
        }
        signed = sign_authorization_document(doc_data, private_key=priv, public_key=pub)

        with pytest.raises(TargetNotAuthorizedError, match="expired"):
            gate_active_scan(
                target="https://api.example.com",
                action="security_scan",
                authorization_document=signed,
                trusted_public_keys=[pub],
            )

    def test_gate_active_scan_denies_wrong_target(
        self, signed_doc_file: Path, keypair: tuple[str, str]
    ) -> None:
        _priv, pub = keypair
        with pytest.raises(TargetNotAuthorizedError, match="Target mismatch"):
            gate_active_scan(
                target="https://different.example.com",
                action="security_scan",
                authorization_document=signed_doc_file,
                trusted_public_keys=[pub],
            )

    def test_gate_active_scan_denies_invalid_signature(
        self, keypair: tuple[str, str], signed_doc_file: Path
    ) -> None:
        _priv, pub = keypair
        _other_priv, other_pub = generate_keypair()
        with pytest.raises(TargetNotAuthorizedError, match="not present in the trusted public keys"):
            gate_active_scan(
                target="https://api.example.com",
                action="security_scan",
                authorization_document=signed_doc_file,
                trusted_public_keys=[other_pub],
            )

    def test_gate_active_scan_denies_insufficient_scope(
        self, keypair: tuple[str, str]
    ) -> None:
        priv, pub = keypair
        now = datetime.now(UTC)
        doc_data = {
            "target": "https://api.example.com",
            "scope": ["read_only_scan"],
            "authorized_by": "SecOps",
            "contact": "sec@example.com",
            "valid_from": (now - timedelta(hours=1)).isoformat(),
            "valid_until": (now + timedelta(hours=2)).isoformat(),
            "public_key": pub,
        }
        signed = sign_authorization_document(doc_data, private_key=priv, public_key=pub)

        with pytest.raises(TargetNotAuthorizedError, match="not permitted by authorization document scope"):
            gate_active_scan(
                target="https://api.example.com",
                action="security_scan",
                authorization_document=signed,
                trusted_public_keys=[pub],
            )

    def test_multiscanner_engine_scan_with_signed_doc(
        self, tmp_path: Path, signed_doc_file: Path, keypair: tuple[str, str]
    ) -> None:
        _priv, pub = keypair
        gate = TargetAuthorizationGate(trusted_public_keys=[pub])
        engine = MultiScannerEngine(target_gate=gate)

        # Scanning local directory using signed document
        # First create a valid doc for tmp_path
        priv, pub = keypair
        now = datetime.now(UTC)
        doc_data = {
            "target": str(tmp_path),
            "scope": ["security_scan"],
            "authorized_by": "Director",
            "contact": "sec@example.com",
            "valid_from": (now - timedelta(hours=1)).isoformat(),
            "valid_until": (now + timedelta(hours=5)).isoformat(),
            "public_key": pub,
        }
        signed = sign_authorization_document(doc_data, private_key=priv, public_key=pub)

        res = engine.scan(
            tmp_path,
            enabled_scanners=["bandit"],
            force_offline=True,
            authorization_document=signed,
        )
        assert res.scanner == "multi-scanner-engine"
        assert res.metadata is not None

    def test_multiscanner_engine_scan_denies_when_doc_required(self, tmp_path: Path) -> None:
        engine = MultiScannerEngine()
        with pytest.raises(TargetNotAuthorizedError, match="requires a valid signed authorization document"):
            engine.scan(
                tmp_path,
                enabled_scanners=["bandit"],
                force_offline=True,
                require_signed_document=True,
            )

    def test_hook_and_ci_blocks_prohibited_calls_outside_gate(self, tmp_path: Path) -> None:
        # Create a mock source file outside the gate module that attempts direct socket / prohibited scan
        bad_code = (
            "import socket\n"
            "def exploit():\n"
            "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    s.connect(('10.0.0.1', 80))\n"
        )
        bad_file = tmp_path / "rogue_scanner.py"
        bad_file.write_text(bad_code, encoding="utf-8")

        violations = check_file(bad_file)
        assert len(violations) >= 1
        assert any("Direct raw socket call" in v[1] for v in violations)

        # Check that main returns exit code 1 on violations
        ret = enforcement_main([str(bad_file)])
        assert ret == 1

        # Check clean file passes
        clean_code = "def safe_helper():\n    return 42\n"
        clean_file = tmp_path / "clean_code.py"
        clean_file.write_text(clean_code, encoding="utf-8")
        assert len(check_file(clean_file)) == 0
        assert enforcement_main([str(clean_file)]) == 0

    def test_cli_scan_with_auth_doc(
        self, tmp_path: Path, keypair: tuple[str, str], monkeypatch
    ) -> None:
        priv, pub = keypair
        now = datetime.now(UTC)
        doc_data = {
            "target": str(tmp_path),
            "scope": ["security_scan"],
            "authorized_by": "Compliance Lead",
            "contact": "compliance@example.com",
            "valid_from": (now - timedelta(hours=1)).isoformat(),
            "valid_until": (now + timedelta(hours=5)).isoformat(),
            "public_key": pub,
        }
        signed = sign_authorization_document(doc_data, private_key=priv, public_key=pub)
        doc_file = tmp_path / "auth_token.json"
        signed.save(doc_file)

        gate = TargetAuthorizationGate(trusted_public_keys=[pub])
        audit = AppendOnlyAuditLog()

        code = cli_main(
            ["scan", str(tmp_path), "--offline", "--auth-doc", str(doc_file), "--scanners", "bandit"],
            audit_log=audit,
            target_gate=gate,
        )
        assert code == 0
