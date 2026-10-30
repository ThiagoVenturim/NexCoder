"""Semantic cache for LLM answers.

If a new question is close enough (cosine similarity above ``threshold``) to a
question already answered, the stored answer is returned without calling the
model. Answers that signal failure ("not found", "I don't know") are never
cached, otherwise one bad answer would be served forever.
"""

from __future__ import annotations

import hashlib
import time

from faccoder_core.retrieval.embeddings import Embedder
from faccoder_core.store.sqlite_store import HybridStore, StoredChunk

NEGATIVE_MARKERS = ("not found", "i don't know", "no information", "nao encontrei", "não encontrei",
                    "não sei", "nao sei")


class SemanticCache:
    def __init__(self, store: HybridStore, embedder: Embedder, *, threshold: float = 0.95,
                 ttl_seconds: int = 7 * 24 * 3600):
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
        self.store.upsert([StoredChunk(
            id=f"cache:{key}",
            text=question,
            metadata={"namespace": namespace, "answer": answer, "created_at": time.time()},
            embedding=self.embedder.embed_query(question),
        )])
        return True
