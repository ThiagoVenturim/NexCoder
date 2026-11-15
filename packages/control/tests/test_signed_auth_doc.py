"""Offline tests for signed authorization documents and gate validation (Issue #106)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from nexcoder_control.approval import (
    TargetAuthorizationGate,
    TargetNotAuthorizedError,
    compute_scope_hash,
    create_canonical_payload,
    generate_keypair,
    is_local_or_owned_target,
    load_authorization_document,
    sign_authorization_document,
    verify_signed_document,
)


@pytest.fixture
def keypair() -> tuple[str, str]:
    return generate_keypair()


@pytest.fixture
def valid_doc_data(keypair: tuple[str, str]) -> dict:
    _priv, pub = keypair
    now = datetime.now(UTC)
    return {
        "target": "https://api.example.com",
        "scope": ["security_scan", "web_capture"],
        "authorized_by": "Security Team (Lead: Alice)",
        "contact": "security@example.com",
        "valid_from": (now - timedelta(hours=1)).isoformat(),
        "valid_until": (now + timedelta(hours=24)).isoformat(),
        "public_key": pub,
    }


class TestSignedAuthorizationDocument:
    def test_generate_keypair(self) -> None:
        priv, pub = generate_keypair()
        assert isinstance(priv, str) and len(priv) > 20
        assert isinstance(pub, str) and len(pub) > 20

    def test_sign_and_verify_valid_document(self, keypair: tuple[str, str], valid_doc_data: dict) -> None:
        priv, pub = keypair
        signed = sign_authorization_document(valid_doc_data, private_key=priv, public_key=pub)
        assert signed.signature != ""
        assert signed.scope_hash == compute_scope_hash(["security_scan", "web_capture"])

        verified = verify_signed_document(
            signed,
            trusted_public_keys=[pub],
            target="https://api.example.com",
            action="security_scan",
        )
        assert verified.target == "https://api.example.com"
        assert verified.authorized_by == "Security Team (Lead: Alice)"

    def test_yaml_and_json_serialization_and_loading(
        self, tmp_path: Path, keypair: tuple[str, str], valid_doc_data: dict
    ) -> None:
        priv, pub = keypair
        signed = sign_authorization_document(valid_doc_data, private_key=priv, public_key=pub)

        # YAML save and load
        yaml_path = tmp_path / "auth_doc.yaml"
        signed.save(yaml_path)
        loaded_yaml = load_authorization_document(yaml_path)
        assert loaded_yaml.target == signed.target
        assert loaded_yaml.signature == signed.signature

        # JSON save and load
        json_path = tmp_path / "auth_doc.json"
        signed.save(json_path)
        loaded_json = load_authorization_document(json_path)
        assert loaded_json.target == signed.target
        assert loaded_json.signature == signed.signature

        # Direct string load
        loaded_str = load_authorization_document(signed.to_yaml())
        assert loaded_str.scope_hash == signed.scope_hash

    def test_portuguese_field_aliases(self, keypair: tuple[str, str]) -> None:
        priv, pub = keypair
        now = datetime.now(UTC)
        pt_data = {
            "alvo": "https://service.example.com",
            "escopo": ["security_scan"],
            "autorizado_por": "Diretor de Seguranca",
            "contato": "contato@example.com",
            "valido_de": (now - timedelta(hours=2)).isoformat(),
            "valido_ate": (now + timedelta(hours=10)).isoformat(),
        }
        signed = sign_authorization_document(pt_data, private_key=priv, public_key=pub)
        assert signed.target == "https://service.example.com"
        assert signed.authorized_by == "Diretor de Seguranca"

        verified = verify_signed_document(
            signed,
            trusted_public_keys=[pub],
            target="https://service.example.com",
            action="security_scan",
        )
        assert verified.target == "https://service.example.com"

    def test_gate_denies_without_document_default_deny(self) -> None:
        gate = TargetAuthorizationGate()
        target = "https://unauthorized.example.com"

        # Default NEGAR
        with pytest.raises(TargetNotAuthorizedError, match="USAGE_POLICY.md|requires a valid signed authorization"):
            gate.verify_target(target, mode="security_scan", owned_target=False)

        denied = gate.audit_log.query(event_type="target.authorization.denied")
        assert len(denied) == 1
        assert denied[0].details["status"] == "denied"

    def test_gate_accepts_valid_signed_document(self, keypair: tuple[str, str], valid_doc_data: dict) -> None:
        priv, pub = keypair
        gate = TargetAuthorizationGate(trusted_public_keys=[pub])
        signed = sign_authorization_document(valid_doc_data, private_key=priv, public_key=pub)

        rec = gate.verify_target(
            "https://api.example.com",
            mode="security_scan",
            authorization_document=signed,
        )
        assert rec.authorized_by == "Security Team (Lead: Alice)"
        assert rec.ownership == "authorized"

        granted = gate.audit_log.query(event_type="target.authorization.granted")
        assert len(granted) == 1
        assert granted[0].actor == "Security Team (Lead: Alice)"

    def test_gate_rejects_expired_document(self, keypair: tuple[str, str], valid_doc_data: dict) -> None:
        priv, pub = keypair
        gate = TargetAuthorizationGate(trusted_public_keys=[pub])
        now = datetime.now(UTC)
        valid_doc_data["valid_from"] = (now - timedelta(days=2)).isoformat()
        valid_doc_data["valid_until"] = (now - timedelta(days=1)).isoformat()

        signed = sign_authorization_document(valid_doc_data, private_key=priv, public_key=pub)

        with pytest.raises(TargetNotAuthorizedError, match="expired"):
            gate.verify_target(
                "https://api.example.com",
                mode="security_scan",
                authorization_document=signed,
            )

        denied = gate.audit_log.query(event_type="target.authorization.denied")
        assert len(denied) == 1
        assert "expired" in denied[0].details["reason"].lower()

    def test_gate_rejects_not_yet_valid_document(self, keypair: tuple[str, str], valid_doc_data: dict) -> None:
        priv, pub = keypair
        gate = TargetAuthorizationGate(trusted_public_keys=[pub])
        now = datetime.now(UTC)
        valid_doc_data["valid_from"] = (now + timedelta(days=1)).isoformat()
        valid_doc_data["valid_until"] = (now + timedelta(days=2)).isoformat()

        signed = sign_authorization_document(valid_doc_data, private_key=priv, public_key=pub)

        with pytest.raises(TargetNotAuthorizedError, match="not yet valid"):
            gate.verify_target(
                "https://api.example.com",
                mode="security_scan",
                authorization_document=signed,
            )

    def test_gate_rejects_wrong_target(self, keypair: tuple[str, str], valid_doc_data: dict) -> None:
        priv, pub = keypair
        gate = TargetAuthorizationGate(trusted_public_keys=[pub])
        signed = sign_authorization_document(valid_doc_data, private_key=priv, public_key=pub)

        with pytest.raises(TargetNotAuthorizedError, match="Target mismatch"):
            gate.verify_target(
                "https://other.example.com",
                mode="security_scan",
                authorization_document=signed,
            )

    def test_gate_rejects_invalid_signature(self, keypair: tuple[str, str], valid_doc_data: dict) -> None:
        priv, pub = keypair
        gate = TargetAuthorizationGate(trusted_public_keys=[pub])
        signed = sign_authorization_document(valid_doc_data, private_key=priv, public_key=pub)

        # Corrupt signature
        bad_doc = signed.model_copy(update={"signature": "A" * 88})

        with pytest.raises(TargetNotAuthorizedError, match="signature verification failed"):
            gate.verify_target(
                "https://api.example.com",
                mode="security_scan",
                authorization_document=bad_doc,
            )

    def test_gate_rejects_tampered_scope_hash(self, keypair: tuple[str, str], valid_doc_data: dict) -> None:
        priv, pub = keypair
        gate = TargetAuthorizationGate(trusted_public_keys=[pub])
        signed = sign_authorization_document(valid_doc_data, private_key=priv, public_key=pub)

        # Scope tampered without re-signing
        bad_doc = signed.model_copy(update={"scope": ["security_scan", "extreme_attack", "rce"]})

        with pytest.raises(TargetNotAuthorizedError, match="scope hash mismatch|tampering"):
            gate.verify_target(
                "https://api.example.com",
                mode="security_scan",
                authorization_document=bad_doc,
            )

    def test_gate_rejects_untrusted_public_key(self, keypair: tuple[str, str], valid_doc_data: dict) -> None:
        priv, pub = keypair
        _other_priv, other_pub = generate_keypair()
        # Gate only trusts other_pub, not pub
        gate = TargetAuthorizationGate(trusted_public_keys=[other_pub])
        signed = sign_authorization_document(valid_doc_data, private_key=priv, public_key=pub)

        with pytest.raises(TargetNotAuthorizedError, match="not present in the trusted public keys"):
            gate.verify_target(
                "https://api.example.com",
                mode="security_scan",
                authorization_document=signed,
            )

    def test_gate_rejects_insufficient_scope(self, keypair: tuple[str, str], valid_doc_data: dict) -> None:
        priv, pub = keypair
        gate = TargetAuthorizationGate(trusted_public_keys=[pub])
        valid_doc_data["scope"] = ["web_capture"]
        signed = sign_authorization_document(valid_doc_data, private_key=priv, public_key=pub)

        with pytest.raises(TargetNotAuthorizedError, match="not permitted by authorization document scope"):
            gate.verify_target(
                "https://api.example.com",
                mode="security_scan",
                authorization_document=signed,
            )

    def test_gate_allows_wildcard_scope(self, keypair: tuple[str, str], valid_doc_data: dict) -> None:
        priv, pub = keypair
        gate = TargetAuthorizationGate(trusted_public_keys=[pub])
        valid_doc_data["scope"] = ["*"]
        signed = sign_authorization_document(valid_doc_data, private_key=priv, public_key=pub)

        rec = gate.verify_target(
            "https://api.example.com",
            mode="security_scan",
            authorization_document=signed,
        )
        assert rec.ownership == "authorized"

    def test_canonical_payload_and_local_target_check(self) -> None:
        now = datetime.now(UTC)
        payload = create_canonical_payload(
            target="https://target.example.com",
            scope_hash="abc",
            authorized_by="Lead",
            contact="c@e.com",
            valid_from=now,
            valid_until=now + timedelta(hours=1),
        )
        assert isinstance(payload, bytes)
        assert b"target" in payload

        assert is_local_or_owned_target("http://localhost:8000") is True
        assert is_local_or_owned_target("http://127.0.0.1:5000") is True
        assert is_local_or_owned_target(Path("/local/path")) is True
        assert is_local_or_owned_target("https://remote.example.com") is False
