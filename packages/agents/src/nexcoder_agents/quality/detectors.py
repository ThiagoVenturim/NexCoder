"""Deterministic quality detectors.

Every detector is a pure function over a `ProjectSnapshot` (or plain data) and
returns `QualityFinding` items with file, line, priority and a suggestion. No
detector calls a model, the network or the disk.

Language coverage: duplication, function length, abstractions with a single
implementation, temporary markers, SQL modeling and folder structure work on
every language `nexcoder-code-intel` parses. Wrapper, complexity, naming and
loop checks read the Python AST and only cover Python files.
"""

from __future__ import annotations

import ast
import io
import keyword
import re
import tokenize
from collections.abc import Iterator
from pathlib import PurePosixPath

from nexcoder_code_intel.graph import EdgeType
from nexcoder_code_intel.models import RelationshipKind, Symbol, SymbolType

from nexcoder_agents.quality.models import (
    BranchInfo,
    QualityCategory,
    QualityFinding,
    QualitySeverity,
    QualityThresholds,
    sort_findings,
)
from nexcoder_agents.quality.snapshot import ProjectSnapshot, is_test_path

_CALLABLE_TYPES = {SymbolType.FUNCTION, SymbolType.METHOD, SymbolType.CONSTRUCTOR}
_FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _iter_python_functions(
    tree: ast.AST, prefix: str = "", owner: ast.ClassDef | None = None
) -> Iterator[tuple[_FunctionNode, ast.ClassDef | None, str]]:
    """Yield `(function node, enclosing class, qualified name)` for a module tree."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            qname = f"{prefix}{node.name}"
            yield node, owner, qname
            yield from _iter_python_functions(node, prefix=f"{qname}.", owner=None)
        elif isinstance(node, ast.ClassDef):
            yield from _iter_python_functions(node, prefix=f"{prefix}{node.name}.", owner=node)
        else:
            yield from _iter_python_functions(node, prefix=prefix, owner=owner)


def _iter_python_classes(tree: ast.AST, prefix: str = "") -> Iterator[tuple[ast.ClassDef, str]]:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            qname = f"{prefix}{node.name}"
            yield node, qname
            yield from _iter_python_classes(node, prefix=f"{qname}.")
        elif not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield from _iter_python_classes(node, prefix=prefix)


def _body_without_docstring(node: _FunctionNode | ast.ClassDef) -> list[ast.stmt]:
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            body = body[1:]
    return body


def _dotted_name(node: ast.AST) -> str:
    """Render `a.b.c` for Name/Attribute chains; empty string for anything else."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return ""


def _is_method(owner: ast.ClassDef | None, func: _FunctionNode) -> bool:
    if owner is None:
        return False
    return not any(_dotted_name(d) == "staticmethod" for d in func.decorator_list)


def _delegated_call(func: _FunctionNode, owner: ast.ClassDef | None, allow_no_params: bool = False) -> str:
    """Return the dotted callee when `func` only forwards its own parameters, else ''.

    A forwarder has a single statement that calls something with exactly the
    function's parameters, in order, adding no constant, default or logic.
    """
    body = _body_without_docstring(func)
    if len(body) != 1:
        return ""
    stmt = body[0]
    value = stmt.value if isinstance(stmt, ast.Return | ast.Expr) else None
    if isinstance(value, ast.Await):
        value = value.value
    if not isinstance(value, ast.Call):
        return ""

    args = func.args
    if args.defaults or any(d is not None for d in args.kw_defaults):
        return ""  # supplying defaults is real value (partial application)

    positional = [a.arg for a in [*args.posonlyargs, *args.args]]
    if _is_method(owner, func) and positional:
        positional = positional[1:]
    keyword_only = [a.arg for a in args.kwonlyargs]
    if not allow_no_params and not (positional or keyword_only or args.vararg or args.kwarg):
        return ""

    expected: list[str] = [*positional]
    if args.vararg:
        expected.append(f"*{args.vararg.arg}")
    expected.extend(f"{name}=" for name in keyword_only)
    if args.kwarg:
        expected.append(f"**{args.kwarg.arg}")

    passed: list[str] = []
    for arg in value.args:
        if isinstance(arg, ast.Name):
            passed.append(arg.id)
        elif isinstance(arg, ast.Starred) and isinstance(arg.value, ast.Name):
            passed.append(f"*{arg.value.id}")
        else:
            return ""
    for kw in value.keywords:
        if not isinstance(kw.value, ast.Name):
            return ""
        if kw.arg is None:
            passed.append(f"**{kw.value.id}")
        elif kw.arg == kw.value.id:
            passed.append(kw.arg if kw.arg in positional else f"{kw.arg}=")
        else:
            return ""

    if sorted(passed) != sorted(expected):
        return ""
    # Positional arguments must keep their order, otherwise the function adapts a signature.
    passed_positional = [p for p in passed if p in positional]
    if passed_positional != positional:
        return ""
    return _dotted_name(value.func)


def _symbol_exists(snapshot: ProjectSnapshot, name: str) -> bool:
    try:
        return snapshot.graph.resolve_symbol_id(name) is not None
    except ValueError:
        return True  # ambiguous means more than one definition exists


# --------------------------------------------------------------------------- #
# 1. Duplicated functions
# --------------------------------------------------------------------------- #

_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|\d+(?:\.\d+)?|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|[^\s\w]")
_TRIPLE_QUOTED_RE = re.compile(r"(\"\"\"|''')[\s\S]*?\1")
_LINE_COMMENT_RE = re.compile(r"(?m)(?:#|//).*$")
_STRUCTURAL_WORDS = frozenset(
    {
        *keyword.kwlist,
        "function", "var", "let", "const", "func", "fn", "new", "this", "self", "null", "nil", "true", "false",
        "public", "private", "protected", "static", "void", "switch", "case", "do", "begin", "end", "procedure",
        "then", "throw", "catch", "typeof", "interface", "struct", "impl", "match", "mut", "package", "go", "defer",
    }
)  # fmt: skip


def normalize_code_tokens(code: str) -> list[str]:
    """Tokenize code and erase names and literals, keeping only its structure.

    Two functions that differ only in identifiers, numbers, strings, comments or
    docstrings produce the same token list.
    """
    text = _TRIPLE_QUOTED_RE.sub(" ", code)
    text = _LINE_COMMENT_RE.sub("", text)
    tokens: list[str] = []
    for tok in _TOKEN_RE.findall(text):
        first = tok[0]
        if first.isalpha() or first == "_":
            tokens.append(tok if tok in _STRUCTURAL_WORDS else "ID")
        elif first.isdigit():
            tokens.append("NUM")
        elif first in "\"'":
            tokens.append("STR")
        else:
            tokens.append(tok)
    return tokens


def _shingles(tokens: list[str], size: int = 4) -> frozenset[tuple[str, ...]]:
    if len(tokens) < size:
        return frozenset({tuple(tokens)})
    return frozenset(tuple(tokens[i : i + size]) for i in range(len(tokens) - size + 1))


def token_similarity(left: list[str], right: list[str]) -> float:
    """Jaccard similarity between the 4-token shingles of two normalized token lists."""
    if left == right:
        return 1.0
    a, b = _shingles(left), _shingles(right)
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def detect_duplicate_functions(
    snapshot: ProjectSnapshot, thresholds: QualityThresholds | None = None
) -> list[QualityFinding]:
    """Find functions that are copies of each other (identical or near-identical structure).

    Bodies come from `nexcoder-code-intel` symbols, so the check is cross-language.
    """
    limits = thresholds or QualityThresholds()
    candidates: list[tuple[Symbol, list[str]]] = []
    for sym in snapshot.symbols:
        if sym.symbol_type not in _CALLABLE_TYPES or not sym.body or is_test_path(sym.location.file_path):
            continue
        tokens = normalize_code_tokens(sym.body)
        if len(tokens) >= limits.duplicate_min_tokens:
            candidates.append((sym, tokens))
    candidates.sort(key=lambda item: (item[0].location.file_path, item[0].location.start_line))

    parent = list(range(len(candidates)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    exact: dict[tuple[str, ...], int] = {}
    for idx, (_, tokens) in enumerate(candidates):
        first = exact.setdefault(tuple(tokens), idx)
        if first != idx:
            union(first, idx)

    # Near-duplicate comparison is quadratic; very large projects keep only exact clones.
    if len(candidates) <= limits.duplicate_max_candidates:
        shingle_sets = [_shingles(tokens) for _, tokens in candidates]
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                if find(i) == find(j):
                    continue
                len_i, len_j = len(candidates[i][1]), len(candidates[j][1])
                if min(len_i, len_j) / max(len_i, len_j) < 0.7:
                    continue
                union_size = len(shingle_sets[i] | shingle_sets[j])
                if union_size and len(shingle_sets[i] & shingle_sets[j]) / union_size >= limits.duplicate_similarity:
                    union(i, j)

    clusters: dict[int, list[int]] = {}
    for idx in range(len(candidates)):
        clusters.setdefault(find(idx), []).append(idx)

    findings: list[QualityFinding] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        symbols = [candidates[i][0] for i in members]
        anchor, others = symbols[0], symbols[1:]
        biggest = max(len(candidates[i][1]) for i in members)
        severity = QualitySeverity.P1 if len(members) >= 3 or biggest >= 200 else QualitySeverity.P2
        other_names = ", ".join(f"`{s.qualified_name}`" for s in others)
        findings.append(
            QualityFinding(
                rule="duplicate-function",
                category=QualityCategory.DUPLICATION,
                severity=severity,
                file_path=anchor.location.file_path,
                line=anchor.location.start_line,
                end_line=anchor.location.end_line,
                symbol=anchor.qualified_name,
                message=(
                    f"`{anchor.qualified_name}` has the same structure as {other_names}: "
                    f"{len(members)} copies solve the same problem."
                ),
                suggestion=(
                    "Keep one implementation, move it to a shared module and make the other call sites use it. "
                    "If the copies must differ, pass the difference as a parameter."
                ),
                related_locations=[f"{s.location.file_path}:{s.location.start_line}" for s in others],
            )
        )
    return sort_findings(findings)


# --------------------------------------------------------------------------- #
# 2. Useless wrappers
# --------------------------------------------------------------------------- #


def detect_useless_wrappers(snapshot: ProjectSnapshot) -> list[QualityFinding]:
    """Find Python functions that only forward their arguments to another callable."""
    findings: list[QualityFinding] = []
    for rel_path, tree in snapshot.python_trees():
        for func, owner, qname in _iter_python_functions(tree):
            if func.decorator_list or (func.name.startswith("__") and func.name.endswith("__")):
                continue
            if owner is not None and (owner.bases or owner.keywords):
                continue  # may be fulfilling an interface contract
            callee = _delegated_call(func, owner)
            if not callee or callee.split(".")[0] in {"self", "cls", "super"}:
                continue
            if callee.split(".")[-1] == func.name and "." not in callee:
                continue
            in_project = _symbol_exists(snapshot, callee.split(".")[-1])
            findings.append(
                QualityFinding(
                    rule="pass-through-wrapper",
                    category=QualityCategory.USELESS_WRAPPER,
                    severity=QualitySeverity.P2 if in_project else QualitySeverity.P3,
                    file_path=rel_path,
                    line=func.lineno,
                    end_line=func.end_lineno,
                    symbol=qname,
                    message=(
                        f"`{qname}` only forwards its arguments to `{callee}` "
                        "and adds no validation, default, conversion or error handling."
                    ),
                    suggestion=(
                        f"Call `{callee}` directly and delete `{qname}`. "
                        "If the new name matters, keep it as an alias or give the wrapper a real responsibility."
                    ),
                )
            )
    return sort_findings(findings)


# --------------------------------------------------------------------------- #
# 3. Temporary solutions
# --------------------------------------------------------------------------- #

_MARKER_RE = re.compile(
    r"\b(TODO|FIXME|HACK|XXX)\b"
    r"|(?i:\b(gambiarra|workaround|kludge|quick fix|temp(?:orary)? (?:fix|hack|solution)"
    r"|solucao temporaria|provisori[oa])\b)"
)
_COMMENT_LEADERS: dict[str, tuple[str, ...]] = {
    ".sql": ("--", "/*"),
    ".pas": ("//", "{", "(*"),
    ".php": ("//", "#", "/*"),
}
_DEFAULT_COMMENT_LEADERS = ("//", "/*")


def _python_comments(content: str) -> list[tuple[int, str]] | None:
    try:
        return [
            (tok.start[0], tok.string)
            for tok in tokenize.generate_tokens(io.StringIO(content).readline)
            if tok.type == tokenize.COMMENT
        ]
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return None


def _generic_comments(content: str, leaders: tuple[str, ...]) -> list[tuple[int, str]]:
    comments: list[tuple[int, str]] = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("*"):
            comments.append((lineno, stripped))
            continue
        positions = [pos for pos in (line.find(leader) for leader in leaders) if pos >= 0]
        if positions:
            comments.append((lineno, line[min(positions) :]))
    return comments


def detect_temporary_solutions(snapshot: ProjectSnapshot) -> list[QualityFinding]:
    """Find comments that admit a temporary solution (to-do, fix-me and hack markers)."""
    findings: list[QualityFinding] = []
    for rel_path, content in snapshot.files.items():
        suffix = PurePosixPath(rel_path).suffix.lower()
        comments = _python_comments(content) if suffix == ".py" else None
        if comments is None:
            leaders = ("#",) if suffix == ".py" else _COMMENT_LEADERS.get(suffix, _DEFAULT_COMMENT_LEADERS)
            comments = _generic_comments(content, leaders)
        for lineno, text in comments:
            match = _MARKER_RE.search(text)
            if not match:
                continue
            marker = match.group(1) or match.group(2).lower()
            is_note = marker == "TODO"
            findings.append(
                QualityFinding(
                    rule="temporary-marker",
                    category=QualityCategory.TEMPORARY_SOLUTION,
                    severity=QualitySeverity.P3 if is_note else QualitySeverity.P2,
                    file_path=rel_path,
                    line=lineno,
                    message=f"Temporary solution left in the code ({marker}): {text.strip()[:160]}",
                    suggestion=(
                        "Open an issue for the pending work and reference it here, or finish it now."
                        if is_note
                        else "Replace the workaround with the proper fix, or record why it must stay and until when."
                    ),
                )
            )
    return sort_findings(findings)


# --------------------------------------------------------------------------- #
# 4. Readability
# --------------------------------------------------------------------------- #

_VAGUE_NAMES = frozenset(
    {"foo", "bar", "baz", "tmp", "temp", "stuff", "thing", "things", "func", "function", "do_it", "doit", "aaa", "asdf"}
)
_SHORT_NAME_ALLOWLIST = frozenset({"id", "ok", "on", "up", "go", "io", "do", "eq", "ne", "lt", "gt", "le", "ge"})
_NUMBERED_NAME_RE = re.compile(
    r"^(?:[a-z]+_?)?(?:func|function|method|test|data|process|handle|new|old|tmp|temp)_?\d+$"
)
_BRANCH_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.comprehension)
_NESTING_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.Match)


def cyclomatic_complexity(func: ast.AST) -> int:
    """McCabe complexity of a Python function: 1 plus every decision point."""
    score = 1
    for node in ast.walk(func):
        if isinstance(node, _BRANCH_NODES):
            score += 1
        elif isinstance(node, ast.BoolOp):
            score += len(node.values) - 1
        elif isinstance(node, ast.match_case):
            score += 1
    return score


def max_nesting_depth(func: ast.AST) -> int:
    """Deepest level of nested control-flow blocks inside a Python function."""

    def depth(node: ast.AST, current: int) -> int:
        deepest = current
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
                continue
            level = current + 1 if isinstance(child, _NESTING_NODES) else current
            deepest = max(deepest, depth(child, level))
        return deepest

    return depth(func, 0)


def _length_finding(
    rel_path: str, name: str, start: int, end: int, limits: QualityThresholds
) -> QualityFinding | None:
    length = end - start + 1
    if length <= limits.max_function_lines:
        return None
    critical = length >= limits.critical_function_lines
    return QualityFinding(
        rule="long-function",
        category=QualityCategory.READABILITY,
        severity=QualitySeverity.P1 if critical else QualitySeverity.P2,
        file_path=rel_path,
        line=start,
        end_line=end,
        symbol=name,
        message=f"`{name}` is {length} lines long (limit {limits.max_function_lines}).",
        suggestion=(
            "Split it into smaller functions, one per step (validate, compute, persist, report), "
            "and name each step after what it does."
        ),
    )


def detect_readability_issues(
    snapshot: ProjectSnapshot, thresholds: QualityThresholds | None = None
) -> list[QualityFinding]:
    """Find long functions, high complexity, deep nesting, long parameter lists and vague names."""
    limits = thresholds or QualityThresholds()
    findings: list[QualityFinding] = []

    for rel_path, tree in snapshot.python_trees():
        for func, _owner, qname in _iter_python_functions(tree):
            length = _length_finding(rel_path, qname, func.lineno, func.end_lineno or func.lineno, limits)
            if length:
                findings.append(length)

            complexity = cyclomatic_complexity(func)
            if complexity > limits.max_complexity:
                findings.append(
                    QualityFinding(
                        rule="high-complexity",
                        category=QualityCategory.READABILITY,
                        severity=(
                            QualitySeverity.P1 if complexity >= limits.critical_complexity else QualitySeverity.P2
                        ),
                        file_path=rel_path,
                        line=func.lineno,
                        end_line=func.end_lineno,
                        symbol=qname,
                        message=f"`{qname}` has cyclomatic complexity {complexity} (limit {limits.max_complexity}).",
                        suggestion=(
                            "Use early returns, extract each branch into a named function, "
                            "or replace the condition chain with a lookup table."
                        ),
                    )
                )

            nesting = max_nesting_depth(func)
            if nesting > limits.max_nesting:
                findings.append(
                    QualityFinding(
                        rule="deep-nesting",
                        category=QualityCategory.READABILITY,
                        severity=QualitySeverity.P3,
                        file_path=rel_path,
                        line=func.lineno,
                        end_line=func.end_lineno,
                        symbol=qname,
                        message=f"`{qname}` nests control flow {nesting} levels deep (limit {limits.max_nesting}).",
                        suggestion="Invert conditions into guard clauses and move inner loops to helper functions.",
                    )
                )

            args = func.args
            param_count = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
            if param_count and (args.posonlyargs + args.args)[:1] and (args.posonlyargs + args.args)[0].arg in {
                "self",
                "cls",
            }:
                param_count -= 1
            if param_count > limits.max_parameters:
                findings.append(
                    QualityFinding(
                        rule="too-many-parameters",
                        category=QualityCategory.READABILITY,
                        severity=QualitySeverity.P3,
                        file_path=rel_path,
                        line=func.lineno,
                        symbol=qname,
                        message=f"`{qname}` takes {param_count} parameters (limit {limits.max_parameters}).",
                        suggestion="Group related parameters into a dataclass or split the function by responsibility.",
                    )
                )

            name = func.name
            is_dunder = name.startswith("__") and name.endswith("__")
            bare = name.lstrip("_")
            vague = (
                bare in _VAGUE_NAMES
                or (len(bare) <= 2 and bare not in _SHORT_NAME_ALLOWLIST)
                or bool(_NUMBERED_NAME_RE.match(bare))
            )
            if vague and not is_dunder:
                findings.append(
                    QualityFinding(
                        rule="vague-name",
                        category=QualityCategory.READABILITY,
                        severity=QualitySeverity.P3,
                        file_path=rel_path,
                        line=func.lineno,
                        symbol=qname,
                        message=f"`{qname}` has a name that does not say what the function does.",
                        suggestion=(
                            "Rename it to a verb plus object that states the outcome, for example `load_invoice`."
                        ),
                    )
                )

    # Other languages: length only, from code-intel symbol locations.
    for sym in snapshot.symbols:
        path = sym.location.file_path
        if sym.symbol_type not in _CALLABLE_TYPES or path.endswith(".py") or is_test_path(path):
            continue
        length = _length_finding(path, sym.qualified_name, sym.location.start_line, sym.location.end_line, limits)
        if length:
            findings.append(length)

    return sort_findings(findings)


# --------------------------------------------------------------------------- #
# 5. Over-engineering
# --------------------------------------------------------------------------- #

_ABSTRACT_BASE_NAMES = ("ABC", "ABCMeta")
_STRUCTURAL_BASE_NAMES = ("Protocol",)


def _is_abstract(sym: Symbol) -> bool:
    if sym.symbol_type == SymbolType.INTERFACE:
        return True
    bases = sym.relationships.get(RelationshipKind.INHERITS, [])
    if any(base.split(".")[-1].split("[")[0] in _STRUCTURAL_BASE_NAMES for base in bases):
        return False  # structural typing has no explicit implementers
    if any(base.split(".")[-1].split("=")[-1].strip() in _ABSTRACT_BASE_NAMES for base in bases):
        return True
    body = sym.body or ""
    if sym.language == "python":
        return "@abstractmethod" in body or "@abc.abstractmethod" in body
    signature = sym.signature.raw if sym.signature else ""
    return bool(re.search(r"\babstract\s+class\b", signature or body[:200]))


def _abstraction_findings(snapshot: ProjectSnapshot) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    inherit_kinds = [EdgeType.INHERITS.value, EdgeType.IMPLEMENTS.value]
    for sym in snapshot.symbols:
        path = sym.location.file_path
        if sym.symbol_type not in {SymbolType.CLASS, SymbolType.INTERFACE} or is_test_path(path):
            continue
        if not _is_abstract(sym):
            continue
        report = snapshot.graph.impact_analysis(sym.id, max_depth=1, edge_kinds=inherit_kinds)
        implementers = [a for a in report.affected_symbols if not is_test_path(a.file_path)]
        if len(implementers) > 1:
            continue
        if implementers:
            only = implementers[0]
            start_line = snapshot.graph.graph.nodes[only.symbol_id].get("start_line", 0)
            findings.append(
                QualityFinding(
                    rule="single-implementation-abstraction",
                    category=QualityCategory.OVER_ENGINEERING,
                    severity=QualitySeverity.P2,
                    file_path=path,
                    line=sym.location.start_line,
                    end_line=sym.location.end_line,
                    symbol=sym.qualified_name,
                    message=(
                        f"Abstraction `{sym.qualified_name}` has a single implementation (`{only.name}`): "
                        "the extra layer generalizes a variation that does not exist yet."
                    ),
                    suggestion=(
                        f"Use `{only.name}` directly and remove `{sym.qualified_name}`. "
                        "Extract the abstraction again when a second implementation is really needed."
                    ),
                    related_locations=[f"{only.file_path}:{start_line}"],
                )
            )
        else:
            findings.append(
                QualityFinding(
                    rule="unimplemented-abstraction",
                    category=QualityCategory.OVER_ENGINEERING,
                    severity=QualitySeverity.P3,
                    file_path=path,
                    line=sym.location.start_line,
                    end_line=sym.location.end_line,
                    symbol=sym.qualified_name,
                    message=f"Abstraction `{sym.qualified_name}` has no implementation in the project.",
                    suggestion=(
                        "Delete it if nothing uses it. Keep it only if it is a public extension point, "
                        "and say so in its docstring."
                    ),
                )
            )
    return findings


def _class_shape_findings(snapshot: ProjectSnapshot) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    for rel_path, tree in snapshot.python_trees():
        for cls, qname in _iter_python_classes(tree):
            methods = [n for n in cls.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
            public = [m for m in methods if not m.name.startswith("_")]

            # A class whose public methods all forward to the same collaborator is a hollow layer.
            forwarded = [
                callee
                for callee in (_delegated_call(m, cls, allow_no_params=True) for m in public)
                if callee.startswith("self.") and callee.count(".") >= 2
            ]
            targets = {".".join(callee.split(".")[:2]) for callee in forwarded}
            if len(public) >= 2 and len(forwarded) == len(public) and len(targets) == 1:
                target = next(iter(targets))
                findings.append(
                    QualityFinding(
                        rule="pass-through-layer",
                        category=QualityCategory.OVER_ENGINEERING,
                        severity=QualitySeverity.P2,
                        file_path=rel_path,
                        line=cls.lineno,
                        end_line=cls.end_lineno,
                        symbol=qname,
                        message=(
                            f"Every public method of `{qname}` only forwards to `{target}`: "
                            "the class is an indirection layer with no behavior of its own."
                        ),
                        suggestion=f"Let callers depend on `{target}` directly and remove `{qname}`.",
                    )
                )
                continue

            # A stateless class with one method is a function wearing a class.
            has_state = any(isinstance(n, ast.Assign | ast.AnnAssign) for n in cls.body)
            if cls.bases or cls.keywords or cls.decorator_list or has_state or len(methods) != 1 or len(public) != 1:
                continue
            method = public[0]
            uses_self = any(isinstance(n, ast.Name) and n.id in {"self", "cls"} for n in ast.walk(method))
            if uses_self:
                continue
            findings.append(
                QualityFinding(
                    rule="class-as-function",
                    category=QualityCategory.OVER_ENGINEERING,
                    severity=QualitySeverity.P3,
                    file_path=rel_path,
                    line=cls.lineno,
                    end_line=cls.end_lineno,
                    symbol=qname,
                    message=f"`{qname}` holds no state and has a single method (`{method.name}`).",
                    suggestion=f"Replace the class with a module-level function `{method.name}`.",
                )
            )
    return findings


def detect_over_engineering(snapshot: ProjectSnapshot) -> list[QualityFinding]:
    """Find abstractions and layers that exist without a real use.

    Inheritance is resolved through the `CodeGraph`, so the single-implementation
    rule covers every parsed language. Class-shape rules are Python only.
    """
    return sort_findings([*_abstraction_findings(snapshot), *_class_shape_findings(snapshot)])


# --------------------------------------------------------------------------- #
# 6. Performance
# --------------------------------------------------------------------------- #

_LOOP_NODES = (ast.For, ast.AsyncFor, ast.While)
_QUERY_METHODS = frozenset({"execute", "fetchone", "fetchall", "query", "find_one", "get_by_id", "find_by_id"})
_IO_METHODS = frozenset({"read_text", "write_text", "read_bytes", "write_bytes", "urlopen"})
_HTTP_CLIENTS = frozenset({"requests", "httpx"})


def _loop_depth(node: ast.AST) -> int:
    deepest = 0
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
            continue
        deepest = max(deepest, _loop_depth(child))
    return deepest + 1 if isinstance(node, _LOOP_NODES) else deepest


def detect_performance_smells(snapshot: ProjectSnapshot) -> list[QualityFinding]:
    """Find queries and I/O inside loops (N+1 pattern) and deeply nested loops in Python code."""
    findings: list[QualityFinding] = []
    for rel_path, tree in snapshot.python_trees():
        for func, _owner, qname in _iter_python_functions(tree):
            seen: set[tuple[str, int]] = set()
            loops = [n for n in ast.walk(func) if isinstance(n, _LOOP_NODES)]
            for loop in loops:
                for stmt in [*loop.body, *loop.orelse]:
                    for node in ast.walk(stmt):
                        if not isinstance(node, ast.Call):
                            continue
                        callee = _dotted_name(node.func)
                        method = node.func.attr if isinstance(node.func, ast.Attribute) else callee
                        rule = ""
                        if isinstance(node.func, ast.Attribute) and method in _QUERY_METHODS:
                            rule = "query-in-loop"
                        elif callee == "open" or method in _IO_METHODS or callee.split(".")[0] in _HTTP_CLIENTS:
                            rule = "io-in-loop"
                        if not rule or (rule, node.lineno) in seen:
                            continue
                        seen.add((rule, node.lineno))
                        shown = callee or method
                        if rule == "query-in-loop":
                            message = f"`{shown}(...)` runs once per loop iteration in `{qname}` (N+1 query pattern)."
                            suggestion = (
                                "Fetch all rows in one query before the loop (IN clause or JOIN) "
                                "and look them up from a dict."
                            )
                        else:
                            message = f"`{shown}(...)` does I/O on every loop iteration in `{qname}`."
                            suggestion = "Read or request once outside the loop, batch the calls, or cache the result."
                        findings.append(
                            QualityFinding(
                                rule=rule,
                                category=QualityCategory.PERFORMANCE,
                                severity=QualitySeverity.P2 if rule == "query-in-loop" else QualitySeverity.P3,
                                file_path=rel_path,
                                line=node.lineno,
                                symbol=qname,
                                message=message,
                                suggestion=suggestion,
                            )
                        )

            outer_loops = [n for n in loops if _loop_depth(n) >= 3]
            if outer_loops:
                first = min(outer_loops, key=lambda n: n.lineno)
                findings.append(
                    QualityFinding(
                        rule="nested-loops",
                        category=QualityCategory.PERFORMANCE,
                        severity=QualitySeverity.P3,
                        file_path=rel_path,
                        line=first.lineno,
                        symbol=qname,
                        message=f"`{qname}` nests {_loop_depth(first)} loops; cost grows polynomially with input size.",
                        suggestion="Index one of the collections in a dict or set to remove an inner loop.",
                    )
                )
    return sort_findings(findings)


# --------------------------------------------------------------------------- #
# 7. Data modeling
# --------------------------------------------------------------------------- #

_IDENT = r"[`\"\[]?[\w.]+[`\"\]]?"
_CREATE_TABLE_RE = re.compile(
    rf"CREATE\s+(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?({_IDENT})\s*\(", re.IGNORECASE
)
_CREATE_INDEX_RE = re.compile(
    rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?{_IDENT}\s+ON\s+({_IDENT})\s*(?:USING\s+\w+\s*)?\(([^)]*)\)",
    re.IGNORECASE,
)
_SQL_TYPE_RE = (
    r"TEXT|VARCHAR|NVARCHAR|CHAR|NCHAR|CLOB|INT|INTEGER|BIGINT|SMALLINT|TINYINT"
    r"|NUMERIC|DECIMAL|REAL|FLOAT|DOUBLE|BOOLEAN|BOOL|DATE|TIME|DATETIME|TIMESTAMP"
    r"|UUID|JSON|JSONB|BLOB|BYTEA|BINARY|VARBINARY|BIT|SERIAL|BIGSERIAL"
)
_CONSTRAINT_PREFIX_RE = re.compile(
    rf"^(?:CONSTRAINT\s+\S+\s+)?"
    rf"(?:PRIMARY\s+KEY\b|FOREIGN\s+KEY\b|CHECK\s*\("
    rf"|UNIQUE(?:\s+(?:KEY|INDEX))?(?:\s+(?!({_SQL_TYPE_RE})\b)\S+)?\s*\("
    rf"|(?:KEY|INDEX)\s*(?:\(|(?!({_SQL_TYPE_RE})\b)\w+\s*\())",
    re.IGNORECASE,
)
_PAREN_COLUMNS_RE = re.compile(r"\(([^)]*)\)")
_NUMBERED_COLUMN_RE = re.compile(r"^(.*?[a-z])_?(\d+)$")
_KEY_COLUMNS = frozenset({"key", "k", "meta_key", "config_key", "setting_key", "option_name"})
_VALUE_COLUMNS = frozenset({"value", "val", "v", "meta_value", "config_value", "setting_value", "option_value"})
_BOOKKEEPING_COLUMNS = frozenset({"id", "created_at", "updated_at"})
_LIST_COLUMN_SUFFIXES = ("_ids", "_list", "_csv")


def _clean_ident(raw: str) -> str:
    return raw.strip().strip("`\"[]").split(".")[-1].strip("`\"[]").lower()


def _first_column(spec: str) -> str:
    match = _PAREN_COLUMNS_RE.search(spec)
    if not match:
        return ""
    first = match.group(1).split(",")[0].strip()
    return _clean_ident(first.split()[0]) if first else ""


def _split_top_level(body: str) -> list[tuple[int, str]]:
    """Split a column list on commas that are not inside parentheses; keep each part's offset."""
    parts: list[tuple[int, str]] = []
    depth = 0
    start = 0
    for idx, char in enumerate(body):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append((start, body[start:idx]))
            start = idx + 1
    parts.append((start, body[start:]))
    result: list[tuple[int, str]] = []
    for offset, part in parts:
        stripped = part.lstrip()
        if stripped.strip():
            result.append((offset + len(part) - len(stripped), stripped.rstrip()))
    return result


def _sql_sources(snapshot: ProjectSnapshot) -> list[tuple[str, int, str]]:
    """Return `(file, first line, sql text)` for SQL files and DDL strings in Python code."""
    sources = [(path, 1, content) for path, content in snapshot.sql_files().items()]
    for rel_path, tree in snapshot.python_trees(include_tests=False):
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "create table" in node.value.lower():
                    sources.append((rel_path, node.lineno, node.value))
    return sources


def detect_data_modeling_issues(snapshot: ProjectSnapshot) -> list[QualityFinding]:
    """Review `CREATE TABLE` statements found in the project (text only, nothing is executed).

    Flags tables without primary key, foreign keys without index, numbered column
    groups, list-valued columns and relational tables used as key-value stores.
    """
    sources = _sql_sources(snapshot)
    indexed: dict[str, set[str]] = {}
    for _path, _line, text in sources:
        for match in _CREATE_INDEX_RE.finditer(text):
            first = match.group(2).split(",")[0].strip()
            if first:
                indexed.setdefault(_clean_ident(match.group(1)), set()).add(_clean_ident(first.split()[0]))

    findings: list[QualityFinding] = []
    for rel_path, base_line, text in sources:
        for match in _CREATE_TABLE_RE.finditer(text):
            table = _clean_ident(match.group(1))
            body_start = match.end()
            depth, idx = 1, body_start
            while idx < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[idx], 0)
                idx += 1
            if depth:
                continue  # unbalanced statement, skip
            body = text[body_start : idx - 1]

            def line_of(offset: int, _text: str = text, _base: int = base_line) -> int:
                return _base + _text.count("\n", 0, offset)

            table_line = line_of(match.start())
            columns: list[tuple[str, str, int]] = []  # name, definition, line
            has_primary_key = False
            covered = set(indexed.get(table, set()))
            foreign: set[str] = set()
            for offset, part in _split_top_level(body):
                upper = part.upper()
                if _CONSTRAINT_PREFIX_RE.match(part):
                    constraint = re.sub(r"(?i)^CONSTRAINT\s+\S+\s+", "", part)
                    constraint_upper = constraint.upper()
                    if constraint_upper.startswith("PRIMARY"):
                        has_primary_key = True
                        covered.add(_first_column(constraint))
                    elif constraint_upper.startswith("FOREIGN"):
                        foreign.add(_first_column(constraint))
                    elif constraint_upper.startswith(("UNIQUE", "KEY", "INDEX")):
                        covered.add(_first_column(constraint))
                    continue
                name = _clean_ident(part.split()[0])
                columns.append((name, part, line_of(body_start + offset)))
                if "PRIMARY KEY" in upper:
                    has_primary_key = True
                    covered.add(name)
                elif "UNIQUE" in upper:
                    covered.add(name)
                if "REFERENCES" in upper or (name.endswith("_id") and "PRIMARY KEY" not in upper):
                    foreign.add(name)

            if not columns:
                continue
            names = [name for name, _definition, _line in columns]

            if not has_primary_key:
                findings.append(
                    QualityFinding(
                        rule="missing-primary-key",
                        category=QualityCategory.DATA_MODELING,
                        severity=QualitySeverity.P2,
                        file_path=rel_path,
                        line=table_line,
                        symbol=table,
                        message=f"Table `{table}` has no primary key.",
                        suggestion="Declare a primary key so rows can be addressed, deduplicated and referenced.",
                    )
                )

            for name, _definition, line in columns:
                if name in foreign and name not in covered:
                    findings.append(
                        QualityFinding(
                            rule="foreign-key-without-index",
                            category=QualityCategory.DATA_MODELING,
                            severity=QualitySeverity.P2,
                            file_path=rel_path,
                            line=line,
                            symbol=f"{table}.{name}",
                            message=f"Column `{table}.{name}` looks like a foreign key and has no index.",
                            suggestion=(
                                f"Create an index on `{table}({name})`; "
                                "joins and lookups by this column scan the table."
                            ),
                        )
                    )

            groups: dict[str, list[tuple[str, int]]] = {}
            for name, _definition, line in columns:
                numbered = _NUMBERED_COLUMN_RE.match(name)
                if numbered:
                    groups.setdefault(numbered.group(1).rstrip("_"), []).append((name, line))
            for base, members in groups.items():
                if len(members) >= 2:
                    listed = ", ".join(f"`{n}`" for n, _ in members)
                    findings.append(
                        QualityFinding(
                            rule="repeated-column-group",
                            category=QualityCategory.DATA_MODELING,
                            severity=QualitySeverity.P2,
                            file_path=rel_path,
                            line=members[0][1],
                            symbol=table,
                            message=f"Table `{table}` repeats the same attribute in numbered columns ({listed}).",
                            suggestion=(
                                f"Move `{base}` to a child table with one row per value and a foreign key to `{table}`."
                            ),
                        )
                    )

            for name, definition, line in columns:
                if name.endswith(_LIST_COLUMN_SUFFIXES) and re.search(r"(?i)\b(TEXT|VARCHAR|CHAR|CLOB)\b", definition):
                    findings.append(
                        QualityFinding(
                            rule="list-in-column",
                            category=QualityCategory.DATA_MODELING,
                            severity=QualitySeverity.P3,
                            file_path=rel_path,
                            line=line,
                            symbol=f"{table}.{name}",
                            message=f"Column `{table}.{name}` stores a list inside a text field.",
                            suggestion=(
                                "Use an association table (or a native array/JSON type) so values can be queried."
                            ),
                        )
                    )

            name_set = set(names)
            if (
                name_set & _KEY_COLUMNS
                and name_set & _VALUE_COLUMNS
                and name_set - _KEY_COLUMNS - _VALUE_COLUMNS <= _BOOKKEEPING_COLUMNS
            ):
                findings.append(
                    QualityFinding(
                        rule="key-value-in-relational",
                        category=QualityCategory.DATA_MODELING,
                        severity=QualitySeverity.P3,
                        file_path=rel_path,
                        line=table_line,
                        symbol=table,
                        message=f"Table `{table}` is a plain key-value pair stored in a relational table.",
                        suggestion=(
                            "If it is only read by key, a key-value store or a config file fits better; "
                            "if the values have structure, model them as typed columns."
                        ),
                    )
                )
    return sort_findings(findings)


# --------------------------------------------------------------------------- #
# 8. Folder structure
# --------------------------------------------------------------------------- #

_LEFTOVER_NAME_RE = re.compile(
    r"(?:^|[_\-. ])(old|bak|backup|copy|copia|tmp|temp|final|novo|new)\d*$|\(\d+\)$|^(copy|copia|backup|old)[_\- ]"
)
_CATCH_ALL_STEMS = frozenset({"utils", "util", "helpers", "helper", "misc", "common", "stuff", "shared"})


def detect_structure_issues(
    snapshot: ProjectSnapshot, thresholds: QualityThresholds | None = None
) -> list[QualityFinding]:
    """Find confusing folder organization: leftover copies, crowded or deep folders, catch-all modules."""
    limits = thresholds or QualityThresholds()
    findings: list[QualityFinding] = []
    files_per_dir: dict[str, int] = {}
    flagged_dirs: set[str] = set()
    deep_dirs: set[str] = set()

    for rel_path in snapshot.all_paths:
        path = PurePosixPath(rel_path)
        directory = path.parent.as_posix()
        files_per_dir[directory] = files_per_dir.get(directory, 0) + 1

        if _LEFTOVER_NAME_RE.search(path.stem.lower()):
            findings.append(
                QualityFinding(
                    rule="leftover-file-name",
                    category=QualityCategory.STRUCTURE,
                    severity=QualitySeverity.P2,
                    file_path=rel_path,
                    line=1,
                    message=f"File name `{path.name}` suggests a manual copy or a temporary version.",
                    suggestion="Delete the leftover and rely on git history, or rename it after what it contains.",
                )
            )

        parents = [p for p in path.parent.parts if p not in {".", ""}]
        for depth, part in enumerate(parents, start=1):
            dir_path = "/".join(parents[:depth])
            if dir_path not in flagged_dirs and _LEFTOVER_NAME_RE.search(part.lower()):
                flagged_dirs.add(dir_path)
                findings.append(
                    QualityFinding(
                        rule="leftover-directory-name",
                        category=QualityCategory.STRUCTURE,
                        severity=QualitySeverity.P2,
                        file_path=f"{dir_path}/",
                        message=f"Directory `{dir_path}/` suggests a manual copy or a temporary version.",
                        suggestion="Remove it or merge its content into the real module; git keeps the old version.",
                    )
                )
        if len(parents) > limits.max_dir_depth and directory not in deep_dirs:
            deep_dirs.add(directory)
            findings.append(
                QualityFinding(
                    rule="deep-directory",
                    category=QualityCategory.STRUCTURE,
                    severity=QualitySeverity.P3,
                    file_path=f"{directory}/",
                    message=f"Directory `{directory}/` is {len(parents)} levels deep (limit {limits.max_dir_depth}).",
                    suggestion="Flatten the hierarchy: group by feature and keep at most a few levels.",
                )
            )

    for directory, count in sorted(files_per_dir.items()):
        if count > limits.max_files_per_dir:
            shown = "./" if directory == "." else f"{directory}/"
            findings.append(
                QualityFinding(
                    rule="crowded-directory",
                    category=QualityCategory.STRUCTURE,
                    severity=QualitySeverity.P3,
                    file_path=shown,
                    message=f"Directory `{shown}` holds {count} files (limit {limits.max_files_per_dir}).",
                    suggestion="Split the folder into sub-packages by feature or layer.",
                )
            )

    top_level_per_file: dict[str, int] = {}
    for sym in snapshot.symbols:
        if sym.parent_id is None and sym.symbol_type in {*_CALLABLE_TYPES, SymbolType.CLASS}:
            path = sym.location.file_path
            top_level_per_file[path] = top_level_per_file.get(path, 0) + 1
    for rel_path, count in sorted(top_level_per_file.items()):
        if PurePosixPath(rel_path).stem.lower() in _CATCH_ALL_STEMS and count > limits.catch_all_module_symbols:
            findings.append(
                QualityFinding(
                    rule="catch-all-module",
                    category=QualityCategory.STRUCTURE,
                    severity=QualitySeverity.P3,
                    file_path=rel_path,
                    line=1,
                    message=f"`{rel_path}` collects {count} unrelated top-level definitions.",
                    suggestion="Move each group of functions next to the feature that uses it.",
                )
            )
    return sort_findings(findings)


# --------------------------------------------------------------------------- #
# 9. Branch organization
# --------------------------------------------------------------------------- #

_PROTECTED_BRANCHES = frozenset({"main", "master", "develop", "dev", "trunk"})
_BRANCH_NAME_RE = re.compile(
    r"^(?:release|hotfix)/[A-Za-z0-9._-]+$"
    r"|^(?:feat|feature|fix|bugfix|chore|docs|refactor|test|perf|ci|build|style|revert)/[a-z0-9][a-z0-9._/-]*$"
)


def detect_branch_issues(
    branches: list[BranchInfo],
    thresholds: QualityThresholds | None = None,
    direct_commits_on_default: list[str] | None = None,
) -> list[QualityFinding]:
    """Review branch organization from caller-supplied facts.

    Flags names outside the `type/short-description` convention, long-lived or
    stale branches, and commits made directly on the default branch.
    """
    limits = thresholds or QualityThresholds()
    findings: list[QualityFinding] = []
    default_name = next((b.name for b in branches if b.is_default), "main")

    for branch in branches:
        protected = branch.is_default or branch.name in _PROTECTED_BRANCHES
        anchor = f"branch:{branch.name}"
        if not protected and not _BRANCH_NAME_RE.match(branch.name):
            findings.append(
                QualityFinding(
                    rule="branch-name-convention",
                    category=QualityCategory.BRANCHING,
                    severity=QualitySeverity.P3,
                    file_path=anchor,
                    message=f"Branch `{branch.name}` does not follow `type/short-description`.",
                    suggestion="Rename it to `feat/...`, `fix/...`, `chore/...`, `docs/...` or `refactor/...`.",
                )
            )
        if protected:
            continue
        if branch.age_days is not None and branch.age_days > limits.long_lived_branch_days:
            findings.append(
                QualityFinding(
                    rule="long-lived-branch",
                    category=QualityCategory.BRANCHING,
                    severity=QualitySeverity.P2,
                    file_path=anchor,
                    message=(
                        f"Branch `{branch.name}` has been open for {branch.age_days:.0f} days "
                        f"(limit {limits.long_lived_branch_days})."
                    ),
                    suggestion="Merge it in small pull requests behind a flag, or rebase and close it.",
                )
            )
        elif (
            branch.last_commit_age_days is not None and branch.last_commit_age_days > limits.long_lived_branch_days
        ):
            findings.append(
                QualityFinding(
                    rule="stale-branch",
                    category=QualityCategory.BRANCHING,
                    severity=QualitySeverity.P3,
                    file_path=anchor,
                    message=f"Branch `{branch.name}` has had no commit for {branch.last_commit_age_days:.0f} days.",
                    suggestion="Delete it if it was merged or abandoned; otherwise finish and merge it.",
                )
            )

    commits = [c for c in (direct_commits_on_default or []) if c.strip()]
    if commits:
        findings.append(
            QualityFinding(
                rule="direct-commit-on-default-branch",
                category=QualityCategory.BRANCHING,
                severity=QualitySeverity.P1,
                file_path=f"branch:{default_name}",
                message=(
                    f"{len(commits)} commit(s) went straight to `{default_name}` without a pull request: "
                    + "; ".join(c.strip()[:80] for c in commits[:3])
                ),
                suggestion=f"Protect `{default_name}` and require pull requests with review and green checks.",
            )
        )
    return sort_findings(findings)


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #


def run_quality_detectors(
    snapshot: ProjectSnapshot,
    thresholds: QualityThresholds | None = None,
    branches: list[BranchInfo] | None = None,
    direct_commits_on_default: list[str] | None = None,
) -> list[QualityFinding]:
    """Run every detector over a snapshot and return the findings ordered by priority."""
    limits = thresholds or QualityThresholds()
    findings = [
        *detect_duplicate_functions(snapshot, limits),
        *detect_useless_wrappers(snapshot),
        *detect_temporary_solutions(snapshot),
        *detect_readability_issues(snapshot, limits),
        *detect_over_engineering(snapshot),
        *detect_performance_smells(snapshot),
        *detect_data_modeling_issues(snapshot),
        *detect_structure_issues(snapshot, limits),
    ]
    if branches or direct_commits_on_default:
        findings.extend(detect_branch_issues(branches or [], limits, direct_commits_on_default))
    return sort_findings(findings)


__all__ = [
    "cyclomatic_complexity",
    "detect_branch_issues",
    "detect_data_modeling_issues",
    "detect_duplicate_functions",
    "detect_over_engineering",
    "detect_performance_smells",
    "detect_readability_issues",
    "detect_structure_issues",
    "detect_temporary_solutions",
    "detect_useless_wrappers",
    "max_nesting_depth",
    "normalize_code_tokens",
    "run_quality_detectors",
    "token_similarity",
]
