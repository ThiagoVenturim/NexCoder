"""Tests for pluggable SQLAlchemy storage in control plane (API Keys, Audit Log)."""

from __future__ import annotations

from pathlib import Path

from nexcoder_control.keys.models import APIKeyCreate
from nexcoder_control.keys.store import APIKeyService, SQLAlchemyAPIKeyStore
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_core.store.db import create_db_engine, get_metadata


class TestSQLAlchemyAPIKeyStore:
    def test_key_store_crud(self) -> None:
        store = SQLAlchemyAPIKeyStore(db_url="sqlite:///:memory:")
        service = APIKeyService(store=store)

        created = service.create_key(
            APIKeyCreate(
                name="Production Agent Key",
                owner="devops",
                scopes=["tools:execute", "metrics:read"],
                usd_cap=50.0,
                rate_limit_rpm=120,
            )
        )

        assert created.raw_key.startswith("fc_key_")
        assert created.owner == "devops"

        # Verify key
        record = service.verify_key(created.raw_key, required_scope="tools:execute")
        assert record.key_id == created.key_id
        assert record.owner == "devops"

        # Update spend
        updated = store.update_spend(created.key_id, 12.50)
        assert updated.current_spend_usd == 12.50

        # List all
        all_keys = store.list_all()
        assert len(all_keys) == 1
        assert all_keys[0].key_id == created.key_id

        # Revoke
        revoked = service.revoke_key(created.key_id)
        assert revoked is True

        refetched = store.get(created.key_id)
        assert refetched is not None
        assert refetched.is_active is False


class TestPersistentAuditLog:
    def test_audit_log_persistence_across_instances(self, tmp_path: Path) -> None:
        db_path = tmp_path / "persistent_audit.db"
        db_url = f"sqlite:///{db_path}"
        engine = create_db_engine(db_url)

        # Instance 1: Record events
        audit1 = AppendOnlyAuditLog(engine=engine)
        evt1 = audit1.record_event(
            event_type="auth.login",
            actor="alice",
            action="login",
            resource="control_plane",
            severity="info",
        )
        evt2 = audit1.record_event(
            event_type="key.created",
            actor="alice",
            action="create",
            resource="key_42",
            severity="info",
        )
        evt3 = audit1.record_event(
            event_type="deployment.approved",
            actor="sec-team",
            action="approve",
            resource="cluster-alpha",
            severity="warning",
            details={"approved_by": "sec-team", "environment": "production"},
        )

        valid1, msg1 = audit1.verify_integrity()
        assert valid1 is True
        assert "3 events intact" in msg1

        # Instance 2: Connect to same database, ensure events are reloaded and verified
        audit2 = AppendOnlyAuditLog(engine=engine)
        assert len(audit2._events) == 3
        assert audit2._events[0].event_id == evt1.event_id
        assert audit2._events[1].event_id == evt2.event_id
        assert audit2._events[2].event_id == evt3.event_id
        assert audit2._events[2].details["environment"] == "production"

        valid2, msg2 = audit2.verify_integrity()
        assert valid2 is True
        assert "3 events intact" in msg2

        # Record a 4th event on second instance
        audit2.record_event(
            event_type="security.audit.complete",
            actor="auditor",
            action="verify",
            resource="ledger",
            severity="info",
        )
        valid3, msg3 = audit2.verify_integrity()
        assert valid3 is True
        assert "4 events intact" in msg3


class TestSQLAlchemySmokeSchema:
    def test_generic_schema_creation(self) -> None:
        engine = create_db_engine("sqlite:///:memory:")
        meta = get_metadata()
        meta.create_all(engine)

        expected_tables = {"chunks", "meta", "audit_events", "api_keys"}
        assert expected_tables.issubset(set(meta.tables.keys()))
