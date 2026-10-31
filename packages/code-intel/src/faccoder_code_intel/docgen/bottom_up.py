"""Bottom-up documentation generator.

Synthesizes documentation from leaf functions and methods up to classes,
modules, and system architecture.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from faccoder_code_intel.graph.communities import Community
from faccoder_code_intel.models import Symbol, SymbolType

logger = logging.getLogger(__name__)


class DocLevel(StrEnum):
    ROUTINE = "routine"
    CLASS = "class"
    MODULE = "module"
    SYSTEM = "system"


class DocNode(BaseModel):
    """A synthesized documentation unit at a specific architectural level."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    level: DocLevel
    file_path: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    markdown: str


class BottomUpDocEngine:
    """Hierarchical documentation engine rolling up context from code to architecture."""

    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm

    def _synthesize_with_llm(self, prompt: str, default: str) -> str:
        """Query LLM for documentation synthesis, falling back to default template."""
        if self.llm is None:
            return default
        try:
            resp = self.llm.invoke(prompt)
            content = resp.content if hasattr(resp, "content") else str(resp)
            cleaned = content.strip()
            return cleaned if cleaned else default
        except Exception as exc:
            logger.debug("Docgen LLM invocation failed, using default: %s", exc)
            return default

    def document_routine(self, symbol: Symbol) -> DocNode:
        """Synthesize Level 0 documentation for a function or method."""
        params_desc: list[str] = []
        if symbol.signature:
            for p in symbol.signature.parameters:
                p_type = f": {p.type_annotation}" if p.type_annotation else ""
                params_desc.append(f"`{p.name}`{p_type}")

        ret_type = symbol.signature.return_type if symbol.signature else None
        ret_desc = f"Returns `{ret_type}`." if ret_type else "No return value."
        existing_doc = f"\n\n> {symbol.docstring}" if symbol.docstring else ""

        summary = symbol.docstring or f"Executes {symbol.name} operation."
        if self.llm is not None:
            prompt = (
                f"Summarize this code routine in one concise sentence:\n"
                f"Name: {symbol.name}\n"
                f"Signature: {symbol.signature.raw if symbol.signature else symbol.name}\n"
                f"Existing doc: {symbol.docstring or 'None'}"
            )
            summary = self._synthesize_with_llm(prompt, summary)

        md_lines = [
            f"### `{symbol.qualified_name}`",
            f"**Type**: {symbol.symbol_type.value}",
            f"**Signature**: `{symbol.signature.raw if symbol.signature else symbol.name}`",
            "",
            summary + existing_doc,
            "",
            "**Parameters**:" if params_desc else "",
            *[f"- {p}" for p in params_desc],
            "",
            f"**Output**: {ret_desc}",
        ]
        markdown = "\n".join(line for line in md_lines if line is not None).strip()

        return DocNode(
            id=symbol.id,
            name=symbol.name,
            level=DocLevel.ROUTINE,
            file_path=symbol.location.file_path,
            summary=summary,
            details={
                "qualified_name": symbol.qualified_name,
                "parameters": [p.model_dump() for p in symbol.signature.parameters] if symbol.signature else [],
                "return_type": ret_type,
            },
            markdown=markdown,
        )

    def document_class(self, class_symbol: Symbol, member_docs: list[DocNode]) -> DocNode:
        """Synthesize Level 1 documentation rolling up child member routines."""
        summary = (
            class_symbol.docstring
            or f"Encapsulates {class_symbol.name} state, data contracts, and operational routines."
        )
        if self.llm is not None:
            prompt = (
                f"Summarize this class in one concise sentence based on its member routines:\n"
                f"Class: {class_symbol.name}\n"
                f"Members: {[m.name for m in member_docs]}"
            )
            summary = self._synthesize_with_llm(prompt, summary)

        md_lines = [
            f"## Class `{class_symbol.name}`",
            f"**File**: `{class_symbol.location.file_path}`",
            "",
            summary,
            "",
            "### Member Routines:",
            *[f"- **`{m.name}`**: {m.summary}" for m in member_docs],
        ]
        markdown = "\n".join(md_lines)

        return DocNode(
            id=class_symbol.id,
            name=class_symbol.name,
            level=DocLevel.CLASS,
            file_path=class_symbol.location.file_path,
            summary=summary,
            details={
                "members_count": len(member_docs),
                "member_ids": [m.id for m in member_docs],
            },
            markdown=markdown,
        )

    def document_module(
        self,
        module_name: str,
        file_path: str,
        child_docs: list[DocNode],
        imports: list[str] | None = None,
    ) -> DocNode:
        """Synthesize Level 2 documentation rolling up classes and standalone routines."""
        classes = [d for d in child_docs if d.level == DocLevel.CLASS]
        routines = [d for d in child_docs if d.level == DocLevel.ROUTINE]

        summary = (
            f"Module `{module_name}` provides {len(classes)} class definition(s) "
            f"and {len(routines)} standalone routine(s)."
        )
        if self.llm is not None:
            prompt = (
                f"Summarize this module in one concise sentence:\n"
                f"Module: {module_name}\n"
                f"Classes: {[c.name for c in classes]}\n"
                f"Routines: {[r.name for r in routines]}"
            )
            summary = self._synthesize_with_llm(prompt, summary)

        md_lines = [
            f"# Module `{module_name}`",
            f"**Path**: `{file_path}`",
            "",
            summary,
            "",
            "### Dependencies:" if imports else "",
            *[f"- `{imp}`" for imp in (imports or [])],
            "",
            "### Exported Entities:",
            *[f"#### {c.name}\n{c.summary}" for c in classes],
            *[f"- `{r.name}`: {r.summary}" for r in routines],
        ]
        markdown = "\n".join(line for line in md_lines if line is not None).strip()

        return DocNode(
            id=f"{file_path}::module",
            name=module_name,
            level=DocLevel.MODULE,
            file_path=file_path,
            summary=summary,
            details={
                "classes_count": len(classes),
                "routines_count": len(routines),
                "imports": imports or [],
            },
            markdown=markdown,
        )

    def document_system(
        self,
        module_docs: list[DocNode],
        communities: list[Community] | None = None,
    ) -> DocNode:
        """Synthesize Level 3 architecture overview rolling up all modules and GraphRAG clusters."""
        summary = (
            f"System architecture comprises {len(module_docs)} module(s) "
            f"organized across {len(communities or [])} subsystem cluster(s)."
        )
        if self.llm is not None:
            prompt = (
                f"Summarize the system architecture in one concise sentence:\n"
                f"Modules: {[m.name for m in module_docs]}\n"
                f"Subsystems: {[c.title for c in (communities or [])]}"
            )
            summary = self._synthesize_with_llm(prompt, summary)

        md_lines = [
            "# Architecture Overview",
            "",
            summary,
            "",
            "## Subsystem Clusters:" if communities else "",
            *[f"### {c.title}\n{c.summary}\n" for c in (communities or [])],
            "## Module Index:",
            *[f"- **`{m.name}`** (`{m.file_path}`): {m.summary}" for m in module_docs],
        ]
        markdown = "\n".join(line for line in md_lines if line is not None).strip()

        return DocNode(
            id="system::architecture",
            name="Architecture Overview",
            level=DocLevel.SYSTEM,
            file_path="",
            summary=summary,
            details={
                "modules_count": len(module_docs),
                "communities_count": len(communities or []),
            },
            markdown=markdown,
        )

    def generate_tree(
        self,
        symbols: list[Symbol],
        communities: list[Community] | None = None,
    ) -> dict[str, DocNode]:
        """Produce the full bottom-up documentation tree from a collection of symbols."""
        docs: dict[str, DocNode] = {}

        # 1. Level 0: Document routines
        routines = [
            s
            for s in symbols
            if s.symbol_type
            in {
                SymbolType.FUNCTION,
                SymbolType.METHOD,
                SymbolType.CONSTRUCTOR,
                SymbolType.DESTRUCTOR,
            }
        ]
        for r in routines:
            docs[r.id] = self.document_routine(r)

        # 2. Level 1: Document classes with exact member matching
        classes = [s for s in symbols if s.symbol_type in {SymbolType.CLASS, SymbolType.STRUCT, SymbolType.INTERFACE}]
        class_member_ids: set[str] = set()

        for c in classes:
            members: list[DocNode] = []
            for r in routines:
                is_member = False
                if r.parent_id == c.id:
                    is_member = True
                elif r.location.file_path == c.location.file_path:
                    prefix_name = f"{c.name}."
                    prefix_qname = f"{c.qualified_name}."
                    if r.qualified_name.startswith(prefix_name) or r.qualified_name.startswith(prefix_qname):
                        is_member = True

                if is_member:
                    members.append(docs[r.id])
                    class_member_ids.add(r.id)

            docs[c.id] = self.document_class(c, members)

        # 3. Level 2: Group by module / file
        by_file: dict[str, list[DocNode]] = {}
        for c in classes:
            by_file.setdefault(c.location.file_path, []).append(docs[c.id])

        # Standalone routines: Any routine not belonging to a class belongs to module level
        # (retains dotted functions that are not class methods)
        for r in routines:
            if r.id not in class_member_ids:
                by_file.setdefault(r.location.file_path, []).append(docs[r.id])

        module_docs: list[DocNode] = []
        for file_path, file_child_docs in by_file.items():
            mod_name = file_path.split("/")[-1].split("\\")[-1].split(".")[0]
            # Gather imports if any
            module_sym = next(
                (s for s in symbols if s.location.file_path == file_path and s.symbol_type == SymbolType.MODULE), None
            )
            imports = module_sym.relationships.get("uses", []) if module_sym else []

            mod_doc = self.document_module(mod_name, file_path, file_child_docs, imports=imports)
            docs[mod_doc.id] = mod_doc
            module_docs.append(mod_doc)

        # 4. Level 3: System overview
        system_doc = self.document_system(module_docs, communities=communities)
        docs[system_doc.id] = system_doc

        return docs
