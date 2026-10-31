"""Symbol retrieval and semantic search over codebases.

Integrates with faccoder-core HybridStore (SQLite FTS5 + vectors),
rrf_fuse (Reciprocal Rank Fusion), mmr_select (Maximal Marginal Relevance),
second-stage cross-encoder reranking, and HyDE query expansion.
"""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path
from typing import Any

from faccoder_core.retrieval.embeddings import Embedder
from faccoder_core.retrieval.fusion import mmr_select, rrf_fuse
from faccoder_core.retrieval.rerank import NoReranker, Reranker
from faccoder_core.store.sqlite_store import HybridStore

from faccoder_code_intel.chunking import CodeChunk, SymbolChunker
from faccoder_code_intel.query_expansion import HyDEGenerator, QueryRewriter

logger = logging.getLogger(__name__)

DEFAULT_IGNORE_DIRS: set[str] = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "build",
    "dist",
    ".idea",
    ".vscode",
}

DEFAULT_BINARY_EXTENSIONS: set[str] = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".obj",
    ".o",
    ".a",
    ".bin",
    ".pyc",
    ".pyo",
    ".pyd",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".db",
    ".sqlite",
    ".sqlite3",
}


def _parse_gitignore(gitignore_path: Path) -> list[str]:
    """Parse pattern lines from a .gitignore file.

    Supported syntax subset:
    - Standard wildcard globs (*, ?, [a-z])
    - Root-anchored patterns starting with '/' (e.g. '/build', '/config.local.json')
    - Directory indicators ending with '/' (e.g. 'temp/', 'logs/')
    - Relative path patterns (e.g. 'docs/*.tmp', 'src/generated/*')
    - Comment lines (#) and blank lines are ignored.

    Limitations:
    - Negation (!pattern) is not parsed.
    - Recursive double-star (**) in mid-path is approximated with fnmatch.
    - Nested .gitignore files in subdirectories are not discovered; the root file is used.
    """
    if not gitignore_path.is_file():
        return []
    patterns: list[str] = []
    try:
        content = gitignore_path.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                patterns.append(stripped)
    except Exception as exc:
        logger.debug("Failed reading .gitignore from %s: %s", gitignore_path, exc)
    return patterns


def _matches_any_pattern(rel_path_str: str, filename: str, patterns: list[str]) -> bool:
    """Check whether a path or filename matches any glob / gitignore pattern.

    Handles root-anchored patterns ('/pattern'), directory-specific patterns ('dir/'),
    and general wildcard patterns (*, ?, [seq]).
    """
    norm_path = rel_path_str.replace("\\", "/").strip("/")
    for pat in patterns:
        raw_pat = pat.strip()
        if not raw_pat:
            continue

        is_anchored = raw_pat.startswith("/")
        clean_pat = raw_pat.lstrip("/").rstrip("/")

        if is_anchored:
            # Anchored to the indexing root
            if norm_path == clean_pat or norm_path.startswith(clean_pat + "/"):
                return True
            if fnmatch.fnmatch(norm_path, clean_pat):
                return True
            continue

        # Directory-scoped pattern (e.g. 'temp/' or 'sub/temp/')
        if raw_pat.endswith("/"):
            if norm_path == clean_pat or norm_path.startswith(clean_pat + "/") or f"/{clean_pat}/" in f"/{norm_path}/":
                return True
            continue

        # If pattern contains a path separator, match against relative path
        if "/" in clean_pat:
            if fnmatch.fnmatch(norm_path, clean_pat) or fnmatch.fnmatch(norm_path, f"*/{clean_pat}"):
                return True
        else:
            # Simple filename / directory pattern matches anywhere in the tree
            if fnmatch.fnmatch(filename, clean_pat) or fnmatch.fnmatch(norm_path, clean_pat):
                return True

    return False


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

    def _delete_file_chunks(self, file_path: str) -> None:
        """Delete existing chunks for a file before indexing to prevent stale symbols."""
        self.store.delete_by_metadata("file_path", file_path)

    def index_code(
        self,
        file_path: str,
        content: str,
        language: str | None = None,
    ) -> list[CodeChunk]:
        """Parse, chunk, and index source code, replacing existing chunks for file_path."""
        self._delete_file_chunks(file_path)

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
        ignore_patterns: list[str] | None = None,
        use_gitignore: bool = True,
    ) -> int:
        """Recursively index source files ignoring binaries, caches, venvs, and .gitignore rules.

        Purges chunks for any files previously indexed under `root_dir` that no longer exist
        or were deleted from disk.
        """
        root = Path(root_dir).resolve()
        count = 0
        ext_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions} if extensions else None

        active_patterns: list[str] = list(ignore_patterns or [])
        if use_gitignore:
            gi_path = root / ".gitignore"
            active_patterns.extend(_parse_gitignore(gi_path))

        seen_files: set[Path] = set()

        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = os.path.relpath(dirpath, root)
            if rel_dir == ".":
                rel_dir = ""

            # Prune ignored directories in-place so os.walk avoids recursing into them
            kept_dirs = []
            for d in dirnames:
                if d in DEFAULT_IGNORE_DIRS:
                    continue
                d_rel = f"{rel_dir}/{d}" if rel_dir else d
                if active_patterns and _matches_any_pattern(d_rel, d, active_patterns):
                    continue
                kept_dirs.append(d)
            dirnames[:] = kept_dirs

            for f in filenames:
                f_path = Path(dirpath) / f
                suffix = f_path.suffix.lower()
                if suffix in DEFAULT_BINARY_EXTENSIONS:
                    continue
                f_rel = f"{rel_dir}/{f}" if rel_dir else f
                if active_patterns and _matches_any_pattern(f_rel, f, active_patterns):
                    continue
                if ext_set and suffix not in ext_set:
                    continue

                try:
                    self.index_file(f_path)
                    seen_files.add(f_path.resolve())
                    count += 1
                except Exception as exc:
                    logger.debug("Skipping unparseable file %s: %s", f_path, exc)
                    continue

        self._purge_deleted_files(root, seen_files)
        return count

    def _purge_deleted_files(self, root: Path, seen_files: set[Path]) -> int:
        """Purge chunks whose file_path is under root but was not seen during directory indexing."""
        all_file_chunks = self.store.get_metadata_values("file_path")
        stale_ids: list[str] = []
        for cid, fp_val in all_file_chunks.items():
            if not isinstance(fp_val, str):
                continue
            fp = Path(fp_val)
            try:
                resolved_fp = fp.resolve()
                if resolved_fp.is_relative_to(root) and resolved_fp not in seen_files:
                    stale_ids.append(cid)
            except Exception as exc:
                logger.debug("Failed resolving file path %s during purge: %s", fp_val, exc)
                continue

        if stale_ids:
            logger.info("Purged %d stale chunks for removed files under %s", len(stale_ids), root)
            self.store.delete(stale_ids)
        return len(stale_ids)

    def _filtered_text_search(self, query: str, k: int, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Perform full-text search with metadata pushdown in SQL."""
        return self.store.text_search(query, k=k, where=where)

    def _filtered_vector_search(
        self, query_vec: list[float], k: int, where: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Perform vector search with metadata pushdown.

        Note on large repositories: When metadata filters are present, candidates are
        pre-filtered via SQLite JSON pushdown and scored in memory using vectorized NumPy.
        For large repositories, this avoids scanning the entire database while preserving
        exact cosine similarity over the filtered subset.
        """
        return self.store.vector_search(query_vec, k=k, where=where)

    def _get_or_compute_embeddings(self, docs: list[dict[str, Any]], query_dim: int) -> list[list[float]]:
        """Reuse stored vectors from SQLite chunks, computing embeddings only for missing ones."""
        doc_ids = [d["id"] for d in docs]
        stored: dict[str, list[float]] = self.store.get_embeddings(doc_ids) if doc_ids else {}

        missing_indices = [i for i, d in enumerate(docs) if d["id"] not in stored]
        if missing_indices and self.embedder is not None:
            computed = self.embedder.embed_documents([docs[i]["text"] for i in missing_indices])
            for idx, emb in zip(missing_indices, computed, strict=False):
                stored[docs[idx]["id"]] = emb

        return [stored.get(d["id"], [0.0] * query_dim) for d in docs]

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
        """Retrieve code chunks via hybrid search with pushdown filters, HyDE, Reranker, and MMR."""
        # 1. Query Rewriting
        fts_query_str = query
        if rewrite_query and self.rewriter:
            rewritten = self.rewriter.rewrite(query)
            fts_query_str = rewritten.expanded_text

        # 2. BM25 text search with metadata filter pushdown
        text_results = self._filtered_text_search(fts_query_str, k=candidates, where=where)

        # 3. Vector search (optionally using HyDE) with metadata filter pushdown
        query_vec: list[float] | None = None
        vector_results: list[dict[str, Any]] = []

        if self.embedder is not None:
            if hyde and self.hyde_generator:
                synthetic_code = self.hyde_generator.generate_hypothetical_code(query, language=hyde_language)
                query_vec = self.embedder.embed_query(synthetic_code)
            else:
                query_vec = self.embedder.embed_query(query)

            vector_results = self._filtered_vector_search(query_vec, k=candidates, where=where)

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

        # 5. Second-stage reranker
        if rerank and self.reranker and not isinstance(self.reranker, NoReranker) and fused:
            pool = fused[:candidates]
            fused = self.reranker.rerank(query, pool, top_k=candidates)

        # 6. Optional MMR diversification reusing stored embeddings
        if mmr and query_vec is not None and len(fused) > 1:
            pool = fused[:candidates]
            doc_embeddings = self._get_or_compute_embeddings(pool, len(query_vec))

            selected_indices = mmr_select(
                doc_embeddings,
                query_vec,
                k=min(top_k, len(pool)),
                lambda_mult=mmr_lambda,
            )
            return [pool[idx] for idx in selected_indices]

        return fused[:top_k]
