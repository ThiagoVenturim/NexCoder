"""Tests for CodeGraph representation and structural impact analysis."""

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
    assert graph.graph[form.id][btn.id]["kind"] == EdgeType.CONTAINS

    assert graph.graph.has_edge(btn.id, click_handler.id)
    assert graph.graph[btn.id][click_handler.id]["kind"] == EdgeType.UI_BINDS
