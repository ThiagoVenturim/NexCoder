"""Tests for hybrid code search and symbol retrieval with MMR."""

from pathlib import Path
from unittest.mock import MagicMock

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


def test_directory_indexing_with_ignores_and_gitignore(tmp_path: Path) -> None:
    """Ensure index_directory skips .git, .venv, binaries and honors .gitignore rules."""
    src_dir = tmp_path / "project"
    src_dir.mkdir()

    # Source files
    (src_dir / "mod_a.py").write_text("def alpha():\n    return 'alpha'\n", encoding="utf-8")
    (src_dir / "mod_b.py").write_text("def beta():\n    return 'beta'\n", encoding="utf-8")

    # .gitignore rules
    (src_dir / ".gitignore").write_text("ignored_sub/\n*.secret\n", encoding="utf-8")

    # Ignored directory by gitignore
    ignored_sub = src_dir / "ignored_sub"
    ignored_sub.mkdir()
    (ignored_sub / "skip_me.py").write_text("def skip():\n    pass\n", encoding="utf-8")

    # Ignored file pattern by gitignore
    (src_dir / "keys.secret").write_text("secret_token_here", encoding="utf-8")

    # Default ignored directories: .git, .venv
    git_dir = src_dir / ".git"
    git_dir.mkdir()
    (git_dir / "config.py").write_text("git_internal = True", encoding="utf-8")

    venv_dir = src_dir / ".venv"
    venv_dir.mkdir()
    (venv_dir / "env_file.py").write_text("venv_data = 1", encoding="utf-8")

    # Binary files
    (src_dir / "compiled.pyc").write_bytes(b"\x00\x01\x02")
    (src_dir / "tool.exe").write_bytes(b"\x4d\x5a")

    db_path = tmp_path / "dir_index.db"
    embedder = HashEmbedder(dimensions=64)

    with CodeSearchIndex(db_path, embedder=embedder) as idx:
        indexed_count = idx.index_directory(src_dir, extensions=[".py"])
        # Only mod_a.py and mod_b.py should be indexed
        assert indexed_count == 2

        hits = idx.search("alpha", top_k=2)
        assert len(hits) >= 1
        assert "alpha" in hits[0]["text"]

        # Verify ignored files are not present
        skip_hits = idx.search("skip", top_k=5)
        assert not any("skip_me.py" in str(h.get("metadata", {}).get("file_path", "")) for h in skip_hits)


def test_index_code_deletes_stale_chunks(tmp_path: Path) -> None:
    """Ensure re-indexing a file removes chunks of deleted/renamed symbols."""
    db_path = tmp_path / "stale_test.db"
    embedder = HashEmbedder(dimensions=64)

    file_v1 = """def active_func():
    return 1

def old_deprecated_func():
    return 2
"""
    file_v2 = """def active_func():
    return 1
"""
    with CodeSearchIndex(db_path, embedder=embedder) as idx:
        idx.index_code("service.py", file_v1, language="python")
        assert idx.store.count() == 2
        hits_v1 = idx.search("old_deprecated_func", top_k=5)
        assert len(hits_v1) >= 1
        assert any("old_deprecated_func" in h["text"] for h in hits_v1)

        # Re-index service.py with file_v2 (old_deprecated_func removed)
        idx.index_code("service.py", file_v2, language="python")
        assert idx.store.count() == 1

        hits_v2 = idx.search("old_deprecated_func", top_k=5)
        assert not any("old_deprecated_func" in h["text"] for h in hits_v2)

        # active_func should still be found
        hits_active = idx.search("active_func", top_k=5)
        assert len(hits_active) >= 1
        assert any("active_func" in h["text"] for h in hits_active)


def test_search_where_filter_pushdown(tmp_path: Path) -> None:
    """Ensure where filter is pushed down into search queries returning full top_k."""
    db_path = tmp_path / "where_test.db"
    embedder = HashEmbedder(dimensions=64)

    code_py = "def calculate_tax():\n    return 0.1\n"
    code_pas = "function CalculateTax: Double;\nbegin\n  Result := 0.1;\nend;\n"

    with CodeSearchIndex(db_path, embedder=embedder) as idx:
        idx.index_code("tax.py", code_py, language="python")
        idx.index_code("tax.pas", code_pas, language="delphi")

        # Filter strictly for Delphi language
        hits = idx.search("CalculateTax", top_k=1, where={"language": "delphi"})
        assert len(hits) == 1
        assert hits[0]["metadata"].get("language") == "delphi"
        assert "tax.pas" in hits[0]["metadata"].get("file_path")


def test_mmr_reuses_stored_embeddings(tmp_path: Path) -> None:
    """Ensure MMR reuses stored vectors without invoking embedder.embed_documents again."""
    db_path = tmp_path / "mmr_reuse.db"
    mock_embedder = MagicMock(wraps=HashEmbedder(dimensions=64))
    mock_embedder.dimensions = 64

    code = """def calc_alpha():
    return 10

def calc_beta():
    return 20
"""
    with CodeSearchIndex(db_path, embedder=mock_embedder) as idx:
        idx.index_code("calc.py", code, language="python")

        # Reset call count after initial indexing
        mock_embedder.embed_documents.reset_mock()

        # Run search with MMR
        hits = idx.search("calc", top_k=2, mmr=True)
        assert len(hits) >= 1

        # embed_documents must NOT have been called during MMR since stored embeddings are reused
        assert mock_embedder.embed_documents.call_count == 0


def test_index_directory_purges_deleted_files(tmp_path: Path) -> None:
    """Ensure index_directory purges chunks of files deleted from disk under indexed root."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    file_a = src_dir / "mod_a.py"
    file_b = src_dir / "mod_b.py"
    file_a.write_text("def func_a(): return 'a'\n", encoding="utf-8")
    file_b.write_text("def func_b(): return 'b'\n", encoding="utf-8")

    # Outside file that should NOT be purged
    outside_file = tmp_path / "outside.py"
    outside_file.write_text("def func_outside(): return 'out'\n", encoding="utf-8")

    db_path = tmp_path / "purge_test.db"
    embedder = HashEmbedder(dimensions=64)

    with CodeSearchIndex(db_path, embedder=embedder) as idx:
        idx.index_file(outside_file)
        indexed = idx.index_directory(src_dir)
        assert indexed == 2

        # 3 chunks total (outside + mod_a + mod_b)
        assert idx.store.count() == 3

        # Delete mod_b from disk
        file_b.unlink()

        # Re-index src_dir
        indexed = idx.index_directory(src_dir)
        assert indexed == 1

        # mod_b chunks must have been purged, outside must remain
        assert idx.store.count() == 2
        hits_b = idx.search("func_b", top_k=5)
        assert not any("mod_b.py" in str(h.get("metadata", {}).get("file_path", "")) for h in hits_b)

        hits_a = idx.search("func_a", top_k=5)
        assert any("mod_a.py" in str(h.get("metadata", {}).get("file_path", "")) for h in hits_a)

        hits_out = idx.search("func_outside", top_k=5)
        assert any("outside.py" in str(h.get("metadata", {}).get("file_path", "")) for h in hits_out)


def test_gitignore_anchored_and_directory_patterns(tmp_path: Path) -> None:
    """Ensure root-anchored (/pattern) and directory (dir/) gitignore patterns are respected."""
    src_dir = tmp_path / "repo"
    src_dir.mkdir()
    (src_dir / ".gitignore").write_text(
        "/out\n/root_only.py\ntemp/\nsub/*.tmp\n# comment\n\n",
        encoding="utf-8",
    )

    # /out at root: ignored
    out_dir = src_dir / "out"
    out_dir.mkdir()
    (out_dir / "output.py").write_text("def out_dir_func(): pass", encoding="utf-8")

    # nested out dir: should NOT match /out
    nested_dir = src_dir / "nested"
    nested_dir.mkdir()
    nested_out = nested_dir / "out"
    nested_out.mkdir()
    (nested_out / "nested_out.py").write_text("def nested_out_func(): pass", encoding="utf-8")

    # /root_only.py at root: ignored
    (src_dir / "root_only.py").write_text("def root_ignored(): pass", encoding="utf-8")
    # root_only.py in subdirectory: should NOT match /root_only.py
    (nested_dir / "root_only.py").write_text("def nested_allowed(): pass", encoding="utf-8")

    # temp/ anywhere: ignored
    temp_dir = nested_dir / "temp"
    temp_dir.mkdir()
    (temp_dir / "scratch.py").write_text("def scratch(): pass", encoding="utf-8")

    # valid file
    (src_dir / "main.py").write_text("def main(): pass", encoding="utf-8")

    db_path = tmp_path / "gi_anchored.db"
    embedder = HashEmbedder(dimensions=64)

    with CodeSearchIndex(db_path, embedder=embedder) as idx:
        count = idx.index_directory(src_dir, extensions=[".py"])
        # Should index: nested/out/nested_out.py, nested/root_only.py, main.py -> 3 files
        assert count == 3

        hits = idx.search("pass", top_k=10)
        file_paths = [str(h.get("metadata", {}).get("file_path", "")) for h in hits]
        assert not any("out" in fp and "nested" not in fp for fp in file_paths)
        assert not any("scratch.py" in fp for fp in file_paths)
        assert any("nested_out.py" in fp for fp in file_paths)
        assert any("nested_allowed" in h["text"] for h in hits)
        assert any("main.py" in fp for fp in file_paths)
