"""GraphRAG foundation: community detection, clustering, and hierarchical summaries over code graphs."""

from __future__ import annotations

import logging
from typing import Any

import networkx as nx
from networkx.algorithms.community import louvain_communities
from pydantic import BaseModel, ConfigDict, Field

from nexcoder_code_intel.graph.code_graph import CodeGraph

logger = logging.getLogger(__name__)


class Community(BaseModel):
    """An architectural cluster of code symbols discovered via graph modularity."""

    model_config = ConfigDict(frozen=True)

    id: int
    level: int = 0
    symbols: list[str] = Field(default_factory=list)
    title: str
    summary: str
    key_entities: list[str] = Field(default_factory=list)
    internal_edges: int = 0
    external_edges: int = 0
    files: list[str] = Field(default_factory=list)


class CommunityDetector:
    """Discovers modular symbol communities and computes architectural summaries."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed

    def detect_communities(
        self,
        code_graph: CodeGraph,
        resolutions: list[float] | None = None,
    ) -> list[Community]:
        """Run multi-resolution Louvain community detection over the code graph."""
        res_list = resolutions or [1.0]
        g = code_graph.graph
        if g.number_of_nodes() == 0:
            return []

        # Undirected projection with weights for clustering
        ug = nx.Graph(g.to_undirected())

        all_communities: list[Community] = []
        comm_counter = 1

        for level, res in enumerate(res_list):
            try:
                clusters = louvain_communities(ug, resolution=res, seed=self.seed)
            except Exception:
                # Fallback to connected components if modularity fails
                clusters = list(nx.connected_components(ug))

            for cluster in clusters:
                if not cluster:
                    continue
                member_ids = sorted(cluster)

                # Compute degrees within cluster to find key central symbols
                sub = ug.subgraph(member_ids)
                degrees = dict(sub.degree())
                sorted_by_degree = sorted(degrees.items(), key=lambda x: x[1], reverse=True)
                key_entities = [code_graph.graph.nodes[n].get("name", n) for n, _ in sorted_by_degree[:5]]

                # Gather files
                files = sorted(
                    {
                        code_graph.graph.nodes[n].get("file_path", "")
                        for n in member_ids
                        if code_graph.graph.nodes[n].get("file_path")
                    }
                )

                # Count internal and external edges
                internal_edges = sub.number_of_edges()
                total_incident = sum(dict(ug.degree(member_ids)).values())
                external_edges = total_incident - (2 * internal_edges)

                # Generate synthesis summary
                title, summary = self._summarize_community(code_graph, member_ids, key_entities, files)

                all_communities.append(
                    Community(
                        id=comm_counter,
                        level=level,
                        symbols=member_ids,
                        title=title,
                        summary=summary,
                        key_entities=key_entities,
                        internal_edges=internal_edges,
                        external_edges=max(0, external_edges),
                        files=files,
                    )
                )
                comm_counter += 1

        return all_communities

    def _summarize_community(
        self,
        code_graph: CodeGraph,
        members: list[str],
        key_entities: list[str],
        files: list[str],
    ) -> tuple[str, str]:
        """Synthesize a structured architectural summary for a group of symbols."""
        symbol_types: dict[str, int] = {}
        for m in members:
            st = code_graph.graph.nodes[m].get("symbol_type", "symbol")
            symbol_types[st] = symbol_types.get(st, 0) + 1

        types_desc = ", ".join(f"{count} {st}(s)" for st, count in sorted(symbol_types.items()))
        lead_name = key_entities[0] if key_entities else "Component"

        title = f"{lead_name} Subsystem" if len(key_entities) <= 1 else f"{lead_name} & Related Services"

        lines = [
            f"Community centered around {', '.join(key_entities[:3])}.",
            f"Comprises {len(members)} symbols ({types_desc}) across {len(files)} file(s): {', '.join(files[:3])}.",
            f"Primary responsibilities: {lead_name} core orchestration and data transformation.",
        ]
        return title, "\n".join(lines)


class GraphRAGContext:
    """Assembles community and symbol context for multi-hop architectural queries."""

    def __init__(self, code_graph: CodeGraph, communities: list[Community]) -> None:
        self.code_graph = code_graph
        self.communities = communities
        self._symbol_to_community: dict[str, Community] = {}
        for c in communities:
            for s in c.symbols:
                self._symbol_to_community[s] = c

    def get_community_for_symbol(self, symbol_id: str) -> Community | None:
        return self._symbol_to_community.get(symbol_id)

    def assemble_query_context(self, symbol_ids: list[str]) -> dict[str, Any]:
        """Assemble structured context for a set of relevant symbols including their architectural clusters."""
        relevant_communities: dict[int, Community] = {}
        symbol_details: list[dict[str, Any]] = []
        ambiguous_symbols: list[dict[str, str]] = []

        for sid in symbol_ids:
            try:
                resolved = self.code_graph.resolve_symbol_id(sid)
            except ValueError as exc:
                logger.warning("Ambiguous symbol query '%s': %s", sid, exc)
                ambiguous_symbols.append({"id": sid, "reason": str(exc)})
                continue

            if not resolved or not self.code_graph.graph.has_node(resolved):
                continue

            node_data = self.code_graph.graph.nodes[resolved]
            comm = self.get_community_for_symbol(resolved)
            if comm:
                relevant_communities[comm.id] = comm

            symbol_details.append(
                {
                    "id": resolved,
                    "name": node_data.get("name"),
                    "type": node_data.get("symbol_type"),
                    "file_path": node_data.get("file_path"),
                    "signature": node_data.get("signature"),
                    "docstring": node_data.get("docstring"),
                    "community_title": comm.title if comm else None,
                }
            )

        context: dict[str, Any] = {
            "communities": [c.model_dump() for c in relevant_communities.values()],
            "symbols": symbol_details,
        }
        if ambiguous_symbols:
            context["ambiguous_symbols"] = ambiguous_symbols
        return context
