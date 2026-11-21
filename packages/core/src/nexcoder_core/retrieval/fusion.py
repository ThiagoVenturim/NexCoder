"""Rank fusion and diversification.

- ``rrf_fuse``: Reciprocal Rank Fusion (Cormack et al., 2009). Combines rankings
  from heterogeneous searches (vector cosine, BM25, graph expansion) using only
  each document's *position*, so score scales never have to be calibrated.
- ``mmr_select``: Maximal Marginal Relevance. Picks documents that are relevant
  to the query but not redundant with documents already picked.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def rrf_fuse(
    result_lists: Sequence[Sequence[dict]],
    *,
    k: int = 60,
    id_field: str = "id",
    weights: Sequence[float] | None = None,
) -> list[dict]:
    """Fuse ranked lists into one deduplicated list.

    Each list contributes ``weight / (k + rank + 1)`` per document. Documents
    found by several strategies accumulate more score. The output carries
    ``_rrf_score`` (normalised to 0..1) and ``_hits`` (number of lists that
    returned the document).
    """
    weights = list(weights) if weights is not None else [1.0] * len(result_lists)
    if len(weights) != len(result_lists):
        raise ValueError("weights must have one value per result list")

    fused: dict = {}
    for weight, results in zip(weights, result_lists, strict=True):
        for rank, doc in enumerate(results):
            doc_id = doc[id_field]
            contribution = weight / (k + rank + 1)
            if doc_id in fused:
                fused[doc_id]["_rrf_score"] += contribution
                fused[doc_id]["_hits"] += 1
            else:
                fused[doc_id] = {**doc, "_rrf_score": contribution, "_hits": 1}

    ranked = sorted(fused.values(), key=lambda d: d["_rrf_score"], reverse=True)
    if ranked:
        top, bottom = ranked[0]["_rrf_score"], ranked[-1]["_rrf_score"]
        span = top - bottom
        for doc in ranked:
            doc["_rrf_score"] = (doc["_rrf_score"] - bottom) / span if span > 0 else 1.0
    return ranked


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def mmr_select(
    doc_embeddings: Sequence[Sequence[float]],
    query_embedding: Sequence[float],
    *,
    k: int = 5,
    lambda_mult: float = 0.5,
) -> list[int]:
    """Return indices of ``k`` documents chosen by MMR, in selection order.

    ``lambda_mult`` = 1.0 is pure relevance, 0.0 is pure diversity.
    """
    docs = np.asarray(doc_embeddings, dtype=float)
    if docs.size == 0:
        return []
    docs = _normalise(docs)
    query = _normalise(np.asarray(query_embedding, dtype=float).reshape(1, -1))[0]

    query_sims = docs @ query
    doc_sims = docs @ docs.T

    selected = [int(np.argmax(query_sims))]
    candidates = set(range(len(docs))) - set(selected)
    while len(selected) < min(k, len(docs)) and candidates:
        best_idx, best_score = -1, -np.inf
        for idx in candidates:
            redundancy = max(doc_sims[idx][s] for s in selected)
            score = lambda_mult * query_sims[idx] - (1 - lambda_mult) * redundancy
            if score > best_score:
                best_idx, best_score = idx, score
        selected.append(best_idx)
        candidates.remove(best_idx)
    return selected
