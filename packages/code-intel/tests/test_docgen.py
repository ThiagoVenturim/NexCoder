"""Tests for BottomUpDocEngine hierarchical documentation generation."""

from faccoder_code_intel.docgen import BottomUpDocEngine, DocLevel
from faccoder_code_intel.graph import Community
from faccoder_code_intel.models import (
    Symbol,
    SymbolLocation,
    SymbolParameter,
    SymbolSignature,
    SymbolType,
)


def test_bottom_up_doc_generation() -> None:
    # 1. Level 0 Routine
    fn_loc = SymbolLocation(file_path="src/calc.py", start_line=10, end_line=15)
    fn_sig = SymbolSignature(
        raw="def add(a: int, b: int) -> int",
        name="add",
        parameters=[
            SymbolParameter(name="a", type_annotation="int"),
            SymbolParameter(name="b", type_annotation="int"),
        ],
        return_type="int",
    )
    fn_sym = Symbol(
        id="src/calc.py::add:10",
        name="add",
        qualified_name="Calculator.add",
        symbol_type=SymbolType.METHOD,
        location=fn_loc,
        language="python",
        signature=fn_sig,
        docstring="Adds two integers.",
        parent_id="src/calc.py::Calculator:1",
    )

    # Level 1 Class
    cls_loc = SymbolLocation(file_path="src/calc.py", start_line=1, end_line=20)
    cls_sym = Symbol(
        id="src/calc.py::Calculator:1",
        name="Calculator",
        qualified_name="Calculator",
        symbol_type=SymbolType.CLASS,
        location=cls_loc,
        language="python",
        docstring="Mathematical calculator service.",
    )

    # Level 2 Module
    mod_sym = Symbol(
        id="src/calc.py::module",
        name="calc",
        qualified_name="calc",
        symbol_type=SymbolType.MODULE,
        location=cls_loc,
        language="python",
        relationships={"uses": ["math", "sys"]},
    )

    engine = BottomUpDocEngine()

    # Community Level 3
    comm = Community(
        id=1,
        title="Math Subsystem",
        summary="Handles numerical computations.",
        symbols=[fn_sym.id, cls_sym.id],
    )

    tree = engine.generate_tree([mod_sym, cls_sym, fn_sym], communities=[comm])

    assert fn_sym.id in tree
    routine_node = tree[fn_sym.id]
    assert routine_node.level == DocLevel.ROUTINE
    assert "Adds two integers." in routine_node.markdown
    assert "`a`: int" in routine_node.markdown

    assert cls_sym.id in tree
    cls_node = tree[cls_sym.id]
    assert cls_node.level == DocLevel.CLASS
    assert "Calculator" in cls_node.markdown
    assert "add" in cls_node.markdown

    assert "src/calc.py::module" in tree
    mod_node = tree["src/calc.py::module"]
    assert mod_node.level == DocLevel.MODULE
    assert "Calculator" in mod_node.markdown

    assert "system::architecture" in tree
    sys_node = tree["system::architecture"]
    assert sys_node.level == DocLevel.SYSTEM
    assert "Math Subsystem" in sys_node.markdown
