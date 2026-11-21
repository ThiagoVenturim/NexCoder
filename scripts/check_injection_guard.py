#!/usr/bin/env python3
"""Static injection guard scanner.

Blocks commits and CI builds that introduce:
1. SQL queries built with f-strings, format(), or string concatenation (+).
2. eval() or exec() with dynamic variables.
3. subprocess calls with shell=True or os.system/popen.
4. Direct LLM / tool invocations bypassing PromptFirewall.

Exempt paths: scanners, fixer agent, docs, and security test fixtures describing flaws.
"""

from __future__ import annotations

import ast
import fnmatch
import re
import sys
from pathlib import Path
from typing import NamedTuple

ALLOWLIST_PATTERNS = [
    "*/packages/security/src/nexcoder_security/scanners/*",
    "*/packages/security/src/nexcoder_security/agents/fixer.py",
    "packages/security/src/nexcoder_security/scanners/*",
    "packages/security/src/nexcoder_security/agents/fixer.py",
    "*/docs/*",
    "docs/*",
    "*.md",
    "*.rst",
    "*/tests/fixtures/*",
    "tests/fixtures/*",
    "*/packages/security/tests/test_security_review.py",
    "packages/security/tests/test_security_review.py",
    "*/packages/security/tests/test_scanners.py",
    "packages/security/tests/test_scanners.py",
    "*/packages/security/tests/test_agents.py",
    "packages/security/tests/test_agents.py",
    "*/packages/security/tests/test_cli.py",
    "packages/security/tests/test_cli.py",
    "*/packages/agents/tests/test_pipelines_ready.py",
    "packages/agents/tests/test_pipelines_ready.py",
    "*/packages/agents/tests/test_oss_contribution.py",
    "packages/agents/tests/test_oss_contribution.py",
    "*/packages/interfaces/tests/test_tools.py",
    "packages/interfaces/tests/test_tools.py",
    "*/packages/security/tests/test_injection_guard.py",
    "packages/security/tests/test_injection_guard.py",
    "*/tests/test_injection_guard.py",
]

_SQL_KEYWORDS = re.compile(
    r"\b(?:SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+TABLE|CREATE\s+TABLE|ALTER\s+TABLE)\b",
    re.IGNORECASE,
)


class Violation(NamedTuple):
    file_path: str
    line: int
    rule: str
    message: str


def is_path_allowlisted(path: str | Path) -> bool:
    normalized = str(path).replace("\\", "/")
    for pattern in ALLOWLIST_PATTERNS:
        if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(f"*/{normalized}", pattern):
            return True
        if pattern.endswith("/*") and pattern[:-2] in normalized:
            return True
        if pattern in normalized:
            return True
    return False


def _is_sql_string(text: str) -> bool:
    return bool(_SQL_KEYWORDS.search(text))


class SecurityGuardVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        # Check if an f-string contains SQL keywords and dynamic values
        parts_text: list[str] = []
        has_expression = False
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                parts_text.append(part.value)
            elif isinstance(part, ast.FormattedValue):
                has_expression = True
                parts_text.append("{var}")
        full_text = "".join(parts_text)
        if has_expression and _is_sql_string(full_text):
            self.violations.append(
                Violation(
                    file_path=self.file_path,
                    line=node.lineno,
                    rule="sql-injection.fstring-query",
                    message="SQL query assembled using dynamic f-string. Use parameterized queries.",
                )
            )
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        # Check if string concatenation (+) is used to construct SQL queries
        if isinstance(node.op, ast.Add):
            left_is_str = isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)
            right_is_str = isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)
            if left_is_str and _is_sql_string(str(node.left.value)):
                self.violations.append(
                    Violation(
                        file_path=self.file_path,
                        line=node.lineno,
                        rule="sql-injection.concat-query",
                        message="SQL query assembled via string concatenation (+). Use parameterized queries.",
                    )
                )
            elif right_is_str and _is_sql_string(str(node.right.value)):
                self.violations.append(
                    Violation(
                        file_path=self.file_path,
                        line=node.lineno,
                        rule="sql-injection.concat-query",
                        message="SQL query assembled via string concatenation (+). Use parameterized queries.",
                    )
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func_name = ""
        method_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            method_name = node.func.attr
            if isinstance(node.func.value, ast.Name):
                func_name = f"{node.func.value.id}.{method_name}"

        # 1. SQL execution checks on .execute(), .executemany(), .raw()
        if method_name in ("execute", "executemany", "raw", "raw_query"):
            if node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.JoinedStr):
                    self.violations.append(
                        Violation(
                            file_path=self.file_path,
                            line=node.lineno,
                            rule="sql-injection.execute-fstring",
                            message=f"Database .{method_name}() called with an f-string. Use parameterized queries.",
                        )
                    )
                elif isinstance(arg0, ast.BinOp) and isinstance(arg0.op, ast.Add):
                    self.violations.append(
                        Violation(
                            file_path=self.file_path,
                            line=node.lineno,
                            rule="sql-injection.execute-concat",
                            message=f"Database .{method_name}() called with string concatenation (+).",
                        )
                    )
                elif isinstance(arg0, ast.Call) and isinstance(arg0.func, ast.Attribute) and arg0.func.attr == "format":
                    self.violations.append(
                        Violation(
                            file_path=self.file_path,
                            line=node.lineno,
                            rule="sql-injection.execute-format",
                            message=f"Database .{method_name}() called with .format(). Use parameterized queries.",
                        )
                    )

        # 2. eval() and exec() with dynamic input
        if func_name in ("eval", "exec") or method_name in ("eval", "exec"):
            is_static_constant = (
                node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
            )
            if not is_static_constant:
                self.violations.append(
                    Violation(
                        file_path=self.file_path,
                        line=node.lineno,
                        rule="security.dynamic-execution",
                        message=f"Dangerous dynamic code execution via {func_name or method_name}(). Avoid eval/exec.",
                    )
                )

        # 3. subprocess shell=True or os.system/popen
        is_os_call = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
        )
        if (func_name in ("os.system", "os.popen") or method_name in ("system", "popen")) and is_os_call:
            self.violations.append(
                Violation(
                    file_path=self.file_path,
                    line=node.lineno,
                    rule="command-injection.os-system",
                    message=f"os.{method_name}() allows command injection. Use subprocess.run with argument list.",
                )
            )

        for kw in node.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                self.violations.append(
                    Violation(
                        file_path=self.file_path,
                        line=node.lineno,
                        rule="command-injection.shell-true",
                        message="subprocess called with shell=True. Pass command arguments as list with shell=False.",
                    )
                )

        # 4. Direct LLM invocation with unvalidated concatenated prompt
        if method_name in ("invoke", "ainvoke"):
            # Check if caller looks like an llm/model and passes an f-string or concat
            caller_name = ""
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                caller_name = node.func.value.id.lower()
            if any(k in caller_name for k in ("llm", "chat_model", "model", "client", "agent")) and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.JoinedStr):
                    self.violations.append(
                        Violation(
                            file_path=self.file_path,
                            line=node.lineno,
                            rule="prompt-injection.unfirewalled-invoke",
                            message="LLM invoked with unescaped f-string prompt. Route prompts through PromptFirewall.",
                        )
                    )
                elif isinstance(arg0, ast.BinOp) and isinstance(arg0.op, ast.Add):
                    self.violations.append(
                        Violation(
                            file_path=self.file_path,
                            line=node.lineno,
                            rule="prompt-injection.unfirewalled-invoke",
                            message="LLM invoked with concatenated prompt. Route prompts through PromptFirewall.",
                        )
                    )

        # 5. Direct tool invocation without schema validation
        if func_name in ("call_tool", "execute_tool", "dispatch_tool"):
            if node.args and isinstance(node.args[0], (ast.Name, ast.JoinedStr)):
                self.violations.append(
                    Violation(
                        file_path=self.file_path,
                        line=node.lineno,
                        rule="prompt-injection.unvalidated-tool-call",
                        message=f"Tool invocation {func_name}() must use PromptFirewall.validate_tool_call.",
                    )
                )

        self.generic_visit(node)


def scan_file(file_path: Path) -> list[Violation]:
    if is_path_allowlisted(file_path):
        return []
    if file_path.suffix.lower() != ".py":
        return []
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    visitor = SecurityGuardVisitor(str(file_path))
    visitor.visit(tree)
    return visitor.violations


def get_files_to_scan(args: list[str]) -> list[Path]:
    if args:
        paths = []
        for a in args:
            p = Path(a)
            if p.is_file():
                paths.append(p)
            elif p.is_dir():
                paths.extend(p.rglob("*.py"))
        return paths

    # Default: scan monorepo packages and scripts
    root = Path.cwd()
    candidates: list[Path] = []
    for search_dir in ("packages", "scripts"):
        p = root / search_dir
        if p.exists():
            candidates.extend(p.rglob("*.py"))
    return sorted(candidates)


def main() -> int:
    files = get_files_to_scan(sys.argv[1:])
    all_violations: list[Violation] = []

    for fpath in files:
        violations = scan_file(fpath)
        all_violations.extend(violations)

    if not all_violations:
        print(f"Injection guard passed cleanly ({len(files)} files checked).")
        return 0

    print(f"FAILED: Injection guard detected {len(all_violations)} violation(s):", file=sys.stderr)
    for v in all_violations:
        print(f"  {v.file_path}:{v.line}: [{v.rule}] {v.message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
