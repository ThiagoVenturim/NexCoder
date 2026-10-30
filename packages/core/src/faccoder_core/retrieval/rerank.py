"""Second-stage reranking.

First-stage retrieval (vector + BM25 + RRF) is fast and recall-oriented. A
cross-encoder then reads query and candidate *together* and produces a much
more precise relevance score. Rerank the top 20-50 candidates, not the whole
corpus: cross-encoders are expensive.

Rerankers:

- ``cross-encoder``: local sentence-transformers CrossEncoder
  (``BAAI/bge-reranker-v2-m3`` is multilingual and handles code well).
- ``llm``: asks a small-tier model to score candidates; no extra model download.
- ``none``: keep first-stage order.
"""

from __future__ import annotations

import logging
from typing import Protocol

from faccoder_core.config import RerankerSpec

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    def rerank(self, query: str, docs: list[dict], *, text_field: str = "text",
               top_k: int | None = None) -> list[dict]: ...


class NoReranker:
    def rerank(self, query: str, docs: list[dict], *, text_field: str = "text",
               top_k: int | None = None) -> list[dict]:
        return docs[:top_k] if top_k else docs


class CrossEncoderReranker:
    def __init__(self, model: str):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise ImportError("pip install faccoder-core[local-embeddings]") from exc
        self._model = CrossEncoder(model)

    def rerank(self, query: str, docs: list[dict], *, text_field: str = "text",
               top_k: int | None = None) -> list[dict]:
        if not docs:
            return []
        scores = self._model.predict([(query, d.get(text_field, "")[:4000]) for d in docs])
        ranked = [{**d, "_rerank_score": float(s)} for d, s in zip(docs, scores, strict=True)]
        ranked.sort(key=lambda d: d["_rerank_score"], reverse=True)
        return ranked[:top_k] if top_k else ranked


def build_reranker(spec: RerankerSpec) -> Reranker:
    if not spec.enabled or spec.provider == "none":
        return NoReranker()
    if spec.provider == "cross-encoder":
        try:
            return CrossEncoderReranker(spec.model)
        except ImportError:
            logger.warning("sentence-transformers not installed; reranking disabled")
            return NoReranker()
    raise ValueError(f"Unknown reranker '{spec.provider}'")
