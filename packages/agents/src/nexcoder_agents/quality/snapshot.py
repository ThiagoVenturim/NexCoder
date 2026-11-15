"""In-memory view of a project used by the quality detectors.

The snapshot holds file contents, the symbols extracted by `nexcoder-code-intel`
and the `CodeGraph` built from them, so detectors never touch the disk.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from nexcoder_code_intel.graph import CodeGraph
from nexcoder_code_intel.models import Symbol
from nexcoder_code_intel.parsers import parse_file

SOURCE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cs", ".pas", ".php", ".kt"})
SQL_SUFFIXES = frozenset({".sql"})
_SKIP_DIRS = frozenset({"__pycache__", "node_modules", "venv", "dist", "build", "target"})
_MAX_FILE_BYTES = 1_000_000


def is_test_path(rel_path: str) -> bool:
    """Tell whether a relative POSIX path belongs to a test suite."""
    parts = [p.lower() for p in rel_path.split("/")]
    stem = parts[-1].rsplit(".", 1)[0]
    if any(p in {"tests", "test", "__tests__", "spec"} for p in parts[:-1]):
        return True
    return stem.startswith("test_") or stem.endswith(("_test", ".test", ".spec")) or stem == "conftest"


@dataclass
class ProjectSnapshot:
    """Source files, symbols and code graph of one project."""

    name: str
    files: dict[str, str] = field(default_factory=dict)  # relative POSIX path -> text (source and SQL files)
    all_paths: list[str] = field(default_factory=list)  # every file path in the project, relative POSIX
    symbols: list[Symbol] = field(default_factory=list)
    graph: CodeGraph = field(default_factory=CodeGraph)
    _python_trees: dict[str, ast.Module | None] = field(default_factory=dict, repr=False)

    @classmethod
    def from_files(
        cls,
        files: dict[str, str],
        name: str = "project",
        all_paths: list[str] | None = None,
    ) -> ProjectSnapshot:
        """Build a snapshot from in-memory `relative path -> content` pairs."""
        normalized = {path.replace("\\", "/"): content for path, content in sorted(files.items())}
        symbols: list[Symbol] = []
        for rel_path, content in normalized.items():
            if Path(rel_path).suffix.lower() not in SOURCE_SUFFIXES:
                continue
            for sym in parse_file(rel_path, content=content):
                symbols.append(
                    sym.model_copy(
                        update={
                            "id": f"{rel_path}::{sym.qualified_name}:{sym.location.start_line}",
                            "location": sym.location.model_copy(update={"file_path": rel_path}),
                        }
                    )
                )
        # Parent ids produced by the parser point at pre-normalization ids; remap them.
        symbols = _remap_parents(symbols)
        graph = CodeGraph()
        graph.add_symbols(symbols)
        paths = sorted({*normalized, *(p.replace("\\", "/") for p in (all_paths or []))})
        return cls(name=name, files=normalized, all_paths=paths, symbols=symbols, graph=graph)

    @classmethod
    def from_directory(cls, root: Path | str) -> ProjectSnapshot:
        """Read a project directory into a snapshot.

        This only reads files. Callers that expose it to users must first pass the
        control-plane target gate (see `QualityReviewer.review`).
        """
        base = Path(root).resolve()
        if not base.is_dir():
            raise FileNotFoundError(f"Project directory not found: {base}")

        files: dict[str, str] = {}
        all_paths: list[str] = []
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel_parts = path.relative_to(base).parts
            if any(part.startswith(".") or part in _SKIP_DIRS for part in rel_parts[:-1]):
                continue
            rel_path = "/".join(rel_parts)
            all_paths.append(rel_path)
            suffix = path.suffix.lower()
            if suffix not in SOURCE_SUFFIXES and suffix not in SQL_SUFFIXES:
                continue
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            files[rel_path] = path.read_text(encoding="utf-8-sig", errors="replace")
        return cls.from_files(files, name=base.name, all_paths=all_paths)

    def source_files(self, include_tests: bool = False) -> dict[str, str]:
        """Return source files (no SQL), optionally including tests."""
        return {
            path: content
            for path, content in self.files.items()
            if Path(path).suffix.lower() in SOURCE_SUFFIXES and (include_tests or not is_test_path(path))
        }

    def sql_files(self) -> dict[str, str]:
        return {p: c for p, c in self.files.items() if Path(p).suffix.lower() in SQL_SUFFIXES}

    def python_tree(self, rel_path: str) -> ast.Module | None:
        """Parse a Python file once; return None when it does not parse."""
        if rel_path not in self._python_trees:
            try:
                self._python_trees[rel_path] = ast.parse(self.files[rel_path])
            except (SyntaxError, ValueError, KeyError):
                self._python_trees[rel_path] = None
        return self._python_trees[rel_path]

    def python_trees(self, include_tests: bool = False) -> list[tuple[str, ast.Module]]:
        trees: list[tuple[str, ast.Module]] = []
        for rel_path in self.source_files(include_tests=include_tests):
            if rel_path.endswith(".py"):
                tree = self.python_tree(rel_path)
                if tree is not None:
                    trees.append((rel_path, tree))
        return trees


def _remap_parents(symbols: list[Symbol]) -> list[Symbol]:
    """Point `parent_id` at the normalized id of the enclosing symbol in the same file."""
    by_file_qname: dict[tuple[str, str], str] = {}
    for sym in symbols:
        by_file_qname.setdefault((sym.location.file_path, sym.qualified_name), sym.id)

    remapped: list[Symbol] = []
    for sym in symbols:
        parent_id: str | None = None
        if sym.parent_id and "." in sym.qualified_name:
            parent_qname = sym.qualified_name.rsplit(".", 1)[0]
            parent_id = by_file_qname.get((sym.location.file_path, parent_qname))
        remapped.append(sym.model_copy(update={"parent_id": parent_id}))
    return remapped


__all__ = ["SOURCE_SUFFIXES", "SQL_SUFFIXES", "ProjectSnapshot", "is_test_path"]
