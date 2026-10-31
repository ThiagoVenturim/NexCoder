"""Tests for hybrid code search and symbol retrieval with MMR."""

from pathlib import Path

from faccoder_code_intel.retrieval import CodeSearchIndex
from faccoder_core.retrieval.embeddings import HashEmbedder


def test_code_search_index_hybrid_and_mmr(tmp_path: Path) -> None:
    db_path = tmp_path / "test_code.db"
    embedder = HashEmbedder(dimensions=128)

    py_code = """class BillingService:
    \"\"\"Handles billing and invoices.\"\"\"

    def create_invoice(self, customer_id: str, amount: float) -> str:
        \"\"\"Creates an invoice for customer.\"\"\"
        return f"INV-{customer_id}-{amount}"

    def process_refund(self, invoice_id: str) -> bool:
        \"\"\"Refunds an invoice payment.\"\"\"
        return True
"""

    pas_code = """unit ReportEngine;

interface

type
  TReportEngine = class
  public
    function GenerateSalesReport(StartDate, EndDate: TDateTime): string;
  end;

implementation

function TReportEngine.GenerateSalesReport(StartDate, EndDate: TDateTime): string;
begin
  Result := 'Sales summary report content';
end;

end.
"""

    with CodeSearchIndex(db_path, embedder=embedder) as idx:
        chunks_py = idx.index_code("billing.py", py_code, language="python")
        chunks_pas = idx.index_code("ReportEngine.pas", pas_code, language="delphi")

        assert len(chunks_py) >= 2
        assert len(chunks_pas) >= 1

        # 1. BM25 / FTS lexical search
        fts_hits = idx.search("invoice refund", top_k=5)
        assert len(fts_hits) > 0
        assert any("refund" in h["text"].lower() or "billing" in h["text"].lower() for h in fts_hits)

        # 2. Hybrid search for Delphi report
        report_hits = idx.search("generate sales summary report", top_k=5)
        assert len(report_hits) > 0
        top_hit = report_hits[0]
        assert "ReportEngine" in top_hit["text"] or "Sales" in top_hit["text"]

        # 3. MMR diversified search
        mmr_hits = idx.search("billing invoice", top_k=2, mmr=True, mmr_lambda=0.4)
        assert len(mmr_hits) > 0
        assert len(mmr_hits) <= 2


def test_directory_indexing(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "mod_a.py").write_text("def alpha():\n    return 'alpha'\n", encoding="utf-8")
    (src_dir / "mod_b.py").write_text("def beta():\n    return 'beta'\n", encoding="utf-8")
    (src_dir / "ignore.log").write_text("just some log line\n", encoding="utf-8")

    db_path = tmp_path / "dir_index.db"
    embedder = HashEmbedder(dimensions=64)

    with CodeSearchIndex(db_path, embedder=embedder) as idx:
        indexed_count = idx.index_directory(src_dir, extensions=[".py"])
        assert indexed_count == 2

        hits = idx.search("alpha", top_k=2)
        assert len(hits) >= 1
        assert "alpha" in hits[0]["text"]
