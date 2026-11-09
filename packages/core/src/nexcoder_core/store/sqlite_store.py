"""Local hybrid store: vectors + BM25 full-text in one SQLite file.

Zero infrastructure: ``pip install`` and index. Vector search uses the
``sqlite-vec`` extension when available and falls back to an exact numpy scan
(fine up to a few hundred thousand chunks). Full-text search uses SQLite FTS5
with real BM25 ranking. For multi-user deployments use the Postgres backend
(pgvector + tsvector) instead; the interface is the same.

Hybrid search = vector top-N + BM25 top-N fused with RRF.
"""

from __future__ import annotations

import json
import re
import sqlite3
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from nexcoder_core.retrieval.fusion import rrf_fuse


@dataclass
class StoredChunk:
    id: str
    text: str
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None
    content_hash: str | None = None


def _pack(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _unpack(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 query.

    Identifiers are split on CamelCase and underscores so that a question about
    "customer invoice" also matches ``CustomerInvoiceService``.
    """
    words: list[str] = []
    for token in re.findall(r"[A-Za-z0-9_]+", text):
        parts = [p for p in re.split(r"_", _CAMEL.sub("_", token)) if p]
        words.extend(parts if len(parts) > 1 else [token])
        if len(parts) > 1:
            words.append(token)
    unique = list(dict.fromkeys(w.lower() for w in words if len(w) > 1))
    return " OR ".join(f'"{w}"' for w in unique)


def _searchable(text: str) -> str:
    """Index identifiers both whole and split so FTS can match their parts."""
    extra = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_]{3,}", text):
        split = _CAMEL.sub(" ", token).replace("_", " ")
        if split != token:
            extra.append(split)
    return text + ("\n" + " ".join(extra) if extra else "")


class HybridStore:
    def __init__(self, path: str | Path, dimensions: int | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.dimensions = dimensions
        self._vec = self._load_sqlite_vec()
        self._migrate()

    # Setup ---------------------------------------------------------------

    def _load_sqlite_vec(self) -> bool:
        try:
            import sqlite_vec

            self.conn.enable_load_extension(True)
            sqlite_vec.load(self.conn)
            self.conn.enable_load_extension(False)
            return True
        except Exception:  # noqa: BLE001 - extension is optional
            return False

    def _migrate(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT UNIQUE NOT NULL,
                text TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                content_hash TEXT,
                embedding BLOB
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                searchable, tokenize = 'unicode61 remove_diacritics 2'
            );
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            """
        )
        row = cur.execute("SELECT value FROM meta WHERE key='dimensions'").fetchone()
        if row:
            self.dimensions = int(row["value"])
        elif self.dimensions:
            cur.execute("INSERT INTO meta(key, value) VALUES('dimensions', ?)", (str(self.dimensions),))
        if self._vec and self.dimensions:
            cur.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(embedding float[{self.dimensions}] "
                "distance_metric=cosine)"
            )
        self.conn.commit()

    # Writes --------------------------------------------------------------

    def hashes(self) -> dict[str, str]:
        """Map of chunk id to content hash, used for incremental indexing."""
        return {r["id"]: r["content_hash"] for r in self.conn.execute("SELECT id, content_hash FROM chunks")}

    def upsert(self, chunks: list[StoredChunk]) -> None:
        cur = self.conn.cursor()
        for chunk in chunks:
            existing = cur.execute("SELECT rowid FROM chunks WHERE id=?", (chunk.id,)).fetchone()
            blob = _pack(chunk.embedding) if chunk.embedding else None
            meta = json.dumps(chunk.metadata, ensure_ascii=False)
            if existing:
                rowid = existing["rowid"]
                cur.execute(
                    "UPDATE chunks SET text=?, metadata=?, content_hash=?, embedding=? WHERE rowid=?",
                    (chunk.text, meta, chunk.content_hash, blob, rowid),
                )
                cur.execute("DELETE FROM chunks_fts WHERE rowid=?", (rowid,))
                if self._vec and self.dimensions:
                    cur.execute("DELETE FROM chunks_vec WHERE rowid=?", (rowid,))
            else:
                cur.execute(
                    "INSERT INTO chunks(id, text, metadata, content_hash, embedding) VALUES(?,?,?,?,?)",
                    (chunk.id, chunk.text, meta, chunk.content_hash, blob),
                )
                rowid = cur.lastrowid
            cur.execute("INSERT INTO chunks_fts(rowid, searchable) VALUES(?, ?)", (rowid, _searchable(chunk.text)))
            if self._vec and self.dimensions and blob:
                cur.execute("INSERT INTO chunks_vec(rowid, embedding) VALUES(?, ?)", (rowid, blob))
        self.conn.commit()

    def delete(self, ids: list[str]) -> None:
        cur = self.conn.cursor()
        for chunk_id in ids:
            row = cur.execute("SELECT rowid FROM chunks WHERE id=?", (chunk_id,)).fetchone()
            if not row:
                continue
            cur.execute("DELETE FROM chunks_fts WHERE rowid=?", (row["rowid"],))
            if self._vec and self.dimensions:
                cur.execute("DELETE FROM chunks_vec WHERE rowid=?", (row["rowid"],))
            cur.execute("DELETE FROM chunks WHERE rowid=?", (row["rowid"],))
        self.conn.commit()

    # Reads ---------------------------------------------------------------

    def _row(self, row: sqlite3.Row, score: float) -> dict:
        return {"id": row["id"], "text": row["text"], "metadata": json.loads(row["metadata"]), "score": score}

    def get(self, chunk_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone()
        return self._row(row, 1.0) if row else None

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def vector_search(self, query_vector: list[float], k: int = 20, where: dict | None = None) -> list[dict]:
        """Search chunks by cosine similarity with optional metadata filtering.

        Note: When `where` is provided, candidates are pre-filtered via SQLite JSON pushdown
        and scored in memory using vectorized NumPy operations. For ultra-large repositories,
        partition indices or combine with external vector indexes.
        """
        where_clauses = ["embedding IS NOT NULL"]
        params: list[object] = []
        if where:
            for key, value in where.items():
                safe_key = "".join(c for c in key if c.isalnum() or c == "_")
                where_clauses.append(f"json_extract(metadata, '$.{safe_key}') = ?")
                params.append(value)

        if self._vec and self.dimensions and not where:
            rows = self.conn.execute(
                "SELECT c.*, v.distance FROM chunks_vec v JOIN chunks c ON c.rowid = v.rowid "
                "WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance",
                (_pack(query_vector), k),
            ).fetchall()
            return [self._row(r, 1.0 - float(r["distance"])) for r in rows]

        where_sql = " AND ".join(where_clauses)
        rows = self.conn.execute(
            f"SELECT * FROM chunks WHERE {where_sql}",  # noqa: S608
            params,
        ).fetchall()
        if not rows:
            return []
        matrix = np.vstack([_unpack(r["embedding"]) for r in rows])
        query = np.asarray(query_vector, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(query) or 1.0)
        norms[norms == 0] = 1.0
        sims = (matrix @ query) / norms
        top = np.argsort(-sims)[:k]
        return [self._row(rows[i], float(sims[i])) for i in top]

    def text_search(self, query: str, k: int = 20, where: dict | None = None) -> list[dict]:
        """Full-text search using SQLite FTS5 BM25 with optional metadata filtering."""
        match = fts_query(query)
        if not match:
            return []
        where_clauses = ["chunks_fts MATCH ?"]
        params: list[object] = [match]
        if where:
            for key, value in where.items():
                safe_key = "".join(c for c in key if c.isalnum() or c == "_")
                where_clauses.append(f"json_extract(c.metadata, '$.{safe_key}') = ?")
                params.append(value)

        where_sql = " AND ".join(where_clauses)
        params.append(k)
        rows = self.conn.execute(
            f"SELECT c.*, bm25(chunks_fts) AS rank FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid "  # noqa: S608
            f"WHERE {where_sql} ORDER BY rank LIMIT ?",
            params,
        ).fetchall()
        # bm25() is lower-is-better; flip the sign so higher is better like the other searches.
        return [self._row(r, -float(r["rank"])) for r in rows]

    def hybrid_search(
        self,
        query: str,
        query_vector: list[float] | None,
        k: int = 10,
        candidates: int = 40,
        where: dict | None = None,
    ) -> list[dict]:
        lists = [self.text_search(query, candidates, where=where)]
        if query_vector is not None:
            lists.insert(0, self.vector_search(query_vector, candidates, where=where))
        fused = rrf_fuse(lists)
        return fused[:k]

    def get_embeddings(self, ids: list[str]) -> dict[str, list[float]]:
        """Return a mapping of chunk id to embedding vector for the requested chunk ids."""
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"SELECT id, embedding FROM chunks WHERE id IN ({placeholders}) AND embedding IS NOT NULL",  # noqa: S608
            ids,
        ).fetchall()
        return {r["id"]: _unpack(r["embedding"]).tolist() for r in rows if r["embedding"]}

    def delete_by_metadata(self, key: str, value: object) -> int:
        """Delete all chunks where metadata[key] == value. Returns count of deleted chunks."""
        safe_key = "".join(c for c in key if c.isalnum() or c == "_")
        rows = self.conn.execute(
            f"SELECT id FROM chunks WHERE json_extract(metadata, '$.{safe_key}') = ?",  # noqa: S608
            (value,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            self.delete(ids)
        return len(ids)

    def get_metadata_values(self, key: str) -> dict[str, object]:
        """Return a mapping of chunk id to metadata[key] for chunks that have that metadata key."""
        safe_key = "".join(c for c in key if c.isalnum() or c == "_")
        rows = self.conn.execute(
            f"SELECT id, json_extract(metadata, '$.{safe_key}') AS val FROM chunks WHERE val IS NOT NULL"  # noqa: S608
        ).fetchall()
        return {r["id"]: r["val"] for r in rows}

    def close(self) -> None:
        self.conn.close()
