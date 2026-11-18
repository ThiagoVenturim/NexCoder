"""Repository scanner: detects failing tests, coverage deficits, TODOs, outdated deps, security risks, and lint."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from nexcoder_continuous_improvement.issues.planning_bridge import FindingCategory, ImprovementFinding

TODO_PATTERN = re.compile(r"#\s*(TODO|FIXME|HACK|XXX)\b:?\s*(.*)", re.IGNORECASE)

DANGEROUS_SECURITY_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\beval\s*\("), "Dynamic code evaluation via eval()", "critical"),
    (re.compile(r"\bexec\s*\("), "Dynamic execution via exec()", "critical"),
    (re.compile(r"subprocess\.\w+\(.*shell\s*=\s*True"), "Shell injection vector with shell=True", "high"),
    (
        re.compile(r"(?:api_key|secret|password|token)\s*=\s*['\"][a-zA-Z0-9_\-]{16,}['\"]", re.IGNORECASE),
        "Possible hardcoded secret or token literal",
        "high",
    ),
]

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    ".nexhub-floors",
}


class RepoScanner:
    """Scans repository source trees to surface actionable continuous improvement findings."""

    def __init__(self, root_path: str | Path = ".") -> None:
        self.root_path = Path(root_path).resolve()

    def scan_all(self) -> list[ImprovementFinding]:
        """Perform a comprehensive scan across all supported inspection dimensions."""
        findings: list[ImprovementFinding] = []
        findings.extend(self.scan_todos())
        findings.extend(self.scan_dependencies())
        findings.extend(self.scan_security_risks())
        findings.extend(self.scan_lint_and_hygiene())
        findings.extend(self.scan_test_coverage_gaps())
        return findings

    def scan_todos(self) -> list[ImprovementFinding]:
        """Scan Python and markdown files for TODO, FIXME, HACK, or XXX markers."""
        findings: list[ImprovementFinding] = []
        for path in self._walk_files(suffixes={".py", ".md", ".sh", ".toml"}):
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            rel_path = str(path.relative_to(self.root_path))
            for line_no, line in enumerate(content.splitlines(), start=1):
                match = TODO_PATTERN.search(line)
                if match:
                    tag = match.group(1).upper()
                    comment = match.group(2).strip() or "Resolve marked code debt item"
                    layer = self._infer_layer(path)
                    priority = "high" if tag in ("FIXME", "XXX") else "medium"

                    findings.append(
                        ImprovementFinding(
                            category=FindingCategory.TODO_DEBT,
                            title=f"Resolve {tag} in {path.name}: {comment[:60]}",
                            description=f"Technical debt marker '{tag}' found in {rel_path}:{line_no}: {comment}",
                            layer=layer,
                            recommended_agent="code-refactorer",
                            estimate_points=2 if tag == "TODO" else 3,
                            priority=priority,
                            acceptance_given=f"A debt marker '{tag}' exists in {rel_path}:{line_no}",
                            acceptance_when=f"The underlying debt '{comment}' is refactored or addressed",
                            acceptance_then=f"The {tag} marker is removed and all tests pass offline",
                            file_path=rel_path,
                            line_number=line_no,
                            metadata={"marker_tag": tag, "line": line_no, "file": rel_path},
                        )
                    )
        return findings

    def scan_dependencies(self) -> list[ImprovementFinding]:
        """Inspect pyproject.toml and requirements files for unpinned or outdated dependency declarations."""
        findings: list[ImprovementFinding] = []
        for path in self._walk_files(suffixes={".toml", ".txt"}):
            if path.name not in ("pyproject.toml", "requirements.txt"):
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            rel_path = str(path.relative_to(self.root_path))
            layer = self._infer_layer(path)

            for line_no, line in enumerate(content.splitlines(), start=1):
                stripped = line.strip()
                # Check for unpinned direct dependencies (e.g. "package" without version specifier in dependencies)
                is_unpinned = (
                    stripped.startswith('"')
                    and stripped.endswith('",')
                    and not any(op in stripped for op in (">=", "==", "<=", "~=", "^"))
                )
                if is_unpinned:
                    dep_name = stripped.strip('",')
                    if dep_name.isidentifier() or "-" in dep_name:
                        findings.append(
                            ImprovementFinding(
                                category=FindingCategory.DEPENDENCY,
                                title=f"Pin dependency '{dep_name}' in {path.name}",
                                description=(
                                    f"Dependency '{dep_name}' in {rel_path}:{line_no} lacks version constraints."
                                ),
                                layer=layer,
                                recommended_agent="sec-fixer",
                                estimate_points=1,
                                priority="medium",
                                acceptance_given=f"Dependency '{dep_name}' has no lower/upper version bounds",
                                acceptance_when=f"Explicit version constraint is specified in {rel_path}",
                                acceptance_then="Dependency resolves cleanly and installation passes offline",
                                file_path=rel_path,
                                line_number=line_no,
                                metadata={"dependency": dep_name, "file": rel_path},
                            )
                        )
        return findings

    def scan_security_risks(self) -> list[ImprovementFinding]:
        """Inspect source files for dangerous security calls, injection vectors, and hardcoded secrets."""
        findings: list[ImprovementFinding] = []
        for path in self._walk_files(suffixes={".py"}):
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            rel_path = str(path.relative_to(self.root_path))
            layer = self._infer_layer(path)

            for line_no, line in enumerate(content.splitlines(), start=1):
                # Ignore test files for deliberate test cases of security scanners
                if "tests" in path.parts:
                    continue

                for pattern, desc, severity in DANGEROUS_SECURITY_PATTERNS:
                    if pattern.search(line):
                        findings.append(
                            ImprovementFinding(
                                category=FindingCategory.SECURITY,
                                title=f"Remediate security risk in {path.name}: {desc}",
                                description=f"Security alert at {rel_path}:{line_no}: {desc}",
                                layer=layer,
                                recommended_agent="sec-fixer",
                                estimate_points=3,
                                priority=severity,
                                acceptance_given=f"Insecure construct '{desc}' present at {rel_path}:{line_no}",
                                acceptance_when="Construct is replaced with safe alternative or removed",
                                acceptance_then="Security check passes cleanly with no residual risk",
                                file_path=rel_path,
                                line_number=line_no,
                                metadata={"severity": severity, "rule": desc, "file": rel_path},
                            )
                        )
        return findings

    def scan_lint_and_hygiene(self) -> list[ImprovementFinding]:
        """Scan Python files for syntax errors or hygiene smells like wildcard imports."""
        findings: list[ImprovementFinding] = []
        for path in self._walk_files(suffixes={".py"}):
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            rel_path = str(path.relative_to(self.root_path))
            layer = self._infer_layer(path)

            # Check AST parse validity
            try:
                tree = ast.parse(content, filename=str(path))
            except SyntaxError as exc:
                findings.append(
                    ImprovementFinding(
                        category=FindingCategory.LINT,
                        title=f"Fix syntax error in {path.name}",
                        description=f"Syntax error at {rel_path}:{exc.lineno}: {exc.msg}",
                        layer=layer,
                        recommended_agent="code-refactorer",
                        estimate_points=2,
                        priority="high",
                        acceptance_given=f"File {rel_path} fails AST parsing",
                        acceptance_when=f"Syntax error at line {exc.lineno} is repaired",
                        acceptance_then="File parses validly and passes ruff check",
                        file_path=rel_path,
                        line_number=exc.lineno,
                        metadata={"error": str(exc), "file": rel_path},
                    )
                )
                continue

            # Check for wildcard imports: `from module import *`
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name == "*":
                            findings.append(
                                ImprovementFinding(
                                    category=FindingCategory.LINT,
                                    title=f"Remove wildcard import in {path.name}",
                                    description=(
                                        f"Wildcard import 'from {node.module} import *' at {rel_path}:{node.lineno}"
                                    ),
                                    layer=layer,
                                    recommended_agent="code-refactorer",
                                    estimate_points=1,
                                    priority="low",
                                    acceptance_given=f"Wildcard import exists in {rel_path}:{node.lineno}",
                                    acceptance_when="Specific symbol imports are declared explicitly",
                                    acceptance_then="Wildcard import is eliminated and lint checks pass",
                                    file_path=rel_path,
                                    line_number=node.lineno,
                                    metadata={"module": node.module, "file": rel_path},
                                )
                            )
        return findings

    def scan_test_coverage_gaps(self) -> list[ImprovementFinding]:
        """Detect packages or core modules lacking corresponding unit test files."""
        findings: list[ImprovementFinding] = []
        packages_dir = self.root_path / "packages"
        if not packages_dir.is_dir():
            return findings

        for pkg in packages_dir.iterdir():
            if not pkg.is_dir():
                continue
            src_dir = pkg / "src"
            tests_dir = pkg / "tests"

            if src_dir.is_dir() and not tests_dir.is_dir():
                findings.append(
                    ImprovementFinding(
                        category=FindingCategory.LOW_COVERAGE,
                        title=f"Add unit test suite for package '{pkg.name}'",
                        description=f"Package '{pkg.name}' has source code under src/ but lacks a tests/ directory.",
                        layer=pkg.name,
                        recommended_agent="test-writer",
                        estimate_points=3,
                        priority="high",
                        acceptance_given=f"Package {pkg.name} has no automated tests directory",
                        acceptance_when="Unit test directory and initial test module are established",
                        acceptance_then="Test suite runs offline and passes via python -m pytest",
                        file_path=str(pkg.relative_to(self.root_path)),
                        line_number=1,
                        metadata={"package": pkg.name},
                    )
                )
        return findings

    def _walk_files(self, suffixes: set[str]) -> list[Path]:
        results: list[Path] = []
        for path in self.root_path.rglob("*"):
            if not path.is_file():
                continue
            if any(part in IGNORE_DIRS for part in path.parts):
                continue
            if path.suffix.lower() in suffixes:
                results.append(path)
        return results

    def _infer_layer(self, path: Path) -> str:
        """Infer nexcoder layer name from file path."""
        parts = path.parts
        if "packages" in parts:
            idx = parts.index("packages")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return "core"
