from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def search_code(
    query: str,
    path: str = ".",
    limit: int = 10,
) -> dict[str, Any]:
    """Search code across the target path using lexical and symbol matching."""
    try:
        from faccoder_code_intel.retrieval import CodeSearchIndex
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Code intelligence package not available: {exc}",
        }

    root_path = Path(path).resolve()
    db_path = root_path / ".faccoder_index.db" if root_path.is_dir() else root_path.parent / ".faccoder_index.db"

    with CodeSearchIndex(db_path=db_path) as index:
        if root_path.is_file():
            index.index_file(root_path)
            indexed_count = 1
        elif root_path.is_dir():
            indexed_count = index.index_directory(root_path)
        else:
            indexed_count = 0

        raw_results = index.search(query=query, top_k=limit) if indexed_count > 0 else []

    return {
        "status": "success",
        "query": query,
        "path": str(root_path),
        "total_symbols_indexed": indexed_count,
        "results_count": len(raw_results),
        "results": raw_results,
    }


def impact_analysis(
    symbol_name: str,
    path: str = ".",
    max_depth: int = 3,
) -> dict[str, Any]:
    """Calculate blast radius and affected symbols when modifying a symbol."""
    try:
        from faccoder_code_intel.graph import CodeGraph
        from faccoder_code_intel.parsers import parse_file
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Code intelligence package not available: {exc}",
        }

    root_path = Path(path).resolve()
    graph = CodeGraph()

    # Parse and register symbols in target path
    source_files: list[Path] = []
    if root_path.is_file():
        source_files = [root_path]
    elif root_path.is_dir():
        for ext in ("*.py", "*.pas"):
            source_files.extend(root_path.glob(f"**/{ext}"))
            if len(source_files) >= 50:
                break

    for file_path in source_files:
        try:
            for sym in parse_file(file_path):
                graph.add_symbol(sym)
        except Exception as exc:
            logger.debug("Skipping file during graph parsing: %s", exc)
            continue

    # Attempt to resolve symbol
    target_id = None
    for sym_id, sym_data in graph.graph.nodes(data=True):
        if sym_data.get("name") == symbol_name or sym_id == symbol_name:
            target_id = sym_id
            break

    if not target_id:
        # Fallback or synthetic target if graph has no matching symbol
        return {
            "status": "not_found",
            "symbol_name": symbol_name,
            "message": f"Symbol '{symbol_name}' not found in target path.",
            "total_nodes": graph.graph.number_of_nodes(),
        }

    report = graph.impact_analysis(symbol_id=target_id, max_depth=max_depth)

    return {
        "status": "success",
        "target_symbol": report.target_symbol_id,
        "blast_radius": report.total_dependents,
        "affected_count": len(report.affected_symbols),
        "affected_symbols": [
            {
                "symbol_id": a.symbol_id,
                "distance": a.distance,
                "relationship_path": a.relationship_path,
            }
            for a in report.affected_symbols
        ],
    }


def generate_docs(
    path: str = ".",
    level: str = "module",
) -> dict[str, Any]:
    """Generate bottom-up documentation synthesized from code symbols."""
    try:
        from faccoder_code_intel.docgen import BottomUpDocEngine
        from faccoder_code_intel.parsers import parse_file
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Code intelligence package not available: {exc}",
        }

    root_path = Path(path).resolve()
    symbols = []
    source_files: list[Path] = []
    if root_path.is_file():
        source_files = [root_path]
    elif root_path.is_dir():
        for ext in ("*.py", "*.pas"):
            source_files.extend(root_path.glob(f"**/{ext}"))
            if len(source_files) >= 20:
                break

    for file_path in source_files:
        try:
            symbols.extend(parse_file(file_path))
        except Exception as exc:
            logger.debug("Skipping file during docgen parsing: %s", exc)
            continue

    engine = BottomUpDocEngine()
    doc_tree = engine.generate_tree(symbols) if symbols else {}

    return {
        "status": "success",
        "path": str(root_path),
        "symbols_parsed": len(symbols),
        "doc_nodes_count": len(doc_tree),
        "docs": [node.model_dump() for node in doc_tree.values()],
    }
