"""Base parser interface for language analyzers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from faccoder_code_intel.models import Symbol


class BaseParser(ABC):
    """Abstract base class for all code parsers."""

    @property
    @abstractmethod
    def supported_languages(self) -> list[str]:
        """List of canonical language names supported by this parser."""

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """List of lowercase file extensions (e.g. ['.py', '.pyi']) handled."""

    @abstractmethod
    def parse(self, content: str, file_path: str = "") -> list[Symbol]:
        """Parse source content and return extracted symbols."""

    def can_parse(self, file_path: str | Path) -> bool:
        """Check if the given file path can be parsed by this parser."""
        suffix = Path(file_path).suffix.lower()
        return suffix in self.supported_extensions

    def make_symbol_id(self, file_path: str, qualified_name: str, start_line: int) -> str:
        """Create a stable identifier for a symbol."""
        clean_path = str(file_path).replace("\\", "/")
        return f"{clean_path}::{qualified_name}:{start_line}"
