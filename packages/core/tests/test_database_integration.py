"""Integration tests for pluggable database drivers and dialects."""

from __future__ import annotations

import os
from typing import Any

import pytest
from nexcoder_core.store.db import create_db_engine, get_metadata, init_db
from nexcoder_core.store.sqlalchemy_store import SQLAlchemyStore
from nexcoder_core.store.sqlite_store import StoredChunk


class TestDatabaseDialectSupport:
    def test_sqlite_integration(self, tmp_path: Any) -> None:
        db_file = tmp_path / "offline_integ.db"
        db_url = f"sqlite:///{db_file}"

        engine = create_db_engine(db_url)
        init_db(engine)

        store = SQLAlchemyStore(engine=engine, dimensions=2)
        store.upsert([
            StoredChunk(
                id="integ-1",
                text="Postgres and MySQL pluggable storage integration test",
                metadata={"env": "ci"},
                embedding=[0.7, 0.7],
            )
        ])
        assert store.count() == 1
        res = store.get("integ-1")
        assert res is not None
        assert res["text"].startswith("Postgres")
        store.close()

    def test_postgres_or_external_db_url_environment(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        """Verify DB_URL environment variable routing works seamlessly."""
        db_file = tmp_path / "env_route.db"
        test_url = f"sqlite:///{db_file}"
        monkeypatch.setenv("DB_URL", test_url)

        # Ensure store picks up DB_URL from environment
        engine = create_db_engine()
        assert str(engine.url) == test_url

        metadata = get_metadata()
        metadata.create_all(engine)
        assert "chunks" in metadata.tables
        assert "api_keys" in metadata.tables
        assert "audit_events" in metadata.tables

    @pytest.mark.skipif(
        not os.environ.get("POSTGRES_TEST_URL"),
        reason="Set POSTGRES_TEST_URL to execute live PostgreSQL integration tests",
    )
    def test_live_postgres_integration(self) -> None:
        live_url = os.environ["POSTGRES_TEST_URL"]
        engine = create_db_engine(live_url)
        init_db(engine)

        store = SQLAlchemyStore(engine=engine, dimensions=2)
        store.upsert([
            StoredChunk(
                id="live-pg-1",
                text="Live PostgreSQL test chunk",
                metadata={"backend": "postgresql"},
                embedding=[0.1, 0.9],
            )
        ])
        assert store.count() >= 1
        store.close()
