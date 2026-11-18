"""Tests for pluggable SQLAlchemy store and multi-database support."""

from __future__ import annotations

import pytest
from nexcoder_core.store.db import create_db_engine, get_db_url, normalize_db_url
from nexcoder_core.store.sqlalchemy_store import SQLAlchemyStore
from nexcoder_core.store.sqlite_store import HybridStore, StoredChunk


class TestPluggableDBConfig:
    def test_default_db_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DB_URL", raising=False)
        monkeypatch.delenv("NEXCODER_DB_URL", raising=False)
        url = get_db_url()
        assert "sqlite:" in url

    def test_env_db_url_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_URL", "postgresql+psycopg2://usr:pwd@localhost:5432/nexcoder")
        assert get_db_url() == "postgresql+psycopg2://usr:pwd@localhost:5432/nexcoder"

    def test_normalize_postgres_url(self) -> None:
        raw = "postgres://usr:pwd@localhost:5432/mydb"
        assert normalize_db_url(raw) == "postgresql://usr:pwd@localhost:5432/mydb"

    def test_normalize_odbc_connection_string(self) -> None:
        raw_odbc = "Driver={ODBC Driver 18 for SQL Server};Server=tcp:sqlserver,1433;Database=nexcoder;"
        normalized = normalize_db_url(raw_odbc)
        assert normalized.startswith("mssql+pyodbc:///?odbc_connect=")
        assert "ODBC+Driver+18" in normalized or "ODBC%20Driver%2018" in normalized or "ODBC" in normalized


class TestSQLAlchemyStore:
    def test_lifecycle_and_vector_search(self) -> None:
        engine = create_db_engine("sqlite:///:memory:")
        store = SQLAlchemyStore(engine=engine, dimensions=3)

        chunks = [
            StoredChunk(
                id="c1",
                text="The quick brown fox jumps over the lazy dog",
                metadata={"category": "animals", "active": True},
                embedding=[1.0, 0.0, 0.0],
                content_hash="hash1",
            ),
            StoredChunk(
                id="c2",
                text="Artificial intelligence and distributed computing systems",
                metadata={"category": "tech", "active": True},
                embedding=[0.0, 1.0, 0.0],
                content_hash="hash2",
            ),
            StoredChunk(
                id="c3",
                text="PostgreSQL and SQLAlchemy pluggable database architectures",
                metadata={"category": "tech", "active": False},
                embedding=[0.0, 0.8, 0.2],
                content_hash="hash3",
            ),
        ]

        store.upsert(chunks)
        assert store.count() == 3

        # Hashes
        hashes = store.hashes()
        assert hashes["c1"] == "hash1"
        assert hashes["c2"] == "hash2"

        # Get
        c1 = store.get("c1")
        assert c1 is not None
        assert c1["text"] == "The quick brown fox jumps over the lazy dog"
        assert c1["metadata"]["category"] == "animals"

        # Vector search
        hits = store.vector_search([1.0, 0.0, 0.0], k=2)
        assert len(hits) == 2
        assert hits[0]["id"] == "c1"
        assert hits[0]["score"] > 0.99

        # Vector search with metadata filter
        tech_hits = store.vector_search([0.0, 1.0, 0.0], k=5, where={"active": True})
        assert len(tech_hits) == 2
        assert all(h["metadata"]["active"] is True for h in tech_hits)

        # Text search
        text_hits = store.text_search("PostgreSQL architectures", k=2)
        assert len(text_hits) >= 1
        assert text_hits[0]["id"] == "c3"

        # Hybrid search
        hybrid_hits = store.hybrid_search("computing systems", [0.0, 1.0, 0.0], k=2)
        assert len(hybrid_hits) >= 1
        assert hybrid_hits[0]["id"] == "c2"

        # Metadata operations
        deleted_count = store.delete_by_metadata("category", "animals")
        assert deleted_count == 1
        assert store.count() == 2
        assert store.get("c1") is None

        values = store.get_metadata_values("category")
        assert values == {"c2": "tech", "c3": "tech"}

        # Embeddings
        embs = store.get_embeddings(["c2"])
        assert "c2" in embs
        assert len(embs["c2"]) == 3

        # Delete
        store.delete(["c2"])
        assert store.count() == 1
        assert store.get("c2") is None

        store.close()


class TestHybridStorePluggableBackend:
    def test_hybrid_store_with_db_url(self) -> None:
        store = HybridStore(db_url="sqlite:///:memory:", dimensions=4)
        assert store._sa_store is not None

        chunks = [
            StoredChunk(
                id="doc1",
                text="Modern cloud native applications running on Kubernetes and Docker containers.",
                metadata={"framework": "k8s"},
                embedding=[0.5, 0.5, 0.5, 0.5],
            )
        ]
        store.upsert(chunks)
        assert store.count() == 1

        hit = store.get("doc1")
        assert hit is not None
        assert "Kubernetes" in hit["text"]

        v_hits = store.vector_search([0.5, 0.5, 0.5, 0.5], k=1)
        assert len(v_hits) == 1
        assert v_hits[0]["id"] == "doc1"

        store.close()
