"""Pluggable SQLAlchemy-backed hybrid vector and text store.

Works with any database supported by SQLAlchemy (PostgreSQL, MySQL, SQL Server,
SQLite) via DB_URL connection strings.
"""

from __future__ import annotations

import json
import re
from typing import Any

import numpy as np
from sqlalchemy import (
    Engine,
    bindparam,
    func,
    or_,
    select,
)

from nexcoder_core.retrieval.fusion import rrf_fuse
from nexcoder_core.store.db import create_db_engine, get_metadata, init_db
from nexcoder_core.store.sqlite_store import StoredChunk, _pack, _unpack

_WORD_RE = re.compile(r"[A-Za-z0-9_]{2,}")


class SQLAlchemyStore:
    """SQLAlchemy-backed store supporting vectors, text search, and hybrid retrieval."""

    def __init__(
        self,
        db_url: str | None = None,
        dimensions: int | None = None,
        engine: Engine | None = None,
    ) -> None:
        self.engine: Engine = engine or create_db_engine(db_url)
        self.dimensions = dimensions
        self.metadata = get_metadata()
        init_db(self.engine)

        self._chunks = self.metadata.tables["chunks"]
        self._meta = self.metadata.tables["meta"]

        self._init_meta()

    def _init_meta(self) -> None:
        with self.engine.begin() as conn:
            stmt = select(self._meta.c.value).where(self._meta.c.key == "dimensions")
            row = conn.execute(stmt).fetchone()
            if row:
                self.dimensions = int(row[0])
            elif self.dimensions:
                insert_stmt = self._meta.insert().values(key="dimensions", value=str(self.dimensions))
                conn.execute(insert_stmt)

    # Writes -----------------------------------------------------------------

    def hashes(self) -> dict[str, str]:
        """Map of chunk id to content hash, used for incremental indexing."""
        with self.engine.connect() as conn:
            stmt = select(self._chunks.c.id, self._chunks.c.content_hash)
            rows = conn.execute(stmt).fetchall()
            return {r[0]: (r[1] or "") for r in rows}

    def upsert(self, chunks: list[StoredChunk]) -> None:
        """Insert or update chunks with parameterized statements."""
        if not chunks:
            return

        with self.engine.begin() as conn:
            for chunk in chunks:
                blob = _pack(chunk.embedding) if chunk.embedding else None
                meta_str = json.dumps(chunk.metadata, ensure_ascii=False)

                check_stmt = select(self._chunks.c.id).where(self._chunks.c.id == chunk.id)
                exists = conn.execute(check_stmt).fetchone()

                if exists:
                    update_stmt = (
                        self._chunks.update()
                        .where(self._chunks.c.id == chunk.id)
                        .values(
                            text=chunk.text,
                            metadata_json=meta_str,
                            content_hash=chunk.content_hash,
                            embedding=blob,
                        )
                    )
                    conn.execute(update_stmt)
                else:
                    insert_stmt = self._chunks.insert().values(
                        id=chunk.id,
                        text=chunk.text,
                        metadata_json=meta_str,
                        content_hash=chunk.content_hash,
                        embedding=blob,
                    )
                    conn.execute(insert_stmt)

    def delete(self, ids: list[str]) -> None:
        """Delete chunks by ID with parameterized statement."""
        if not ids:
            return

        with self.engine.begin() as conn:
            stmt = self._chunks.delete().where(self._chunks.c.id.in_(ids))
            conn.execute(stmt)

    # Reads ------------------------------------------------------------------

    def _row(self, row: Any, score: float) -> dict[str, Any]:
        meta = json.loads(row[2]) if isinstance(row[2], str) else (row[2] or {})
        return {
            "id": row[0],
            "text": row[1],
            "metadata": meta,
            "score": score,
        }

    def get(self, chunk_id: str) -> dict[str, Any] | None:
        """Retrieve chunk by ID."""
        with self.engine.connect() as conn:
            stmt = select(
                self._chunks.c.id,
                self._chunks.c.text,
                self._chunks.c.metadata_json,
            ).where(self._chunks.c.id == chunk_id)
            row = conn.execute(stmt).fetchone()
            return self._row(row, 1.0) if row else None

    def count(self) -> int:
        """Return total count of stored chunks."""
        with self.engine.connect() as conn:
            stmt = select(func.count()).select_from(self._chunks)
            res = conn.execute(stmt).scalar()
            return int(res or 0)

    def vector_search(
        self,
        query_vector: list[float],
        k: int = 20,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search chunks by cosine similarity with optional metadata filtering."""
        with self.engine.connect() as conn:
            stmt = select(
                self._chunks.c.id,
                self._chunks.c.text,
                self._chunks.c.metadata_json,
                self._chunks.c.embedding,
            ).where(self._chunks.c.embedding.isnot(None))
            rows = conn.execute(stmt).fetchall()

        if not rows:
            return []

        # Filter by metadata if where clause provided
        candidates = []
        for r in rows:
            if where:
                meta = json.loads(r[2]) if isinstance(r[2], str) else (r[2] or {})
                if not all(meta.get(wk) == wv for wk, wv in where.items()):
                    continue
            candidates.append(r)

        if not candidates:
            return []

        matrix = np.vstack([_unpack(r[3]) for r in candidates])
        query = np.asarray(query_vector, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(query) or 1.0)
        norms[norms == 0] = 1.0
        sims = (matrix @ query) / norms
        top_indices = np.argsort(-sims)[:k]

        return [self._row(candidates[i], float(sims[i])) for i in top_indices]

    def text_search(
        self,
        query: str,
        k: int = 20,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Parameterized full-text search with metadata filtering."""
        tokens = [t.lower() for t in _WORD_RE.findall(query)]
        if not tokens:
            return []

        # Parameterized LIKE search across candidate tokens
        conditions = [
            self._chunks.c.text.ilike(bindparam(f"tok_{idx}", f"%{tok}%"))
            for idx, tok in enumerate(tokens[:10])
        ]

        with self.engine.connect() as conn:
            stmt = select(
                self._chunks.c.id,
                self._chunks.c.text,
                self._chunks.c.metadata_json,
            ).where(or_(*conditions))
            rows = conn.execute(stmt).fetchall()

        if not rows:
            return []

        # Score by token matches and length
        scored: list[tuple[float, Any]] = []
        for r in rows:
            meta = json.loads(r[2]) if isinstance(r[2], str) else (r[2] or {})
            if where and not all(meta.get(wk) == wv for wk, wv in where.items()):
                continue

            text_lower = r[1].lower()
            hit_count = sum(text_lower.count(tok) for tok in tokens)
            if hit_count > 0:
                score = float(hit_count) / (len(text_lower.split()) + 1.0)
                scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._row(r, sc) for sc, r in scored[:k]]

    def hybrid_search(
        self,
        query: str,
        query_vector: list[float] | None,
        k: int = 10,
        candidates: int = 40,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Combine vector similarity and text search via Reciprocal Rank Fusion."""
        lists: list[list[dict[str, Any]]] = [self.text_search(query, candidates, where=where)]
        if query_vector is not None:
            lists.insert(0, self.vector_search(query_vector, candidates, where=where))
        fused = rrf_fuse(lists)
        return fused[:k]

    def get_embeddings(self, ids: list[str]) -> dict[str, list[float]]:
        """Return mapping of chunk id to embedding vector."""
        if not ids:
            return {}

        with self.engine.connect() as conn:
            stmt = select(
                self._chunks.c.id,
                self._chunks.c.embedding,
            ).where(self._chunks.c.id.in_(ids), self._chunks.c.embedding.isnot(None))
            rows = conn.execute(stmt).fetchall()
            return {r[0]: _unpack(r[1]).tolist() for r in rows if r[1]}

    def delete_by_metadata(self, key: str, value: object) -> int:
        """Delete chunks matching metadata key and value."""
        with self.engine.connect() as conn:
            stmt = select(self._chunks.c.id, self._chunks.c.metadata_json)
            rows = conn.execute(stmt).fetchall()

        to_delete: list[str] = []
        for r in rows:
            meta = json.loads(r[1]) if isinstance(r[1], str) else (r[1] or {})
            if meta.get(key) == value:
                to_delete.append(r[0])

        if to_delete:
            self.delete(to_delete)
        return len(to_delete)

    def get_metadata_values(self, key: str) -> dict[str, object]:
        """Return map of chunk id to metadata[key]."""
        with self.engine.connect() as conn:
            stmt = select(self._chunks.c.id, self._chunks.c.metadata_json)
            rows = conn.execute(stmt).fetchall()

        result: dict[str, object] = {}
        for r in rows:
            meta = json.loads(r[1]) if isinstance(r[1], str) else (r[1] or {})
            if key in meta:
                result[r[0]] = meta[key]
        return result

    def close(self) -> None:
        """Dispose SQLAlchemy engine connections."""
        self.engine.dispose()
