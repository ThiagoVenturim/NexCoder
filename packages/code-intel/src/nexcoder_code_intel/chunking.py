"""Symbol-aware code chunking.

Splits source code along syntactic symbol boundaries (functions, methods, classes,
units) so RAG embeddings never cut through the middle of an entity.
"""

from __future__ import annotations

import hashlib
from typing import Any

from nexcoder_core.store.sqlite_store import StoredChunk
from pydantic import BaseModel, ConfigDict, Field

from nexcoder_code_intel.models import Symbol, SymbolType
from nexcoder_code_intel.parsers import get_parser_for_file


class CodeChunk(BaseModel):
    """A semantic chunk of source code bounded by syntactic structures."""

    model_config = ConfigDict(frozen=True)

    id: str
    file_path: str
    content: str
    start_line: int
    end_line: int
    symbol_name: str | None = None
    symbol_type: SymbolType | None = None
    qualified_name: str | None = None
    signature: str | None = None
    docstring: str | None = None
    language: str = "text"
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_stored_chunk(self, embedding: list[float] | None = None) -> StoredChunk:
        """Convert this chunk into nexcoder-core StoredChunk for HybridStore."""
        meta = {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "symbol_name": self.symbol_name,
            "symbol_type": self.symbol_type.value if self.symbol_type else None,
            "qualified_name": self.qualified_name,
            "signature": self.signature,
            "language": self.language,
            **self.metadata,
        }
        content_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()[:16]
        return StoredChunk(
            id=self.id,
            text=self.content,
            metadata=meta,
            embedding=embedding,
            content_hash=content_hash,
        )


class SymbolChunker:
    """Chunks code files using parsed AST symbol boundaries."""

    def __init__(self, max_lines_per_chunk: int = 100, overlap_lines: int = 10):
        self.max_lines_per_chunk = max_lines_per_chunk
        self.overlap_lines = overlap_lines

    def chunk_content(
        self,
        content: str,
        file_path: str,
        symbols: list[Symbol] | None = None,
        language: str | None = None,
    ) -> list[CodeChunk]:
        """Produce semantic code chunks for a given file content."""
        if not content.strip():
            return []

        clean_path = str(file_path).replace("\\", "/")
        lines = content.splitlines()

        # If symbols not provided, attempt parsing
        if symbols is None:
            parser = get_parser_for_file(file_path)
            symbols = parser.parse(content, file_path=file_path) if parser else []

        if not symbols:
            return self._fallback_line_chunks(lines, clean_path, language or "text")

        # Select significant boundaries: prefer methods, functions, and standalone classes
        primary_symbols = [
            s
            for s in symbols
            if s.symbol_type
            in {
                SymbolType.FUNCTION,
                SymbolType.METHOD,
                SymbolType.CONSTRUCTOR,
                SymbolType.DESTRUCTOR,
                SymbolType.CLASS,
                SymbolType.INTERFACE,
                SymbolType.STRUCT,
            }
        ]

        # If only module/uses symbols exist, use all symbols
        if not primary_symbols:
            primary_symbols = [s for s in symbols if s.symbol_type != SymbolType.MODULE]

        if not primary_symbols:
            return self._fallback_line_chunks(lines, clean_path, language or symbols[0].language)

        # Sort symbols by starting line
        primary_symbols.sort(key=lambda s: s.location.start_line)

        chunks: list[CodeChunk] = []
        last_covered_line = 0

        # Build map of container symbols to their child routine starting lines to avoid overlap
        child_starts: dict[str, int] = {}
        for s in symbols:
            if s.parent_id and s.symbol_type in {
                SymbolType.FUNCTION,
                SymbolType.METHOD,
                SymbolType.CONSTRUCTOR,
                SymbolType.DESTRUCTOR,
            }:
                current_min = child_starts.get(s.parent_id, 999999)
                child_starts[s.parent_id] = min(current_min, s.location.start_line)

        for sym in primary_symbols:
            sym_start = max(1, sym.location.start_line)
            sym_end = min(len(lines), sym.location.end_line)

            # Avoid class/method overlap: truncate container to header prior to first child routine
            if sym.symbol_type in {SymbolType.CLASS, SymbolType.STRUCT, SymbolType.INTERFACE}:
                first_child_start = child_starts.get(sym.id)
                if first_child_start and first_child_start > sym_start:
                    sym_end = min(sym_end, first_child_start - 1)

            # Check if there is an uncovered preamble/gap before this symbol
            if sym_start > last_covered_line + 1:
                gap_start = last_covered_line + 1
                gap_end = sym_start - 1
                gap_lines = lines[gap_start - 1 : gap_end]
                gap_text = "\n".join(gap_lines).strip()
                if gap_text:
                    gap_id = f"{clean_path}:preamble:{gap_start}-{gap_end}"
                    chunks.append(
                        CodeChunk(
                            id=gap_id,
                            file_path=clean_path,
                            content=gap_text,
                            start_line=gap_start,
                            end_line=gap_end,
                            symbol_name=None,
                            symbol_type=SymbolType.CODE_BLOCK,
                            language=sym.language,
                        )
                    )

            # Extract symbol lines
            sym_lines = lines[sym_start - 1 : sym_end]
            sym_text = "\n".join(sym_lines).strip()

            if not sym_text:
                last_covered_line = max(last_covered_line, sym_end)
                continue

            # If symbol is excessively large, subdivide safely
            if len(sym_lines) > self.max_lines_per_chunk:
                sub_chunks = self._split_large_symbol(sym_lines, sym, clean_path, sym_start)
                chunks.extend(sub_chunks)
            else:
                chunk_id = f"{clean_path}:{sym.qualified_name}:{sym_start}-{sym_end}"
                chunks.append(
                    CodeChunk(
                        id=chunk_id,
                        file_path=clean_path,
                        content=sym_text,
                        start_line=sym_start,
                        end_line=sym_end,
                        symbol_name=sym.name,
                        symbol_type=sym.symbol_type,
                        qualified_name=sym.qualified_name,
                        signature=sym.signature.raw if sym.signature else None,
                        docstring=sym.docstring,
                        language=sym.language,
                        metadata={"parent_id": sym.parent_id, **sym.metadata},
                    )
                )

            last_covered_line = max(last_covered_line, sym_end)

        # Check for trailing lines after the last symbol
        if last_covered_line < len(lines):
            trailing_start = last_covered_line + 1
            trailing_end = len(lines)
            trailing_lines = lines[trailing_start - 1 : trailing_end]
            trailing_text = "\n".join(trailing_lines).strip()
            if trailing_text:
                trail_id = f"{clean_path}:trailing:{trailing_start}-{trailing_end}"
                chunks.append(
                    CodeChunk(
                        id=trail_id,
                        file_path=clean_path,
                        content=trailing_text,
                        start_line=trailing_start,
                        end_line=trailing_end,
                        symbol_name=None,
                        symbol_type=SymbolType.CODE_BLOCK,
                        language=primary_symbols[0].language if primary_symbols else "text",
                    )
                )

        return chunks

    def _split_large_symbol(
        self,
        sym_lines: list[str],
        sym: Symbol,
        clean_path: str,
        start_offset: int,
    ) -> list[CodeChunk]:
        sub_chunks: list[CodeChunk] = []
        step = self.max_lines_per_chunk - self.overlap_lines
        total = len(sym_lines)

        for i in range(0, total, step):
            slice_lines = sym_lines[i : i + self.max_lines_per_chunk]
            slice_text = "\n".join(slice_lines).strip()
            if not slice_text:
                continue
            c_start = start_offset + i
            c_end = start_offset + min(i + len(slice_lines) - 1, total - 1)
            part_idx = (i // step) + 1
            chunk_id = f"{clean_path}:{sym.qualified_name}:p{part_idx}:{c_start}-{c_end}"
            sub_chunks.append(
                CodeChunk(
                    id=chunk_id,
                    file_path=clean_path,
                    content=slice_text,
                    start_line=c_start,
                    end_line=c_end,
                    symbol_name=sym.name,
                    symbol_type=sym.symbol_type,
                    qualified_name=sym.qualified_name,
                    signature=sym.signature.raw if sym.signature else None,
                    docstring=sym.docstring,
                    language=sym.language,
                    metadata={"part": part_idx, "parent_id": sym.parent_id, **sym.metadata},
                )
            )
        return sub_chunks

    def _fallback_line_chunks(self, lines: list[str], clean_path: str, language: str) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        step = self.max_lines_per_chunk - self.overlap_lines
        total = len(lines)

        for i in range(0, total, step):
            slice_lines = lines[i : i + self.max_lines_per_chunk]
            slice_text = "\n".join(slice_lines).strip()
            if not slice_text:
                continue
            c_start = i + 1
            c_end = min(i + len(slice_lines), total)
            chunk_id = f"{clean_path}:lines:{c_start}-{c_end}"
            chunks.append(
                CodeChunk(
                    id=chunk_id,
                    file_path=clean_path,
                    content=slice_text,
                    start_line=c_start,
                    end_line=c_end,
                    symbol_name=None,
                    symbol_type=SymbolType.CODE_BLOCK,
                    language=language,
                )
            )
        return chunks
