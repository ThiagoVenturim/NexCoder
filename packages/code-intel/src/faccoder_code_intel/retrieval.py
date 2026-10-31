"""Symbol retrieval and semantic search over codebases.

Integrates with faccoder-core HybridStore (SQLite FTS5 + vectors),
rrf_fuse (Reciprocal Rank Fusion), mmr_select (Maximal Marginal Relevance),
second-stage cross-encoder reranking, and HyDE query expansion.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from faccoder_core.retrieval.embeddings import Embedder
from faccoder_core.retrieval.fusion import mmr_select, rrf_fuse
from faccoder_core.retrieval.rerank import NoReranker, Reranker
from faccoder_core.store.sqlite_store import HybridStore

from faccoder_code_intel.chunking import CodeChunk, SymbolChunker
from faccoder_code_intel.query_expansion import HyDEGenerator, QueryRewriter

logger = logging.getLogger(__name__)


class CodeSearchIndex:
    """Semantic and lexical symbol index over source code with HyDE and Reranker support."""

    def __init__(
        self,
        db_path: str | Path,
        embedder: Embedder | None = None,
        chunker: SymbolChunker | None = None,
        reranker: Reranker | None = None,
        rewriter: QueryRewriter | None = None,
        hyde_generator: HyDEGenerator | None = None,
    ):
        self.db_path = Path(db_path)
        self.embedder = embedder
        self.chunker = chunker or SymbolChunker()
        self.reranker = reranker or NoReranker()
        self.rewriter = rewriter or QueryRewriter()
        self.hyde_generator = hyde_generator or HyDEGenerator()

        dims = getattr(embedder, "dimensions", None) if embedder else None
        self.store = HybridStore(self.db_path, dimensions=dims)

    def __enter__(self) -> CodeSearchIndex:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        self.store.close()

    def index_code(
        self,
        file_path: str,
        content: str,
        language: str | None = None,
    ) -> list[CodeChunk]:
        """Parse, chunk, and index source code into the hybrid store."""
        chunks = self.chunker.chunk_content(content, file_path=file_path, language=language)
        if not chunks:
            return []

        embeddings: list[list[float]] | None = None
        if self.embedder is not None:
            embeddings = self.embedder.embed_documents([c.content for c in chunks])

        stored_chunks = [
            chunk.to_stored_chunk(embedding=embeddings[i] if embeddings else None) for i, chunk in enumerate(chunks)
        ]
        self.store.upsert(stored_chunks)
        return chunks

    def index_file(self, file_path: Path | str) -> list[CodeChunk]:
        """Index a single file from the filesystem."""
        p = Path(file_path)
        content = p.read_text(encoding="utf-8", errors="replace")
        return self.index_code(str(p), content)

    def index_directory(
        self,
        root_dir: Path | str,
        extensions: list[str] | None = None,
    ) -> int:
        """Recursively index all matching source files in a directory."""
        root = Path(root_dir)
        count = 0
        ext_set = set(extensions) if extensions else None

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if ext_set and path.suffix.lower() not in ext_set:
                continue
            try:
                self.index_file(path)
                count += 1
            except Exception as exc:
                logger.debug("Skipping unparseable file %s: %s", path, exc)
                continue
        return count

    def search(
        self,
        query: str,
        top_k: int = 10,
        candidates: int = 40,
        vector_weight: float = 1.0,
        bm25_weight: float = 1.0,
        rewrite_query: bool = False,
        hyde: bool = False,
        hyde_language: str = "python",
        rerank: bool = True,
        mmr: bool = False,
        mmr_lambda: float = 0.5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve code chunks via hybrid search with optional HyDE, Reranker, and MMR."""
        # 1. Query Rewriting
        fts_query_str = query
        if rewrite_query and self.rewriter:
            rewritten = self.rewriter.rewrite(query)
            fts_query_str = rewritten.expanded_text

        # 2. BM25 text search
        text_results = self.store.text_search(fts_query_str, k=candidates)

        # 3. Vector search (optionally using HyDE)
        query_vec: list[float] | None = None
        vector_results: list[dict[str, Any]] = []

        if self.embedder is not None:
            if hyde and self.hyde_generator:
                synthetic_code = self.hyde_generator.generate_hypothetical_code(query, language=hyde_language)
                query_vec = self.embedder.embed_query(synthetic_code)
            else:
                query_vec = self.embedder.embed_query(query)

            vector_results = self.store.vector_search(query_vec, k=candidates)

        # 4. Rank fusion (RRF)
        result_lists: list[list[dict[str, Any]]] = []
        weights: list[float] = []

        if vector_results:
            result_lists.append(vector_results)
            weights.append(vector_weight)
        if text_results:
            result_lists.append(text_results)
            weights.append(bm25_weight)

        if not result_lists:
            return []

        fused = rrf_fuse(result_lists, weights=weights)

        # Apply metadata filters if provided
        if where:
            fused = [doc for doc in fused if all(doc.get("metadata", {}).get(k) == v for k, v in where.items())]

        # 5. Second-stage reranker
        if rerank and self.reranker and not isinstance(self.reranker, NoReranker) and fused:
            pool = fused[:candidates]
            fused = self.reranker.rerank(query, pool, top_k=candidates)

        # 6. Optional MMR diversification
        if mmr and query_vec is not None and len(fused) > 1:
            pool = fused[:candidates]
            doc_embeddings = self.embedder.embed_documents([doc["text"] for doc in pool])

            selected_indices = mmr_select(
                doc_embeddings,
                query_vec,
                k=min(top_k, len(pool)),
                lambda_mult=mmr_lambda,
            )
            return [pool[idx] for idx in selected_indices]

        return fused[:top_k]
