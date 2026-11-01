"""Tests for GraphRAG community detection and hierarchical summaries."""

from faccoder_code_intel.graph import CodeGraph, CommunityDetector, EdgeType, GraphRAGContext
from faccoder_code_intel.models import Symbol, SymbolLocation, SymbolType


def _sym(name: str, file_path: str = "app.py") -> Symbol:
    loc = SymbolLocation(file_path=file_path, start_line=1, end_line=10)
    return Symbol(
        id=f"{file_path}::{name}",
        name=name,
        qualified_name=name,
        symbol_type=SymbolType.CLASS,
        location=loc,
        language="python",
    )


def test_community_detection_and_summaries() -> None:
    graph = CodeGraph()

    # Subsystem 1: Billing Cluster
    invoice = _sym("InvoiceService", "billing.py")
    payment = _sym("PaymentGateway", "billing.py")
    tax = _sym("TaxCalculator", "tax.py")

    # Subsystem 2: Auth Cluster
    user = _sym("UserService", "auth.py")
    token = _sym("TokenManager", "auth.py")
    perm = _sym("PermissionGuard", "auth.py")

    graph.add_symbols([invoice, payment, tax, user, token, perm])

    # Connect internal billing edges
    graph.add_edge(invoice.id, payment.id, EdgeType.CALLS)
    graph.add_edge(invoice.id, tax.id, EdgeType.CALLS)
    graph.add_edge(payment.id, tax.id, EdgeType.CALLS)

    # Connect internal auth edges
    graph.add_edge(user.id, token.id, EdgeType.CALLS)
    graph.add_edge(user.id, perm.id, EdgeType.CALLS)
    graph.add_edge(token.id, perm.id, EdgeType.CALLS)

    # Weak bridge between billing and auth
    graph.add_edge(invoice.id, user.id, EdgeType.CALLS)

    detector = CommunityDetector(seed=42)
    communities = detector.detect_communities(graph, resolutions=[1.0])

    assert len(communities) >= 2
    for comm in communities:
        assert len(comm.symbols) > 0
        assert comm.title is not None
        assert comm.summary is not None
        assert len(comm.key_entities) > 0
        assert comm.internal_edges >= 0

    # Test GraphRAG context assembly
    rag = GraphRAGContext(code_graph=graph, communities=communities)
    context = rag.assemble_query_context([invoice.id, user.id])

    assert len(context["symbols"]) == 2
    assert len(context["communities"]) >= 1


def test_assemble_query_context_ambiguous_symbol() -> None:
    graph = CodeGraph()

    user1 = _sym("UserService", "auth1.py")
    user2 = _sym("UserService", "auth2.py")
    billing = _sym("BillingService", "billing.py")

    graph.add_symbols([user1, user2, billing])
    detector = CommunityDetector(seed=42)
    communities = detector.detect_communities(graph, resolutions=[1.0])

    rag = GraphRAGContext(code_graph=graph, communities=communities)
    # Query with ambiguous short name "UserService" alongside concrete ID billing.id
    context = rag.assemble_query_context(["UserService", billing.id])

    # billing.id should resolve properly
    assert len(context["symbols"]) == 1
    assert context["symbols"][0]["id"] == billing.id

    # Ambiguous symbol should be reported without breaking context assembly
    assert "ambiguous_symbols" in context
    assert len(context["ambiguous_symbols"]) == 1
    assert context["ambiguous_symbols"][0]["id"] == "UserService"
    assert "Ambiguous symbol name" in context["ambiguous_symbols"][0]["reason"]
