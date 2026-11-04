"""Semantic cache for LLM answers.

If a new question is close enough (cosine similarity above ``threshold``) to a
question already answered, the stored answer is returned without calling the
model. Answers that signal failure ("not found", "I don't know") are never
cached, otherwise one bad answer would be served forever.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from faccoder_core.retrieval.embeddings import Embedder
from faccoder_core.store.sqlite_store import HybridStore, StoredChunk

NEGATIVE_MARKERS = (
    "not found",
    "i don't know",
    "no information",
    "nao encontrei",
    "não encontrei",
    "não sei",
    "nao sei",
)
ERROR_MARKERS = ("traceback (most recent call last)", "syntaxerror:", "runtimeerror:", "exception:")


class SemanticCache:
    def __init__(
        self, store: HybridStore, embedder: Embedder, *, threshold: float = 0.95, ttl_seconds: int = 7 * 24 * 3600
    ):
        self.store = store
        self.embedder = embedder
        self.threshold = threshold
        self.ttl_seconds = ttl_seconds

    def get(self, question: str, namespace: str = "default") -> str | None:
        hits = self.store.vector_search(self.embedder.embed_query(question), k=3)
        now = time.time()
        for hit in hits:
            meta = hit["metadata"]
            if meta.get("namespace") != namespace or hit["score"] < self.threshold:
                continue
            if now - float(meta.get("created_at", 0)) > self.ttl_seconds:
                continue
            return meta.get("answer")
        return None

    def put(self, question: str, answer: str, namespace: str = "default") -> bool:
        if any(marker in answer.lower() for marker in NEGATIVE_MARKERS):
            return False
        key = hashlib.sha256(f"{namespace}:{question}".encode()).hexdigest()
        self.store.upsert(
            [
                StoredChunk(
                    id=f"cache:{key}",
                    text=question,
                    metadata={"namespace": namespace, "answer": answer, "created_at": time.time()},
                    embedding=self.embedder.embed_query(question),
                )
            ]
        )
        return True

    @staticmethod
    def tool_cache_key(tool_name: str, arguments: dict[str, Any] | Any) -> str:
        """Deterministic sha256 hash for tool name and its arguments."""
        if isinstance(arguments, dict):
            canonical = json.dumps(arguments, sort_keys=True, default=str)
        else:
            canonical = str(arguments)
        raw = f"{tool_name}:{canonical}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def cache_tool_result(
        self,
        tool_name: str,
        arguments: dict[str, Any] | Any,
        result: str,
        ttl_seconds: int = 3600,
    ) -> bool:
        """Store a successful tool result hashed by its inputs with validity."""
        res_lower = result.lower()
        if any(err in res_lower for err in ERROR_MARKERS):
            return False
        key = self.tool_cache_key(tool_name, arguments)
        chunk_id = f"cache:tool:{key}"
        self.store.upsert(
            [
                StoredChunk(
                    id=chunk_id,
                    text=f"{tool_name}:{key}",
                    metadata={
                        "tool_name": tool_name,
                        "args_hash": key,
                        "result": result,
                        "created_at": time.time(),
                        "ttl_seconds": ttl_seconds,
                    },
                    embedding=self.embedder.embed_query(tool_name),
                )
            ]
        )
        return True

    def get_tool_result(self, tool_name: str, arguments: dict[str, Any] | Any) -> str | None:
        """Retrieve a cached tool result if valid and unexpired."""
        key = self.tool_cache_key(tool_name, arguments)
        chunk_id = f"cache:tool:{key}"
        chunk = self.store.get(chunk_id)
        if chunk and isinstance(chunk, dict) and chunk.get("metadata"):
            meta = chunk["metadata"]
            created_at = float(meta.get("created_at", 0))
            ttl = float(meta.get("ttl_seconds", 3600))
            if time.time() - created_at <= ttl:
                return meta.get("result")
        return None
