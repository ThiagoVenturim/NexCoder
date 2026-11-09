"""Tests for QueryRewriter, HyDE, and second-stage reranker integration."""

from pathlib import Path

from nexcoder_code_intel.query_expansion import HyDEGenerator, QueryRewriter
from nexcoder_code_intel.retrieval import CodeSearchIndex
from nexcoder_core.retrieval.embeddings import HashEmbedder


class MockReranker:
    """Mock cross-encoder reranker for offline test validation."""

    def __init__(self, boost_keyword: str = "refund"):
        self.boost_keyword = boost_keyword

    def rerank(
        self,
        query: str,
        docs: list[dict],
        *,
        text_field: str = "text",
        top_k: int | None = None,
    ) -> list[dict]:
        ranked = []
        for d in docs:
            score = 10.0 if self.boost_keyword in d.get(text_field, "").lower() else 1.0
            ranked.append({**d, "_rerank_score": score})
        ranked.sort(key=lambda d: d["_rerank_score"], reverse=True)
        return ranked[:top_k] if top_k else ranked


def test_query_rewriter() -> None:
    rewriter = QueryRewriter()
    res = rewriter.rewrite("auth cfg for UserService")

    assert "authenticate" in res.expanded_text
    assert "config" in res.expanded_text
    assert "UserService" in res.symbol_hints
    assert "auth" in res.keywords


def test_hyde_generator() -> None:
    hyde = HyDEGenerator()

    py_code = hyde.generate_hypothetical_code("calculate invoice tax", language="python")
    assert "def calculate_invoice_tax" in py_code
    assert '"""calculate invoice tax"""' in py_code

    pas_code = hyde.generate_hypothetical_code("validate customer order", language="delphi")
    assert "function T" in pas_code
    assert "Result := True;" in pas_code

    ts_code = hyde.generate_hypothetical_code("authenticate user session", language="typescript")
    assert "export async function" in ts_code


def test_search_with_hyde_and_reranker(tmp_path: Path) -> None:
    db_path = tmp_path / "hyde_rerank.db"
    embedder = HashEmbedder(dimensions=128)
    reranker = MockReranker(boost_keyword="refund")

    code_a = """def create_invoice():
    \"\"\"Generates bill.\"\"\"
    return 100
"""
    code_b = """def process_refund():
    \"\"\"Refunds money to customer account.\"\"\"
    return True
"""
    with CodeSearchIndex(db_path, embedder=embedder, reranker=reranker) as index:
        index.index_code("invoice.py", code_a)
        index.index_code("refund.py", code_b)

        # 1. Search with HyDE enabled
        hits = index.search("invoice total", top_k=5, hyde=True, rewrite_query=True)
        assert len(hits) > 0

        # 2. Search with second-stage Reranker boosting 'refund'
        hits_reranked = index.search("billing operation", top_k=5, rerank=True)
        assert len(hits_reranked) > 0
        assert "refund" in hits_reranked[0]["text"]
        assert hits_reranked[0]["_rerank_score"] == 10.0
