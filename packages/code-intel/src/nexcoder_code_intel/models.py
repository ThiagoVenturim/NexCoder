"""Symbol data models for code intelligence.

Represents syntactic and semantic code entities (functions, methods, classes,
interfaces, structs, properties, etc.) and their relationships across languages.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SymbolType(StrEnum):
    MODULE = "module"
    CLASS = "class"
    STRUCT = "struct"
    INTERFACE = "interface"
    ENUM = "enum"
    FUNCTION = "function"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    DESTRUCTOR = "destructor"
    PROPERTY = "property"
    VARIABLE = "variable"
    CONSTANT = "constant"
    TYPE_ALIAS = "type_alias"
    USES = "uses"
    DFM_OBJECT = "dfm_object"
    CODE_BLOCK = "code_block"


class SymbolLocation(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_path: str
    start_line: int  # 1-based
    end_line: int  # 1-based
    start_col: int = 0  # 0-based
    end_col: int = 0  # 0-based


class SymbolParameter(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    type_annotation: str | None = None
    default_value: str | None = None


class SymbolSignature(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw: str
    name: str
    parameters: list[SymbolParameter] = Field(default_factory=list)
    return_type: str | None = None
    modifiers: list[str] = Field(default_factory=list)


class RelationshipKind:
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    CALLS = "calls"
    USES = "uses"
    CONTAINS = "contains"
    BINDS_UI = "binds_ui"


class Symbol(BaseModel):
    """A first-class code symbol extracted from source code."""

    id: str
    name: str
    qualified_name: str
    symbol_type: SymbolType
    location: SymbolLocation
    language: str
    signature: SymbolSignature | None = None
    docstring: str | None = None
    body: str | None = None
    parent_id: str | None = None
    relationships: dict[str, list[str]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_relationship(self, kind: str, target: str) -> None:
        """Add a relationship from this symbol to a target symbol or unit."""
        if not target:
            return
        bucket = self.relationships.setdefault(kind, [])
        if target not in bucket:
            bucket.append(target)

    def summary(self) -> str:
        """Single-line human-readable summary of the symbol."""
        sig = self.signature.raw if self.signature else self.name
        return f"[{self.language}] {self.symbol_type.value} {self.qualified_name} - {sig}"
