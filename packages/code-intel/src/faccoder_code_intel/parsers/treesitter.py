"""Tree-sitter based symbol parser for common languages.

Supports: Python, Go, JavaScript, TypeScript, Java, C, C++, and Rust.
Extracts functions, methods, classes, interfaces, structs, signatures,
docstrings, and inheritance relationships.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import tree_sitter_language_pack as tslp
from tree_sitter import Node

from faccoder_code_intel.models import (
    RelationshipKind,
    Symbol,
    SymbolLocation,
    SymbolParameter,
    SymbolSignature,
    SymbolType,
)
from faccoder_code_intel.parsers.base import BaseParser

logger = logging.getLogger(__name__)

EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".go": "go",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".mts": "typescript",
    ".cts": "typescript",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".rs": "rust",
}

CANONICAL_LANG: dict[str, str] = {
    "python": "python",
    "go": "go",
    "javascript": "javascript",
    "typescript": "typescript",
    "tsx": "typescript",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "rust": "rust",
}


class TreeSitterParser(BaseParser):
    """AST-based symbol parser utilizing Tree-sitter grammars."""

    def __init__(self, languages: list[str] | None = None):
        self._parsers: dict[str, Any] = {}
        target_langs = languages or list(set(EXT_TO_LANG.values()))
        for lang in target_langs:
            try:
                self._parsers[lang] = tslp.get_parser(lang)
            except Exception as e:
                logger.warning("Could not load tree-sitter parser for %s: %s", lang, e)

    @property
    def supported_languages(self) -> list[str]:
        return sorted({CANONICAL_LANG.get(k, k) for k in self._parsers})

    @property
    def supported_extensions(self) -> list[str]:
        return [ext for ext, lang in EXT_TO_LANG.items() if lang in self._parsers]

    def _get_lang_for_path(self, file_path: str) -> str | None:
        ext = Path(file_path).suffix.lower()
        return EXT_TO_LANG.get(ext)

    def parse(self, content: str, file_path: str = "") -> list[Symbol]:
        lang_key = self._get_lang_for_path(file_path) or "python"
        parser = self._parsers.get(lang_key)
        if not parser:
            return []

        bytes_content = content.encode("utf-8", errors="replace")
        tree = parser.parse(bytes_content)
        canonical = CANONICAL_LANG.get(lang_key, lang_key)

        extractor = _AstExtractor(bytes_content, file_path, canonical, self)
        return extractor.extract(tree.root_node)


class _AstExtractor:
    def __init__(self, content: bytes, file_path: str, language: str, parser: BaseParser):
        self.content = content
        self.file_path = file_path
        self.language = language
        self.parser = parser
        self.symbols: list[Symbol] = []

    def text(self, node: Node | None) -> str:
        if not node:
            return ""
        return self.content[node.start_byte : node.end_byte].decode("utf-8", errors="replace").strip()

    def location(self, node: Node) -> SymbolLocation:
        return SymbolLocation(
            file_path=self.file_path,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            start_col=node.start_point.column,
            end_col=node.end_point.column,
        )

    def extract(self, root: Node) -> list[Symbol]:
        self._visit(root, parent_prefix="", parent_id=None)
        return self.symbols

    def _extract_leading_comment(self, node: Node) -> str | None:
        comments: list[str] = []
        prev = node.prev_named_sibling
        while prev and prev.type in {"comment", "line_comment", "block_comment"}:
            c_text = self.text(prev)
            for line in c_text.splitlines():
                clean = line.strip()
                for prefix in ("/*", "//", "#", ";"):
                    if clean.startswith(prefix):
                        clean = clean[len(prefix) :].strip()
                if clean.endswith("*/"):
                    clean = clean[:-2].strip()
                if clean:
                    comments.insert(0, clean)
            prev = prev.prev_named_sibling
        return "\n".join(comments) if comments else None

    def _visit(self, node: Node, parent_prefix: str, parent_id: str | None) -> None:
        actual_node = node
        if actual_node.type in {"export_statement", "decorated_definition"}:
            for child in actual_node.named_children:
                if child.type not in {"decorator", "export"}:
                    self._visit_named_construct(child, parent_prefix, parent_id, container_node=actual_node)
            return

        self._visit_named_construct(actual_node, parent_prefix, parent_id)

    def _visit_named_construct(
        self,
        node: Node,
        parent_prefix: str,
        parent_id: str | None,
        container_node: Node | None = None,
    ) -> None:
        outer_node = container_node or node

        if self.language == "python":
            self._handle_python(node, outer_node, parent_prefix, parent_id)
        elif self.language in {"javascript", "typescript"}:
            self._handle_javascript(node, outer_node, parent_prefix, parent_id)
        elif self.language == "go":
            self._handle_go(node, outer_node, parent_prefix, parent_id)
        elif self.language == "java":
            self._handle_java(node, outer_node, parent_prefix, parent_id)
        elif self.language in {"c", "cpp"}:
            self._handle_cpp(node, outer_node, parent_prefix, parent_id)
        elif self.language == "rust":
            self._handle_rust(node, outer_node, parent_prefix, parent_id)
        else:
            for child in node.named_children:
                self._visit(child, parent_prefix, parent_id)

    # ----------------- Python -----------------
    def _extract_python_docstring(self, body_node: Node | None) -> str | None:
        if not body_node or body_node.named_child_count == 0:
            return None
        first_stmt = body_node.named_children[0]
        str_node = None
        if first_stmt.type == "string":
            str_node = first_stmt
        elif first_stmt.type == "expression_statement":
            str_node = first_stmt.named_children[0] if first_stmt.named_children else None

        if str_node and str_node.type == "string":
            content_child = next((c for c in str_node.named_children if c.type == "string_content"), None)
            if content_child:
                return self.text(content_child)
            return self.text(str_node).strip("\"' \n\t")
        return None

    def _handle_python(self, node: Node, outer_node: Node, parent_prefix: str, parent_id: str | None) -> None:
        if node.type in {"function_definition", "async_function_definition"}:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            is_async = any(c.type == "async" for c in node.children) or node.type == "async_function_definition"
            name = self.text(name_node)
            qname = f"{parent_prefix}{name}" if parent_prefix else name
            stype = SymbolType.METHOD if parent_prefix else SymbolType.FUNCTION

            body_node = node.child_by_field_name("body")
            docstring = self._extract_python_docstring(body_node)

            params_node = node.child_by_field_name("parameters")
            ret_node = node.child_by_field_name("return_type")
            raw_sig = f"{'async ' if is_async else ''}def {name}{self.text(params_node)}"
            if ret_node:
                raw_sig += f" -> {self.text(ret_node)}"

            sym_id = self.parser.make_symbol_id(self.file_path, qname, outer_node.start_point.row + 1)
            sym = Symbol(
                id=sym_id,
                name=name,
                qualified_name=qname,
                symbol_type=stype,
                location=self.location(outer_node),
                language="python",
                signature=SymbolSignature(
                    raw=raw_sig,
                    name=name,
                    parameters=self._parse_parameters(params_node),
                    return_type=self.text(ret_node) if ret_node else None,
                    modifiers=["async"] if is_async else [],
                ),
                docstring=docstring,
                body=self.text(outer_node),
                parent_id=parent_id,
            )
            self.symbols.append(sym)

        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = self.text(name_node)
            qname = f"{parent_prefix}{name}" if parent_prefix else name
            super_node = node.child_by_field_name("superclasses")

            body_node = node.child_by_field_name("body")
            docstring = self._extract_python_docstring(body_node)

            raw_sig = f"class {name}{self.text(super_node)}:"
            sym_id = self.parser.make_symbol_id(self.file_path, qname, outer_node.start_point.row + 1)
            sym = Symbol(
                id=sym_id,
                name=name,
                qualified_name=qname,
                symbol_type=SymbolType.CLASS,
                location=self.location(outer_node),
                language="python",
                signature=SymbolSignature(raw=raw_sig, name=name),
                docstring=docstring,
                body=self.text(outer_node),
                parent_id=parent_id,
            )
            if super_node:
                for base_node in super_node.named_children:
                    base_name = self.text(base_node)
                    if base_name:
                        sym.add_relationship(RelationshipKind.INHERITS, base_name)
            self.symbols.append(sym)

            if body_node:
                for child in body_node.named_children:
                    self._visit(child, parent_prefix=f"{qname}.", parent_id=sym_id)
        else:
            for child in node.named_children:
                self._visit(child, parent_prefix, parent_id)

    # ----------------- JS / TS -----------------
    def _handle_javascript(self, node: Node, outer_node: Node, parent_prefix: str, parent_id: str | None) -> None:
        if node.type in {"function_declaration", "generator_function_declaration", "method_definition"}:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = self.text(name_node)
            qname = f"{parent_prefix}{name}" if parent_prefix else name
            stype = SymbolType.METHOD if (parent_prefix or node.type == "method_definition") else SymbolType.FUNCTION
            params_node = node.child_by_field_name("parameters")
            ret_node = node.child_by_field_name("return_type")

            sig_raw = f"{name}{self.text(params_node)}"
            if ret_node:
                sig_raw += f": {self.text(ret_node)}"

            sym_id = self.parser.make_symbol_id(self.file_path, qname, outer_node.start_point.row + 1)
            sym = Symbol(
                id=sym_id,
                name=name,
                qualified_name=qname,
                symbol_type=stype,
                location=self.location(outer_node),
                language=self.language,
                signature=SymbolSignature(
                    raw=sig_raw,
                    name=name,
                    parameters=self._parse_parameters(params_node),
                    return_type=self.text(ret_node) if ret_node else None,
                ),
                docstring=self._extract_leading_comment(outer_node),
                body=self.text(outer_node),
                parent_id=parent_id,
            )
            self.symbols.append(sym)

        elif node.type in {"class_declaration", "interface_declaration", "type_alias_declaration"}:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = self.text(name_node)
            qname = f"{parent_prefix}{name}" if parent_prefix else name

            if node.type == "interface_declaration":
                stype = SymbolType.INTERFACE
            elif node.type == "type_alias_declaration":
                stype = SymbolType.TYPE_ALIAS
            else:
                stype = SymbolType.CLASS

            sym_id = self.parser.make_symbol_id(self.file_path, qname, outer_node.start_point.row + 1)
            sym = Symbol(
                id=sym_id,
                name=name,
                qualified_name=qname,
                symbol_type=stype,
                location=self.location(outer_node),
                language=self.language,
                signature=SymbolSignature(raw=f"{node.type.split('_')[0]} {name}", name=name),
                docstring=self._extract_leading_comment(outer_node),
                body=self.text(outer_node),
                parent_id=parent_id,
            )

            # Check class_heritage
            heritage = next((c for c in node.children if c.type == "class_heritage"), None)
            if heritage:
                for h_child in heritage.named_children:
                    if h_child.type == "extends_clause":
                        for sc in h_child.named_children:
                            if sc.type in {"identifier", "type_identifier"}:
                                sym.add_relationship(RelationshipKind.INHERITS, self.text(sc))
                    elif h_child.type == "implements_clause":
                        for sc in h_child.named_children:
                            if sc.type in {"identifier", "type_identifier"}:
                                sym.add_relationship(RelationshipKind.IMPLEMENTS, self.text(sc))

            self.symbols.append(sym)

            body_node = node.child_by_field_name("body")
            if body_node:
                for child in body_node.named_children:
                    self._visit(child, parent_prefix=f"{qname}.", parent_id=sym_id)
        else:
            for child in node.named_children:
                self._visit(child, parent_prefix, parent_id)

    # ----------------- Go -----------------
    def _handle_go(self, node: Node, outer_node: Node, parent_prefix: str, parent_id: str | None) -> None:
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = self.text(name_node)
            params_node = node.child_by_field_name("parameters")
            result_node = node.child_by_field_name("result")

            sig_raw = f"func {name}{self.text(params_node)}"
            if result_node:
                sig_raw += f" {self.text(result_node)}"

            sym_id = self.parser.make_symbol_id(self.file_path, name, outer_node.start_point.row + 1)
            sym = Symbol(
                id=sym_id,
                name=name,
                qualified_name=name,
                symbol_type=SymbolType.FUNCTION,
                location=self.location(outer_node),
                language="go",
                signature=SymbolSignature(
                    raw=sig_raw,
                    name=name,
                    parameters=self._parse_parameters(params_node),
                    return_type=self.text(result_node) if result_node else None,
                ),
                docstring=self._extract_leading_comment(outer_node),
                body=self.text(outer_node),
                parent_id=parent_id,
            )
            self.symbols.append(sym)

        elif node.type == "method_declaration":
            receiver_node = node.child_by_field_name("receiver")
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = self.text(name_node)
            receiver_text = self.text(receiver_node).strip("()")
            rec_type = receiver_text.split()[-1].lstrip("*") if receiver_text else ""
            qname = f"{rec_type}.{name}" if rec_type else name

            params_node = node.child_by_field_name("parameters")
            result_node = node.child_by_field_name("result")
            sig_raw = f"func {self.text(receiver_node)} {name}{self.text(params_node)}"
            if result_node:
                sig_raw += f" {self.text(result_node)}"

            sym_id = self.parser.make_symbol_id(self.file_path, qname, outer_node.start_point.row + 1)
            sym = Symbol(
                id=sym_id,
                name=name,
                qualified_name=qname,
                symbol_type=SymbolType.METHOD,
                location=self.location(outer_node),
                language="go",
                signature=SymbolSignature(
                    raw=sig_raw,
                    name=name,
                    parameters=self._parse_parameters(params_node),
                    return_type=self.text(result_node) if result_node else None,
                ),
                docstring=self._extract_leading_comment(outer_node),
                body=self.text(outer_node),
                parent_id=parent_id,
            )
            if rec_type:
                sym.add_relationship(RelationshipKind.CONTAINS, rec_type)
            self.symbols.append(sym)

        elif node.type == "type_declaration":
            for spec in node.named_children:
                if spec.type == "type_spec":
                    name_node = spec.child_by_field_name("name")
                    type_node = spec.child_by_field_name("type")
                    if not name_node:
                        continue
                    name = self.text(name_node)
                    stype = SymbolType.STRUCT if (type_node and "struct" in type_node.type) else SymbolType.TYPE_ALIAS
                    if type_node and "interface" in type_node.type:
                        stype = SymbolType.INTERFACE

                    sym_id = self.parser.make_symbol_id(self.file_path, name, outer_node.start_point.row + 1)
                    sym = Symbol(
                        id=sym_id,
                        name=name,
                        qualified_name=name,
                        symbol_type=stype,
                        location=self.location(outer_node),
                        language="go",
                        signature=SymbolSignature(raw=f"type {name} {self.text(type_node)}", name=name),
                        docstring=self._extract_leading_comment(outer_node),
                        body=self.text(outer_node),
                        parent_id=parent_id,
                    )
                    self.symbols.append(sym)
        else:
            for child in node.named_children:
                self._visit(child, parent_prefix, parent_id)

    # ----------------- Java -----------------
    def _handle_java(self, node: Node, outer_node: Node, parent_prefix: str, parent_id: str | None) -> None:
        if node.type in {"class_declaration", "interface_declaration", "enum_declaration"}:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = self.text(name_node)
            qname = f"{parent_prefix}{name}" if parent_prefix else name
            if node.type == "interface_declaration":
                stype = SymbolType.INTERFACE
            elif node.type == "enum_declaration":
                stype = SymbolType.ENUM
            else:
                stype = SymbolType.CLASS

            sym_id = self.parser.make_symbol_id(self.file_path, qname, outer_node.start_point.row + 1)
            sym = Symbol(
                id=sym_id,
                name=name,
                qualified_name=qname,
                symbol_type=stype,
                location=self.location(outer_node),
                language="java",
                signature=SymbolSignature(raw=f"{node.type.split('_')[0]} {name}", name=name),
                docstring=self._extract_leading_comment(outer_node),
                body=self.text(outer_node),
                parent_id=parent_id,
            )
            super_node = node.child_by_field_name("superclass")
            if super_node:
                sym.add_relationship(RelationshipKind.INHERITS, self.text(super_node).replace("extends", "").strip())
            interfaces_node = node.child_by_field_name("interfaces")
            if interfaces_node:
                for iface in interfaces_node.named_children:
                    i_name = self.text(iface).replace("implements", "").strip()
                    if i_name:
                        sym.add_relationship(RelationshipKind.IMPLEMENTS, i_name)

            self.symbols.append(sym)
            body_node = node.child_by_field_name("body")
            if body_node:
                for child in body_node.named_children:
                    self._visit(child, parent_prefix=f"{qname}.", parent_id=sym_id)

        elif node.type in {"method_declaration", "constructor_declaration"}:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = self.text(name_node)
            qname = f"{parent_prefix}{name}" if parent_prefix else name
            stype = SymbolType.CONSTRUCTOR if node.type == "constructor_declaration" else SymbolType.METHOD
            ret_node = node.child_by_field_name("type")
            params_node = node.child_by_field_name("parameters")

            sig_raw = f"{self.text(ret_node) + ' ' if ret_node else ''}{name}{self.text(params_node)}"
            sym_id = self.parser.make_symbol_id(self.file_path, qname, outer_node.start_point.row + 1)
            sym = Symbol(
                id=sym_id,
                name=name,
                qualified_name=qname,
                symbol_type=stype,
                location=self.location(outer_node),
                language="java",
                signature=SymbolSignature(
                    raw=sig_raw,
                    name=name,
                    parameters=self._parse_parameters(params_node),
                    return_type=self.text(ret_node) if ret_node else None,
                ),
                docstring=self._extract_leading_comment(outer_node),
                body=self.text(outer_node),
                parent_id=parent_id,
            )
            self.symbols.append(sym)
        else:
            for child in node.named_children:
                self._visit(child, parent_prefix, parent_id)

    # ----------------- C / C++ -----------------
    def _handle_cpp(self, node: Node, outer_node: Node, parent_prefix: str, parent_id: str | None) -> None:
        if node.type in {"class_specifier", "struct_specifier"}:
            name_node = node.child_by_field_name("name")
            name = self.text(name_node) if name_node else "anonymous"
            qname = f"{parent_prefix}{name}" if parent_prefix else name
            stype = SymbolType.CLASS if node.type == "class_specifier" else SymbolType.STRUCT

            sym_id = self.parser.make_symbol_id(self.file_path, qname, outer_node.start_point.row + 1)
            sym = Symbol(
                id=sym_id,
                name=name,
                qualified_name=qname,
                symbol_type=stype,
                location=self.location(outer_node),
                language=self.language,
                signature=SymbolSignature(raw=f"{node.type.split('_')[0]} {name}", name=name),
                docstring=self._extract_leading_comment(outer_node),
                body=self.text(outer_node),
                parent_id=parent_id,
            )

            base_clause = next((c for c in node.children if c.type == "base_class_clause"), None)
            if base_clause:
                for base_item in base_clause.named_children:
                    raw_b = self.text(base_item)
                    for mod in ("public", "protected", "private"):
                        raw_b = raw_b.replace(mod, "")
                    b_name = raw_b.strip()
                    if b_name:
                        sym.add_relationship(RelationshipKind.INHERITS, b_name)

            self.symbols.append(sym)
            body_node = node.child_by_field_name("body")
            if body_node:
                for child in body_node.named_children:
                    self._visit(child, parent_prefix=f"{qname}::", parent_id=sym_id)

        elif node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            ret_node = node.child_by_field_name("type")
            name = ""
            params_node = None
            if declarator:
                if declarator.type == "function_declarator":
                    inner_decl = declarator.child_by_field_name("declarator")
                    name = self.text(inner_decl)
                    params_node = declarator.child_by_field_name("parameters")
                else:
                    name = self.text(declarator)

            if not name:
                name = "anonymous"
            qname = f"{parent_prefix}{name}" if parent_prefix else name
            stype = SymbolType.METHOD if parent_prefix else SymbolType.FUNCTION

            params_str = self.text(params_node) if params_node else "()"
            ret_str = f"{self.text(ret_node)} " if ret_node else ""
            sig_raw = f"{ret_str}{name}{params_str}"
            sym_id = self.parser.make_symbol_id(self.file_path, qname, outer_node.start_point.row + 1)
            sym = Symbol(
                id=sym_id,
                name=name,
                qualified_name=qname,
                symbol_type=stype,
                location=self.location(outer_node),
                language=self.language,
                signature=SymbolSignature(
                    raw=sig_raw,
                    name=name,
                    parameters=self._parse_parameters(params_node),
                    return_type=self.text(ret_node) if ret_node else None,
                ),
                docstring=self._extract_leading_comment(outer_node),
                body=self.text(outer_node),
                parent_id=parent_id,
            )
            self.symbols.append(sym)
        else:
            for child in node.named_children:
                self._visit(child, parent_prefix, parent_id)

    # ----------------- Rust -----------------
    def _handle_rust(self, node: Node, outer_node: Node, parent_prefix: str, parent_id: str | None) -> None:
        if node.type in {"struct_item", "enum_item", "trait_item"}:
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = self.text(name_node)
            qname = f"{parent_prefix}{name}" if parent_prefix else name
            if node.type == "trait_item":
                stype = SymbolType.INTERFACE
            elif node.type == "enum_item":
                stype = SymbolType.ENUM
            else:
                stype = SymbolType.STRUCT

            sym_id = self.parser.make_symbol_id(self.file_path, qname, outer_node.start_point.row + 1)
            sym = Symbol(
                id=sym_id,
                name=name,
                qualified_name=qname,
                symbol_type=stype,
                location=self.location(outer_node),
                language="rust",
                signature=SymbolSignature(raw=f"{node.type.split('_')[0]} {name}", name=name),
                docstring=self._extract_leading_comment(outer_node),
                body=self.text(outer_node),
                parent_id=parent_id,
            )
            self.symbols.append(sym)

        elif node.type == "impl_item":
            type_node = node.child_by_field_name("type")
            t_name = self.text(type_node)
            prefix = f"{t_name}::" if t_name else ""
            body_node = node.child_by_field_name("body")
            if body_node:
                for child in body_node.named_children:
                    self._visit(child, parent_prefix=prefix, parent_id=None)

        elif node.type == "function_item":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name = self.text(name_node)
            qname = f"{parent_prefix}{name}" if parent_prefix else name
            stype = SymbolType.METHOD if parent_prefix else SymbolType.FUNCTION
            params_node = node.child_by_field_name("parameters")
            ret_node = node.child_by_field_name("return_type")

            sig_raw = f"fn {name}{self.text(params_node)}"
            if ret_node:
                sig_raw += f" -> {self.text(ret_node)}"

            sym_id = self.parser.make_symbol_id(self.file_path, qname, outer_node.start_point.row + 1)
            sym = Symbol(
                id=sym_id,
                name=name,
                qualified_name=qname,
                symbol_type=stype,
                location=self.location(outer_node),
                language="rust",
                signature=SymbolSignature(
                    raw=sig_raw,
                    name=name,
                    parameters=self._parse_parameters(params_node),
                    return_type=self.text(ret_node) if ret_node else None,
                ),
                docstring=self._extract_leading_comment(outer_node),
                body=self.text(outer_node),
                parent_id=parent_id,
            )
            self.symbols.append(sym)
        else:
            for child in node.named_children:
                self._visit(child, parent_prefix, parent_id)

    # ----------------- Parameter Helper -----------------
    def _parse_parameters(self, params_node: Node | None) -> list[SymbolParameter]:
        if not params_node:
            return []
        params: list[SymbolParameter] = []
        for child in params_node.named_children:
            if child.type in {"identifier", "typed_parameter", "parameter", "formal_parameter"}:
                p_text = self.text(child)
                parts = p_text.split(":")
                name = parts[0].strip()
                t_ann = parts[1].strip() if len(parts) > 1 else None
                params.append(SymbolParameter(name=name, type_annotation=t_ann))
            elif child.type not in {",", "(", ")"}:
                p_text = self.text(child).strip()
                if p_text and p_text not in {",", "(", ")"}:
                    params.append(SymbolParameter(name=p_text))
        return params
