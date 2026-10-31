"""Tests for symbol-aware code chunker."""

from faccoder_code_intel.chunking import SymbolChunker
from faccoder_code_intel.models import SymbolType


def test_chunking_python_code() -> None:
    code = """# System imports
import os
import sys

# Global configuration
TIMEOUT = 30

def connect_db(url: str):
    \"\"\"Establishes database connection.\"\"\"
    return url

class DataManager:
    \"\"\"Handles persistence.\"\"\"

    def save(self, record: dict) -> bool:
        \"\"\"Save a single record.\"\"\"
        return True

    def query(self, q: str) -> list:
        \"\"\"Execute query.\"\"\"
        return []
"""
    chunker = SymbolChunker(max_lines_per_chunk=50)
    chunks = chunker.chunk_content(code, file_path="db_service.py")

    assert len(chunks) >= 3

    # Check that preamble chunk was generated
    preamble = chunks[0]
    assert preamble.symbol_type == SymbolType.CODE_BLOCK
    assert "import os" in preamble.content

    # Check function chunk
    connect_chunk = next(c for c in chunks if c.symbol_name == "connect_db")
    assert "Establishes database connection" in connect_chunk.content
    assert connect_chunk.symbol_type == SymbolType.FUNCTION

    # Check StoredChunk conversion
    stored = connect_chunk.to_stored_chunk()
    assert stored.id == connect_chunk.id
    assert stored.metadata["file_path"] == "db_service.py"
    assert stored.metadata["symbol_name"] == "connect_db"
    assert stored.content_hash is not None


def test_large_symbol_splitting() -> None:
    # Generate a function with 60 lines
    lines = ["def massive_routine():"]
    for i in range(50):
        lines.append(f"    x_{i} = {i} * 2")
    lines.append("    return 42")
    code = "\n".join(lines)

    chunker = SymbolChunker(max_lines_per_chunk=25, overlap_lines=5)
    chunks = chunker.chunk_content(code, file_path="heavy.py")

    assert len(chunks) > 1
    assert all("massive_routine" in c.qualified_name for c in chunks)
    assert chunks[0].metadata.get("part") == 1
    assert chunks[1].metadata.get("part") == 2


def test_fallback_chunking() -> None:
    text = "line 1\nline 2\nline 3\nline 4\nline 5\n"
    chunker = SymbolChunker(max_lines_per_chunk=2, overlap_lines=0)
    chunks = chunker.chunk_content(text, file_path="raw_notes.txt")

    assert len(chunks) == 3
    assert chunks[0].symbol_type == SymbolType.CODE_BLOCK
