"""Tests for symbol data models."""

from faccoder_code_intel.models import (
    RelationshipKind,
    Symbol,
    SymbolLocation,
    SymbolParameter,
    SymbolSignature,
    SymbolType,
)


def test_symbol_creation_and_serialization() -> None:
    loc = SymbolLocation(file_path="src/app.py", start_line=10, end_line=25, start_col=0, end_col=12)
    sig = SymbolSignature(
        raw="def calculate(total: float, discount: float = 0.0) -> float",
        name="calculate",
        parameters=[
            SymbolParameter(name="total", type_annotation="float"),
            SymbolParameter(name="discount", type_annotation="float", default_value="0.0"),
        ],
        return_type="float",
    )
    sym = Symbol(
        id="src/app.py::calculate:10",
        name="calculate",
        qualified_name="calculate",
        symbol_type=SymbolType.FUNCTION,
        location=loc,
        language="python",
        signature=sig,
        docstring="Compute final total after discount.",
        body="def calculate(total: float, discount: float = 0.0) -> float:\n    return total - discount",
    )

    sym.add_relationship(RelationshipKind.CALLS, "validate_input")
    sym.add_relationship(RelationshipKind.CALLS, "validate_input")  # duplicate check

    assert sym.name == "calculate"
    assert sym.symbol_type == SymbolType.FUNCTION
    assert len(sym.relationships[RelationshipKind.CALLS]) == 1
    assert sym.relationships[RelationshipKind.CALLS][0] == "validate_input"

    summary = sym.summary()
    assert "[python] function calculate" in summary

    dumped = sym.model_dump()
    assert dumped["id"] == "src/app.py::calculate:10"
    assert dumped["location"]["start_line"] == 10
