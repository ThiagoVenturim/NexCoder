"""Tests for CodeGraph representation and structural impact analysis."""

import pytest
from faccoder_code_intel.graph import CodeGraph, EdgeType
from faccoder_code_intel.models import (
    RelationshipKind,
    Symbol,
    SymbolLocation,
    SymbolSignature,
    SymbolType,
)


def _make_sym(
    name: str,
    stype: SymbolType,
    file_path: str = "app.py",
    relationships: dict | None = None,
    parent_id: str | None = None,
) -> Symbol:
    loc = SymbolLocation(file_path=file_path, start_line=1, end_line=10)
    sig = SymbolSignature(raw=f"{stype.value} {name}", name=name)
    sym = Symbol(
        id=f"{file_path}::{name}",
        name=name,
        qualified_name=name,
        symbol_type=stype,
        location=loc,
        language="python",
        signature=sig,
        parent_id=parent_id,
        relationships=relationships or {},
    )
    return sym


def test_code_graph_construction_and_edges() -> None:
    # Service depends on Repository, Handler calls Service
    repo = _make_sym("UserRepository", SymbolType.CLASS, file_path="repo.py")
    service = _make_sym(
        "UserService",
        SymbolType.CLASS,
        file_path="service.py",
        relationships={RelationshipKind.CALLS: ["UserRepository"]},
    )
    handler = _make_sym(
        "UserHandler",
        SymbolType.CLASS,
        file_path="handler.py",
        relationships={RelationshipKind.CALLS: ["UserService"]},
    )

    graph = CodeGraph()
    graph.add_symbols([repo, service, handler])

    assert graph.node_count() == 3
    assert graph.edge_count() == 2

    # Handler -> Service -> Repo
    path = graph.shortest_path("UserHandler", "UserRepository")
    assert path == ["handler.py::UserHandler", "service.py::UserService", "repo.py::UserRepository"]

    # Dependencies of Handler
    deps = graph.dependencies_of("UserHandler", max_depth=2)
    assert "service.py::UserService" in deps
    assert "repo.py::UserRepository" in deps


def test_impact_analysis_blast_radius() -> None:
    # Modifying UserRepository impacts UserService and UserHandler
    repo = _make_sym("UserRepository", SymbolType.CLASS, file_path="repo.py")
    service = _make_sym(
        "UserService",
        SymbolType.CLASS,
        file_path="service.py",
        relationships={RelationshipKind.CALLS: ["UserRepository"]},
    )
    handler = _make_sym(
        "UserHandler",
        SymbolType.CLASS,
        file_path="handler.py",
        relationships={RelationshipKind.CALLS: ["UserService"]},
    )
    billing = _make_sym(
        "BillingService",
        SymbolType.CLASS,
        file_path="billing.py",
        relationships={RelationshipKind.CALLS: ["UserRepository"]},
    )

    graph = CodeGraph()
    graph.add_symbols([repo, service, handler, billing])

    report = graph.impact_analysis("UserRepository", max_depth=3)

    assert report.target_name == "UserRepository"
    assert report.total_dependents == 3  # UserService, UserHandler, BillingService
    affected_names = {s.name for s in report.affected_symbols}
    assert "UserService" in affected_names
    assert "UserHandler" in affected_names
    assert "BillingService" in affected_names

    # Check files impacted
    assert "repo.py" in report.affected_files
    assert "service.py" in report.affected_files
    assert "handler.py" in report.affected_files
    assert "billing.py" in report.affected_files
    assert report.impact_score > 0
    assert report.risk_level in {"medium", "high", "critical"}


def test_ui_binds_and_contains_edges() -> None:
    graph = CodeGraph()
    form = _make_sym("MainForm", SymbolType.CLASS, file_path="main.pas")
    btn = _make_sym("btnSubmit", SymbolType.DFM_OBJECT, file_path="main.dfm", parent_id=form.id)
    btn.add_relationship(RelationshipKind.BINDS_UI, "btnSubmitClick")
    click_handler = _make_sym("btnSubmitClick", SymbolType.METHOD, file_path="main.pas", parent_id=form.id)

    graph.add_symbols([form, btn, click_handler])

    assert graph.graph.has_edge(form.id, btn.id)
    edge_data = graph.graph.get_edge_data(form.id, btn.id)
    assert EdgeType.CONTAINS in edge_data

    assert graph.graph.has_edge(btn.id, click_handler.id)
    edge_data_btn = graph.graph.get_edge_data(btn.id, click_handler.id)
    assert EdgeType.UI_BINDS in edge_data_btn


def test_multidigraph_multiple_edge_types() -> None:
    """Ensure MultiDiGraph permits multiple distinct relationships between the same two symbols."""
    graph = CodeGraph()
    source = _make_sym("OrderController", SymbolType.CLASS, file_path="order.py")
    target = _make_sym("PaymentGateway", SymbolType.CLASS, file_path="payment.py")
    graph.add_symbols([source, target])

    # Add both CALLS and USES relationships between OrderController and PaymentGateway
    graph.add_edge(source.id, target.id, EdgeType.CALLS)
    graph.add_edge(source.id, target.id, EdgeType.USES)

    edges = graph.graph.get_edge_data(source.id, target.id)
    assert len(edges) == 2
    assert EdgeType.CALLS in edges
    assert EdgeType.USES in edges
    assert edges[EdgeType.CALLS]["kind"] == EdgeType.CALLS
    assert edges[EdgeType.USES]["kind"] == EdgeType.USES


def test_resolve_symbol_id_ambiguity() -> None:
    """Ensure ambiguous symbols without file qualification raise ValueError instead of silent wrong match."""
    graph = CodeGraph()
    user_model = _make_sym("User", SymbolType.CLASS, file_path="models/user.py")
    user_schema = _make_sym("User", SymbolType.CLASS, file_path="schemas/user.py")
    graph.add_symbols([user_model, user_schema])

    # Unqualified ambiguous name must raise ValueError
    with pytest.raises(ValueError, match="Ambiguous symbol name 'User' matches 2 symbols"):
        graph.resolve_symbol_id("User")

    # Qualified by context_file resolves unambiguously
    assert graph.resolve_symbol_id("User", context_file="models/user.py") == user_model.id
    assert graph.resolve_symbol_id("User", context_file="schemas/user.py") == user_schema.id


def test_impact_analysis_excludes_contains_by_default() -> None:
    """Ensure contains edges are excluded by default in blast radius propagation."""
    graph = CodeGraph()
    parent_cls = _make_sym("OrderService", SymbolType.CLASS, file_path="order.py")
    child_method = _make_sym("checkout", SymbolType.METHOD, file_path="order.py", parent_id=parent_cls.id)
    caller_fn = _make_sym(
        "run_api",
        SymbolType.FUNCTION,
        file_path="api.py",
        relationships={RelationshipKind.CALLS: ["checkout"]},
    )
    graph.add_symbols([parent_cls, child_method, caller_fn])

    # Blast radius on child_method with default include_contains=False
    report_default = graph.impact_analysis("checkout", max_depth=2, include_contains=False)
    affected_ids_default = {s.symbol_id for s in report_default.affected_symbols}
    assert caller_fn.id in affected_ids_default
    # parent OrderService should NOT be in affected symbols via contains
    assert parent_cls.id not in affected_ids_default

    # When explicitly include_contains=True, parent container is also traced
    report_with_contains = graph.impact_analysis("checkout", max_depth=2, include_contains=True)
    affected_ids_contains = {s.symbol_id for s in report_with_contains.affected_symbols}
    assert caller_fn.id in affected_ids_contains
    assert parent_cls.id in affected_ids_contains
