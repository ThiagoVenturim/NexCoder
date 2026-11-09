"""faccoder_code_intel - Code intelligence for faccoder.

AST parsers, symbol models, code graph, GraphRAG communities, HyDE retrieval, and bottom-up docgen.
"""

from faccoder_code_intel.chunking import CodeChunk, SymbolChunker
from faccoder_code_intel.docgen import BottomUpDocEngine, DocLevel, DocNode
from faccoder_code_intel.graph import (
    AffectedSymbol,
    CodeGraph,
    Community,
    CommunityDetector,
    EdgeType,
    GraphRAGContext,
    ImpactReport,
)
from faccoder_code_intel.models import (
    RelationshipKind,
    Symbol,
    SymbolLocation,
    SymbolParameter,
    SymbolSignature,
    SymbolType,
)
from faccoder_code_intel.parsers import (
    BaseParser,
    DelphiParser,
    TreeSitterParser,
    get_parser_for_file,
    get_parser_for_language,
    parse_file,
)
from faccoder_code_intel.query_expansion import HyDEGenerator, QueryRewriter, RewrittenQuery
from faccoder_code_intel.retrieval import CodeSearchIndex

__all__ = [
    "AffectedSymbol",
    "BaseParser",
    "BottomUpDocEngine",
    "CodeChunk",
    "CodeGraph",
    "CodeSearchIndex",
    "Community",
    "CommunityDetector",
    "DelphiParser",
    "DocLevel",
    "DocNode",
    "EdgeType",
    "GraphRAGContext",
    "HyDEGenerator",
    "ImpactReport",
    "QueryRewriter",
    "RelationshipKind",
    "RewrittenQuery",
    "Symbol",
    "SymbolChunker",
    "SymbolLocation",
    "SymbolParameter",
    "SymbolSignature",
    "SymbolType",
    "TreeSitterParser",
    "get_parser_for_file",
    "get_parser_for_language",
    "parse_file",
]
