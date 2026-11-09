"""Parsers registry and factory."""

from __future__ import annotations

from pathlib import Path

from faccoder_code_intel.models import Symbol
from faccoder_code_intel.parsers.base import BaseParser
from faccoder_code_intel.parsers.delphi import DelphiParser
from faccoder_code_intel.parsers.treesitter import TreeSitterParser

_DELPHI_PARSER = DelphiParser()
_TREESITTER_PARSER = TreeSitterParser()

_ALL_PARSERS: list[BaseParser] = [_DELPHI_PARSER, _TREESITTER_PARSER]


def get_parser_for_file(file_path: str | Path) -> BaseParser | None:
    """Return an appropriate parser instance for the given file, or None if unsupported."""
    p = Path(file_path)
    for parser in _ALL_PARSERS:
        if parser.can_parse(p):
            return parser
    return None


def get_parser_for_language(language: str) -> BaseParser | None:
    """Return an appropriate parser for the given canonical language name."""
    lang_lower = language.lower()
    for parser in _ALL_PARSERS:
        if lang_lower in parser.supported_languages:
            return parser
    return None


def parse_file(file_path: str | Path, content: str | None = None) -> list[Symbol]:
    """Convenience function to parse a file or content by path extension."""
    p = Path(file_path)
    parser = get_parser_for_file(p)
    if not parser:
        return []
    if content is None:
        content = p.read_text(encoding="utf-8", errors="replace")
    return parser.parse(content, file_path=str(p))


__all__ = [
    "BaseParser",
    "DelphiParser",
    "TreeSitterParser",
    "get_parser_for_file",
    "get_parser_for_language",
    "parse_file",
]
