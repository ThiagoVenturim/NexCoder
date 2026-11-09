"""Code graph and GraphRAG foundation."""

from nexcoder_code_intel.graph.code_graph import AffectedSymbol, CodeGraph, EdgeType, ImpactReport
from nexcoder_code_intel.graph.communities import Community, CommunityDetector, GraphRAGContext

__all__ = [
    "AffectedSymbol",
    "CodeGraph",
    "Community",
    "CommunityDetector",
    "EdgeType",
    "GraphRAGContext",
    "ImpactReport",
]
