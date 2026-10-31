"""Generic Delphi and Object Pascal parser.

Parses .pas units (interface, implementation, uses clauses, classes, methods,
signatures, docstrings) and .dfm form definition files into structured symbols.
Free of vendor-specific dependencies or internal terminology.
"""

from __future__ import annotations

import re
from pathlib import Path

from faccoder_code_intel.models import (
    RelationshipKind,
    Symbol,
    SymbolLocation,
    SymbolParameter,
    SymbolSignature,
    SymbolType,
)
from faccoder_code_intel.parsers.base import BaseParser


class DelphiParser(BaseParser):
    """Parser for Delphi/Object Pascal source (.pas, .dpr, .dpk, .inc) and form (.dfm) files."""

    RE_UNIT = re.compile(r"^\s*unit\s+(\w+)\s*;", re.IGNORECASE | re.MULTILINE)
    RE_USES = re.compile(r"\buses\b\s*([\s\S]*?);", re.IGNORECASE)
    RE_INTERFACE = re.compile(r"\binterface\b([\s\S]*?)(?=\bimplementation\b)", re.IGNORECASE)
    RE_IMPLEMENTATION = re.compile(
        r"\bimplementation\b([\s\S]*?)(?=\binitialization\b|\bfinalization\b|\bend\.)",
        re.IGNORECASE,
    )
    RE_CLASS = re.compile(
        r"^\s*(\w+)\s*=\s*(class|interface)\s*(?:\(([\w\s,]+)\))?\s*([\s\S]*?)\bend\b\s*;",
        re.IGNORECASE | re.MULTILINE,
    )
    RE_METHOD_HEADER = re.compile(
        r"^(?:class\s+)?(function|procedure|constructor|destructor)\s+((?:\w+\.)*\w+)"
        r"(?:\(([\s\S]*?)\))?(?:\s*:\s*([\w\.<>]+))?"
        r"((?:\s*;\s*(?:override|virtual|overload|reintroduce|abstract|static|inline|stdcall|cdecl|safecall))*)\s*;",
        re.IGNORECASE | re.MULTILINE,
    )
    RE_DFM_OBJECT = re.compile(
        r"^\s*(?:inherited|object|inline)\s+(\w+)\s*:\s*(\w+)",
        re.IGNORECASE | re.MULTILINE,
    )

    @property
    def supported_languages(self) -> list[str]:
        return ["delphi", "pascal"]

    @property
    def supported_extensions(self) -> list[str]:
        return [".pas", ".dfm", ".dpr", ".dpk", ".inc"]

    def parse(self, content: str, file_path: str = "") -> list[Symbol]:
        suffix = Path(file_path).suffix.lower() if file_path else ".pas"
        if suffix == ".dfm":
            return self._parse_dfm(content, file_path)
        return self._parse_pas(content, file_path)

    def _parse_pas(self, content: str, file_path: str) -> list[Symbol]:
        symbols: list[Symbol] = []
        lines = content.splitlines()

        # 1. Unit symbol
        unit_match = self.RE_UNIT.search(content)
        unit_name = unit_match.group(1) if unit_match else Path(file_path).stem or "Unit"
        unit_line = content[: unit_match.start()].count("\n") + 1 if unit_match else 1
        unit_sym_id = self.make_symbol_id(file_path, unit_name, unit_line)

        unit_sym = Symbol(
            id=unit_sym_id,
            name=unit_name,
            qualified_name=unit_name,
            symbol_type=SymbolType.MODULE,
            location=SymbolLocation(
                file_path=file_path,
                start_line=1,
                end_line=len(lines) if lines else 1,
            ),
            language="delphi",
            signature=SymbolSignature(raw=f"unit {unit_name};", name=unit_name),
            docstring=self._extract_header_docstring(lines),
        )

        # 2. Uses clauses
        for uses_match in self.RE_USES.finditer(content):
            raw_uses = uses_match.group(1)
            clean_uses = re.sub(r"\{[^}]*\}|\(\*[\s\S]*?\*\)|//.*$", "", raw_uses, flags=re.MULTILINE)
            for token in re.split(r"[,\s]+", clean_uses.strip()):
                token = token.strip().rstrip(",").strip()
                if token and token.lower() not in {"in"}:
                    unit_sym.add_relationship(RelationshipKind.USES, token)

        symbols.append(unit_sym)

        # 3. Class declarations in interface
        interface_match = self.RE_INTERFACE.search(content)
        if interface_match:
            intf_start_char = interface_match.start(1)
            intf_content = interface_match.group(1)
            for class_match in self.RE_CLASS.finditer(intf_content):
                c_name = class_match.group(1)
                c_kind = class_match.group(2).lower()
                c_bases = class_match.group(3)
                c_body = class_match.group(4)

                abs_start = intf_start_char + class_match.start()
                abs_end = intf_start_char + class_match.end()
                start_line = content[:abs_start].count("\n") + 1
                end_line = content[:abs_end].count("\n") + 1

                stype = SymbolType.INTERFACE if c_kind == "interface" else SymbolType.CLASS
                class_id = self.make_symbol_id(file_path, c_name, start_line)

                class_sym = Symbol(
                    id=class_id,
                    name=c_name,
                    qualified_name=c_name,
                    symbol_type=stype,
                    location=SymbolLocation(
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                    ),
                    language="delphi",
                    signature=SymbolSignature(
                        raw=f"{c_name} = {c_kind}" + (f"({c_bases})" if c_bases else "") + " ... end;",
                        name=c_name,
                    ),
                    body=class_match.group(0),
                    parent_id=unit_sym_id,
                )

                if c_bases:
                    bases_list = [b.strip() for b in c_bases.split(",") if b.strip()]
                    if bases_list:
                        class_sym.add_relationship(RelationshipKind.INHERITS, bases_list[0])
                        for iface in bases_list[1:]:
                            class_sym.add_relationship(RelationshipKind.IMPLEMENTS, iface)

                # Extract interface properties
                prop_pattern = r"^\s*property\s+(\w+)\s*:\s*([\w\.<>]+)"
                for prop_match in re.finditer(prop_pattern, c_body, re.MULTILINE | re.IGNORECASE):
                    prop_name = prop_match.group(1)
                    prop_type = prop_match.group(2)
                    prop_line = start_line + c_body[: prop_match.start()].count("\n")
                    symbols.append(
                        Symbol(
                            id=self.make_symbol_id(file_path, f"{c_name}.{prop_name}", prop_line),
                            name=prop_name,
                            qualified_name=f"{c_name}.{prop_name}",
                            symbol_type=SymbolType.PROPERTY,
                            location=SymbolLocation(file_path=file_path, start_line=prop_line, end_line=prop_line),
                            language="delphi",
                            signature=SymbolSignature(raw=f"property {prop_name}: {prop_type};", name=prop_name),
                            parent_id=class_id,
                        )
                    )

                symbols.append(class_sym)

        # 4. Method implementations in implementation section
        impl_match = self.RE_IMPLEMENTATION.search(content)
        if impl_match:
            impl_start_char = impl_match.start(1)
            impl_start_line = content[:impl_start_char].count("\n") + 1
            impl_text = impl_match.group(1)
            symbols.extend(self._extract_implementation_methods(impl_text, impl_start_line, file_path, unit_sym_id))

        return symbols

    def _extract_implementation_methods(
        self,
        impl_text: str,
        impl_start_line: int,
        file_path: str,
        unit_id: str,
    ) -> list[Symbol]:
        methods: list[Symbol] = []
        lines = impl_text.splitlines()
        i = 0
        total_lines = len(lines)

        while i < total_lines:
            line = lines[i].strip()
            # Check if line begins a routine definition
            if re.match(
                r"^(?:class\s+)?(function|procedure|constructor|destructor)\b",
                line,
                re.IGNORECASE,
            ):
                # Accumulate multiline headers until matching ')' and ';' or 'begin'
                header_lines = [line]
                header_idx = i
                paren_depth = line.count("(") - line.count(")")
                while header_idx + 1 < total_lines:
                    if paren_depth <= 0 and (";" in header_lines[-1] or "begin" in header_lines[-1].lower()):
                        break
                    header_idx += 1
                    next_line = lines[header_idx].strip()
                    paren_depth += next_line.count("(") - next_line.count(")")
                    header_lines.append(next_line)

                header_text = " ".join(header_lines)
                match = re.match(
                    r"^(?:class\s+)?(function|procedure|constructor|destructor)\s+"
                    r"((?:\w+\.)*\w+)(?:\(([\s\S]*?)\))?(?:\s*:\s*([\w\.<>]+))?",
                    header_text,
                    re.IGNORECASE,
                )
                if match:
                    m_kind = match.group(1).lower()
                    full_name = match.group(2)
                    params_raw = match.group(3) or ""
                    return_type = match.group(4)

                    start_idx = i
                    # Locate beginning of body and matching end
                    end_idx = self._find_routine_end(lines, i)
                    body_lines = lines[start_idx : end_idx + 1]
                    body_content = "\n".join(body_lines)

                    start_line = impl_start_line + start_idx
                    end_line = impl_start_line + end_idx

                    if m_kind == "constructor":
                        stype = SymbolType.CONSTRUCTOR
                    elif m_kind == "destructor":
                        stype = SymbolType.DESTRUCTOR
                    elif "." in full_name:
                        stype = SymbolType.METHOD
                    else:
                        stype = SymbolType.FUNCTION

                    # Determine parent class if any
                    parent_class = full_name.split(".")[0] if "." in full_name else None
                    short_name = full_name.split(".")[-1]

                    # Parse parameters
                    params: list[SymbolParameter] = []
                    if params_raw:
                        for p_chunk in params_raw.split(";"):
                            p_chunk = p_chunk.strip()
                            if not p_chunk:
                                continue
                            if ":" in p_chunk:
                                p_names, p_t = p_chunk.split(":", 1)
                                p_type = p_t.strip()
                                for pn in p_names.split(","):
                                    pn = pn.strip()
                                    for prefix in ("var ", "const ", "out "):
                                        if pn.lower().startswith(prefix):
                                            pn = pn[len(prefix) :].strip()
                                    if pn:
                                        params.append(SymbolParameter(name=pn, type_annotation=p_type))
                            else:
                                params.append(SymbolParameter(name=p_chunk))

                    raw_sig = header_text.split(";")[0].strip() + ";"
                    sym_id = self.make_symbol_id(file_path, full_name, start_line)

                    sym = Symbol(
                        id=sym_id,
                        name=short_name,
                        qualified_name=full_name,
                        symbol_type=stype,
                        location=SymbolLocation(
                            file_path=file_path,
                            start_line=start_line,
                            end_line=end_line,
                        ),
                        language="delphi",
                        signature=SymbolSignature(
                            raw=raw_sig,
                            name=short_name,
                            parameters=params,
                            return_type=return_type,
                        ),
                        docstring=self._extract_leading_comment_from_lines(lines, start_idx),
                        body=body_content,
                        parent_id=unit_id,
                    )
                    if parent_class:
                        sym.add_relationship(RelationshipKind.CONTAINS, parent_class)

                    methods.append(sym)
                    i = end_idx + 1
                    continue
            i += 1

        return methods

    def _find_routine_end(self, lines: list[str], start: int) -> int:
        depth = 0
        found_begin = False
        total = len(lines)

        for idx in range(start, total):
            line = lines[idx]
            clean = re.sub(r"'[^']*'", "", line)
            clean = re.sub(r"\{[^}]*\}|\(\*[\s\S]*?\*\)|//.*$", "", clean)
            clean = clean.strip()

            begins = len(re.findall(r"\bbegin\b", clean, re.IGNORECASE))
            asm_begins = len(re.findall(r"\basm\b", clean, re.IGNORECASE))
            case_begins = len(re.findall(r"\bcase\b", clean, re.IGNORECASE))
            ends = len(re.findall(r"\bend\b", clean, re.IGNORECASE))

            total_open = begins + asm_begins + case_begins
            if total_open > 0:
                found_begin = True

            depth += total_open - ends

            if found_begin and depth <= 0:
                return idx

            # Safety fallback for forward or interface declarations ending in semicolon
            if not found_begin and idx > start + 3 and line.endswith(";"):
                if re.match(r"^(?:class\s+)?(function|procedure|constructor|destructor)\b", line, re.IGNORECASE):
                    return idx - 1

        return total - 1

    def _extract_leading_comment_from_lines(self, lines: list[str], start_idx: int) -> str | None:
        comments: list[str] = []
        idx = start_idx - 1
        while idx >= 0:
            line = lines[idx].strip()
            if line.startswith("//"):
                comments.insert(0, line.lstrip("/").strip())
                idx -= 1
            elif line.startswith("{") and line.endswith("}"):
                comments.insert(0, line.strip("{} \t"))
                idx -= 1
            elif line.startswith("(*") and line.endswith("*)"):
                comments.insert(0, line.strip("(*)\t "))
                idx -= 1
            else:
                break
        return "\n".join(comments) if comments else None

    def _extract_header_docstring(self, lines: list[str]) -> str | None:
        comments: list[str] = []
        for line in lines[:20]:
            clean = line.strip()
            if clean.startswith("//"):
                comments.append(clean.lstrip("/").strip())
            elif clean.startswith("{") and clean.endswith("}"):
                comments.append(clean.strip("{} \t"))
            elif clean.lower().startswith("unit "):
                break
        return "\n".join(comments) if comments else None

    def _parse_dfm(self, content: str, file_path: str) -> list[Symbol]:
        """Parse Delphi form (.dfm) textual file into component symbols."""
        symbols: list[Symbol] = []
        lines = content.splitlines()

        for idx, line in enumerate(lines):
            match = self.RE_DFM_OBJECT.match(line)
            if match:
                comp_name = match.group(1)
                comp_type = match.group(2)
                line_no = idx + 1
                sym_id = self.make_symbol_id(file_path, comp_name, line_no)

                symbols.append(
                    Symbol(
                        id=sym_id,
                        name=comp_name,
                        qualified_name=f"{comp_name}: {comp_type}",
                        symbol_type=SymbolType.DFM_OBJECT,
                        location=SymbolLocation(file_path=file_path, start_line=line_no, end_line=line_no),
                        language="delphi",
                        signature=SymbolSignature(raw=line.strip(), name=comp_name),
                        metadata={"component_type": comp_type},
                    )
                )

        return symbols
