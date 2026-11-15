"""Static verification check for authorization gate enforcement (Issue #106).

Ensures that active scanning and raw network operations only occur inside the
authorized gate module (packages/security/.../gate/, packages/control/.../approval/,
and MultiScannerEngine). Any active scan or network probe outside the gate module
fails pre-commit and CI checks.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Directories and files permitted to implement the gate and low-level scanners
GATE_ALLOWED_PREFIXES = (
    "packages/security/src/nexcoder_security/gate/",
    "packages/security/src/nexcoder_security/scanners/",
    "packages/security/src/nexcoder_security/cli.py",
    "packages/security/src/nexcoder_security/review.py",
    "packages/security/src/nexcoder_security/agents/",
    "packages/control/src/nexcoder_control/approval/",
    "packages/control/src/nexcoder_control/auth/",
    "packages/core/src/nexcoder_core/reports.py",
    "packages/core/src/nexcoder_core/retrieval/embeddings.py",
    "packages/ideation/src/nexcoder_ideation/search/providers.py",
    "packages/planning/src/nexcoder_planning/adapters/",
    "packages/capture/src/nexcoder_capture/web/",
)

PROHIBITED_SCAN_COMMANDS = frozenset({
    "nmap",
    "masscan",
    "zmap",
    "nikto",
    "hping",
    "hping3",
    "sqlmap",
})

SCANNER_CLASS_NAMES = frozenset({
    "BanditScanner",
    "SemgrepScanner",
    "GitleaksScanner",
    "OSVScanner",
    "PipAuditScanner",
    "TrivyScanner",
    "SyftScanner",
})


def _normalize_path(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def is_test_file(path_str: str) -> bool:
    norm = _normalize_path(path_str)
    return "/tests/" in norm or norm.startswith("tests/") or Path(norm).name.startswith("test_")


def is_gate_allowed_module(path_str: str) -> bool:
    norm = _normalize_path(path_str)
    if is_test_file(norm):
        return True
    return any(norm.startswith(prefix) or f"/{prefix}" in norm for prefix in GATE_ALLOWED_PREFIXES)


class GateEnforcementVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str) -> None:
        self.file_path = _normalize_path(file_path)
        self.violations: list[tuple[int, str]] = []
        self._is_gate_allowed = is_gate_allowed_module(self.file_path)
        self._is_security_package = "packages/security/" in self.file_path

    def visit_Call(self, node: ast.Call) -> None:
        # Check raw socket calls
        call_name = self._get_call_name(node.func)
        if call_name:
            if not self._is_gate_allowed:
                if call_name in ("socket.socket", "socket.create_connection", "socket.connect"):
                    self.violations.append(
                        (node.lineno, f"Direct raw socket call '{call_name}' outside gate module.")
                    )
                elif call_name in ("urllib.request.urlopen", "urllib.request.urlretrieve"):
                    self.violations.append(
                        (node.lineno, f"Direct urllib active network call '{call_name}' outside gate module.")
                    )

            # Check direct scanner class instantiation outside packages/security
            if not self._is_security_package and not is_test_file(self.file_path):
                base_name = call_name.split(".")[-1]
                if base_name in SCANNER_CLASS_NAMES:
                    self.violations.append(
                        (
                            node.lineno,
                            f"Direct scanner instantiation '{base_name}' outside security package. "
                            "Active scans must pass through MultiScannerEngine or gate_active_scan.",
                        )
                    )

        # Check subprocess calls invoking prohibited active scanning tools
        if not self._is_gate_allowed:
            if call_name and any(call_name.startswith(p) for p in ("subprocess.", "os.system", "os.popen")):
                cmd_literal = self._extract_first_arg_literal(node)
                if cmd_literal:
                    cmd_lower = cmd_literal.lower()
                    for tool in PROHIBITED_SCAN_COMMANDS:
                        if tool in cmd_lower:
                            self.violations.append(
                                (
                                    node.lineno,
                                    f"Prohibited active scan tool '{tool}' invocation outside authorization gate.",
                                )
                            )

        self.generic_visit(node)

    def _get_call_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            val_name = self._get_call_name(node.value)
            if val_name:
                return f"{val_name}.{node.attr}"
            return node.attr
        return None

    def _extract_first_arg_literal(self, node: ast.Call) -> str | None:
        if not node.args:
            return None
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        if isinstance(first, ast.List):
            words: list[str] = []
            for elt in first.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    words.append(elt.value)
            return " ".join(words)
        return None


def check_file(file_path: Path) -> list[tuple[int, str]]:
    norm = _normalize_path(file_path)
    if not norm.endswith(".py"):
        return []
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as exc:
        return [(1, f"Failed to parse python AST: {exc}")]

    visitor = GateEnforcementVisitor(norm)
    visitor.visit(tree)
    return visitor.violations


def find_files_to_check(args: list[str]) -> list[Path]:
    if args:
        targets: list[Path] = []
        for a in args:
            p = Path(a)
            if p.is_file() and p.suffix == ".py":
                targets.append(p)
            elif p.is_dir():
                targets.extend(p.rglob("*.py"))
        return targets

    root = Path(__file__).resolve().parent.parent
    packages_dir = root / "packages"
    if packages_dir.exists():
        return list(packages_dir.rglob("*.py"))
    return []


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    files = find_files_to_check(args)
    total_violations = 0

    for file_path in files:
        violations = check_file(file_path)
        if violations:
            for lineno, msg in violations:
                print(f"[AUTH GATE VIOLATION] {_normalize_path(file_path)}:{lineno}: {msg}")
                total_violations += 1

    if total_violations > 0:
        print(f"FAILED: Found {total_violations} authorization gate enforcement violation(s).")
        return 1

    print("PASSED: All files comply with authorization gate enforcement policy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
