"""Code graph representation capturing symbols, imports, inheritance, calls, and UI bindings."""

from __future__ import annotations

import logging
from collections import deque
from enum import StrEnum
from typing import Any

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from nexcoder_code_intel.models import RelationshipKind, Symbol, SymbolType

logger = logging.getLogger(__name__)


class EdgeType(StrEnum):
    IMPORTS = "imports"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    CALLS = "calls"
    UI_BINDS = "ui_binds"
    CONTAINS = "contains"
    USES = "uses"


class AffectedSymbol(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol_id: str
    name: str
    symbol_type: SymbolType
    file_path: str
    depth: int
    relationship: str
    path: list[str] = Field(default_factory=list)


class ImpactReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_symbol_id: str
    target_name: str
    impact_score: float
    risk_level: str  # "low", "medium", "high", "critical"
    affected_symbols: list[AffectedSymbol] = Field(default_factory=list)
    affected_files: list[str] = Field(default_factory=list)
    total_dependents: int = 0


class CodeGraph:
    """Directed multirelational graph representing code architecture and dependencies."""

    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph()
        self._name_index: dict[str, list[str]] = {}
        self._qname_index: dict[str, list[str]] = {}

    def add_symbol(self, symbol: Symbol) -> None:
        """Add a symbol node into the code graph."""
        node_id = symbol.id
        self.graph.add_node(
            node_id,
            id=node_id,
            name=symbol.name,
            qualified_name=symbol.qualified_name,
            symbol_type=symbol.symbol_type.value,
            file_path=symbol.location.file_path,
            language=symbol.language,
            start_line=symbol.location.start_line,
            end_line=symbol.location.end_line,
            docstring=symbol.docstring,
            signature=symbol.signature.raw if symbol.signature else None,
            raw_symbol=symbol,
        )

        self._name_index.setdefault(symbol.name, []).append(node_id)
        self._qname_index.setdefault(symbol.qualified_name, []).append(node_id)

        # Automatic parent-child contains edge
        if symbol.parent_id and self.graph.has_node(symbol.parent_id):
            self.add_edge(symbol.parent_id, node_id, EdgeType.CONTAINS)

    def add_symbols(self, symbols: list[Symbol]) -> None:
        """Add a batch of symbols and resolve their mutual relationships."""
        for sym in symbols:
            self.add_symbol(sym)

        # Wire extracted relationships
        for sym in symbols:
            node_id = sym.id
            if sym.parent_id and self.graph.has_node(sym.parent_id):
                self.add_edge(sym.parent_id, node_id, EdgeType.CONTAINS)

            for rel_kind, targets in sym.relationships.items():
                for target_name in targets:
                    try:
                        target_id = self.resolve_symbol_id(target_name, context_file=sym.location.file_path)
                    except ValueError:
                        target_id = None
                    if target_id and target_id != node_id:
                        edge_type = self._map_rel_to_edge(rel_kind)
                        self.add_edge(node_id, target_id, edge_type)

    def add_edge(
        self, source_id: str, target_id: str, kind: str | EdgeType, metadata: dict[str, Any] | None = None
    ) -> None:
        """Add a directed relationship between two symbols."""
        if not self.graph.has_node(source_id) or not self.graph.has_node(target_id):
            return
        edge_kind = kind.value if isinstance(kind, EdgeType) else str(kind)
        meta = metadata or {}
        # In MultiDiGraph, key distinguishes multiple edges between the same pair of symbols
        self.graph.add_edge(source_id, target_id, key=edge_kind, kind=edge_kind, **meta)

    def resolve_symbol_id(self, name_or_id: str, context_file: str | None = None) -> str | None:
        """Resolve a name or qualified name to a concrete symbol ID without ambiguous fallbacks."""
        if self.graph.has_node(name_or_id):
            return name_or_id

        # 1. Exact unique match in qualified name index
        q_cands = self._qname_index.get(name_or_id, [])
        if len(q_cands) == 1:
            return q_cands[0]

        # 2. Gather candidates from qname or short name
        candidates = q_cands if q_cands else self._name_index.get(name_or_id, [])
        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0]

        # Prioritize matching file context
        if context_file:
            matching = [cand for cand in candidates if self.graph.nodes[cand].get("file_path") == context_file]
            if len(matching) == 1:
                return matching[0]
            if len(matching) > 1:
                raise ValueError(
                    f"Ambiguous symbol name '{name_or_id}' in context file '{context_file}'. "
                    f"Matches multiple symbols: {matching}. Use qualified_name to disambiguate."
                )

        raise ValueError(
            f"Ambiguous symbol name '{name_or_id}' matches {len(candidates)} symbols: {candidates}. "
            "Provide qualified_name or context_file to disambiguate."
        )

    def _map_rel_to_edge(self, rel: str) -> EdgeType:
        rel_lower = rel.lower()
        if rel_lower == RelationshipKind.INHERITS:
            return EdgeType.INHERITS
        if rel_lower == RelationshipKind.IMPLEMENTS:
            return EdgeType.IMPLEMENTS
        if rel_lower == RelationshipKind.CALLS:
            return EdgeType.CALLS
        if rel_lower == RelationshipKind.BINDS_UI:
            return EdgeType.UI_BINDS
        if rel_lower == RelationshipKind.USES:
            return EdgeType.USES
        if rel_lower == RelationshipKind.CONTAINS:
            return EdgeType.CONTAINS
        return EdgeType.CALLS

    def impact_analysis(
        self,
        symbol_id: str,
        max_depth: int = 3,
        edge_kinds: list[str] | None = None,
        include_contains: bool = False,
    ) -> ImpactReport:
        """Perform reverse-dependency blast radius analysis for a modified symbol.

        Finds all symbols directly or indirectly depending on `symbol_id`.
        By default, `contains` edges are excluded so parent containers are not
        falsely marked as dependents when an internal member changes.
        """
        try:
            resolved_id = self.resolve_symbol_id(symbol_id)
        except ValueError:
            resolved_id = None

        if not resolved_id or not self.graph.has_node(resolved_id):
            return ImpactReport(
                target_symbol_id=symbol_id,
                target_name=symbol_id,
                impact_score=0.0,
                risk_level="low",
            )

        target_name = self.graph.nodes[resolved_id].get("name", symbol_id)
        target_file = self.graph.nodes[resolved_id].get("file_path", "")

        # Invert graph to trace callers / inheritors / dependents
        # Edge A -> B means A depends on B (calls, inherits, uses).
        # A change in B impacts A.
        visited: dict[str, int] = {resolved_id: 0}
        paths: dict[str, list[str]] = {resolved_id: [resolved_id]}
        affected: list[AffectedSymbol] = []
        affected_files: set[str] = set()
        if target_file:
            affected_files.add(target_file)

        queue: deque[tuple[str, int]] = deque([(resolved_id, 0)])

        while queue:
            curr_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            # Look at predecessors: nodes that have an edge pointing TO curr_id
            for pred in self.graph.predecessors(curr_id):
                edge_dict = self.graph.get_edge_data(pred, curr_id) or {}
                for key, edge_data in edge_dict.items():
                    kind = edge_data.get("kind", key)

                    if not include_contains and kind == EdgeType.CONTAINS:
                        continue
                    if edge_kinds and kind not in edge_kinds:
                        continue

                    new_depth = depth + 1
                    if pred not in visited or visited[pred] > new_depth:
                        visited[pred] = new_depth
                        path = paths[curr_id] + [pred]
                        paths[pred] = path

                        pred_data = self.graph.nodes[pred]
                        p_file = pred_data.get("file_path", "")
                        if p_file:
                            affected_files.add(p_file)

                        affected.append(
                            AffectedSymbol(
                                symbol_id=pred,
                                name=pred_data.get("name", pred),
                                symbol_type=SymbolType(pred_data.get("symbol_type", "function")),
                                file_path=p_file,
                                depth=new_depth,
                                relationship=kind,
                                path=path,
                            )
                        )
                        queue.append((pred, new_depth))

        # Calculate impact score based on breadth, depth, and file spread
        total_deps = len(affected)
        file_count = len(affected_files)
        # Weighted score: count * file_spread * decay factor
        impact_score = round(total_deps * 1.5 + file_count * 2.0, 2)

        if impact_score > 30 or file_count > 5:
            risk_level = "critical"
        elif impact_score > 15 or file_count > 3:
            risk_level = "high"
        elif impact_score > 5 or file_count > 1:
            risk_level = "medium"
        else:
            risk_level = "low"

        return ImpactReport(
            target_symbol_id=resolved_id,
            target_name=target_name,
            impact_score=impact_score,
            risk_level=risk_level,
            affected_symbols=affected,
            affected_files=sorted(affected_files),
            total_dependents=total_deps,
        )

    def dependencies_of(
        self,
        symbol_id: str,
        max_depth: int = 3,
        edge_kinds: list[str] | None = None,
        include_contains: bool = True,
    ) -> list[str]:
        """Return list of symbol IDs that `symbol_id` depends on (forward traversal)."""
        try:
            resolved_id = self.resolve_symbol_id(symbol_id)
        except ValueError:
            resolved_id = None

        if not resolved_id or not self.graph.has_node(resolved_id):
            return []

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(resolved_id, 0)])

        while queue:
            curr_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            for succ in self.graph.successors(curr_id):
                edge_dict = self.graph.get_edge_data(curr_id, succ) or {}
                for key, edge_data in edge_dict.items():
                    kind = edge_data.get("kind", key)
                    if not include_contains and kind == EdgeType.CONTAINS:
                        continue
                    if edge_kinds and kind not in edge_kinds:
                        continue
                    if succ not in visited:
                        visited.add(succ)
                        queue.append((succ, depth + 1))

        return sorted(visited)

    def shortest_path(self, source_id: str, target_id: str) -> list[str] | None:
        """Find the shortest dependency path between two symbols."""
        s_id = self.resolve_symbol_id(source_id)
        t_id = self.resolve_symbol_id(target_id)
        if not s_id or not t_id:
            return None
        try:
            return nx.shortest_path(self.graph, source=s_id, target=t_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        return self.graph.number_of_edges()
