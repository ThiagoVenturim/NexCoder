"""Unit and contract test generator and runner for owned target source code."""

from __future__ import annotations

import ast
import importlib.util
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexcoder_core.sandbox import resolve_inside
from nexcoder_security.models import Finding, FindingCategory, Location, Remediation, Severity

from nexcoder_testing.models import (
    GeneratedTestArtifact,
    TestCaseExecution,
    TestScope,
)


@dataclass
class DiscoveredFunction:
    """Metadata extracted from AST for a target Python function."""

    module_path: Path
    relative_path: str
    name: str
    lineno: int
    args: list[tuple[str, str]]
    has_defaults: int


class UnitAndContractRunner:
    """Generates and executes unit and boundary contract tests from target source code."""

    def discover_functions(
        self,
        target_root: Path,
        module_paths: list[str] | None = None,
    ) -> list[DiscoveredFunction]:
        """Discover testable functions inside the target root using AST inspection."""
        root = target_root.resolve()
        py_files: list[Path] = []

        if module_paths:
            for rel in module_paths:
                resolved = resolve_inside(root, rel)
                if resolved.is_file() and resolved.suffix == ".py":
                    py_files.append(resolved)
        else:
            ignored = {"tests", "__pycache__", "venv", ".venv"}
            for candidate in sorted(root.rglob("*.py")):
                if any(part.startswith(".") or part in ignored for part in candidate.parts):
                    continue
                if candidate.name.startswith("test_"):
                    continue
                resolved = resolve_inside(root, candidate)
                py_files.append(resolved)

        discovered: list[DiscoveredFunction] = []
        for py_file in py_files:
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue

            rel_str = str(py_file.relative_to(root)).replace("\\", "/")
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and not node.name.startswith("_") and node.name != "main":
                    arg_specs: list[tuple[str, str]] = []
                    for arg in node.args.args:
                        if arg.arg in ("self", "cls"):
                            continue
                        ann = ast.unparse(arg.annotation) if arg.annotation else "Any"
                        arg_specs.append((arg.arg, ann))
                    discovered.append(
                        DiscoveredFunction(
                            module_path=py_file,
                            relative_path=rel_str,
                            name=node.name,
                            lineno=node.lineno,
                            args=arg_specs,
                            has_defaults=len(node.args.defaults),
                        )
                    )
        return discovered

    def _build_vectors(self, fn: DiscoveredFunction) -> list[tuple[str, dict[str, Any], bool]]:
        """Construct normal and boundary input vectors for a discovered function."""
        required_count = max(0, len(fn.args) - fn.has_defaults)
        active_args = fn.args[: max(required_count, len(fn.args))]

        happy_kwargs: dict[str, Any] = {}
        zero_kwargs: dict[str, Any] = {}
        negative_kwargs: dict[str, Any] = {}

        for arg_name, ann in active_args:
            ann_lower = ann.lower()
            name_lower = arg_name.lower()
            if "float" in ann_lower or "price" in name_lower or "pct" in name_lower or "discount" in name_lower:
                happy_kwargs[arg_name] = 10.0 if "pct" in name_lower or "discount" in name_lower else 25.0
                zero_kwargs[arg_name] = 0.0
                negative_kwargs[arg_name] = -5.0
            elif "int" in ann_lower or "count" in name_lower or "size" in name_lower or "quantity" in name_lower:
                happy_kwargs[arg_name] = 2
                zero_kwargs[arg_name] = 0
                negative_kwargs[arg_name] = -1
            elif "bool" in ann_lower:
                happy_kwargs[arg_name] = True
                zero_kwargs[arg_name] = False
                negative_kwargs[arg_name] = False
            else:
                happy_kwargs[arg_name] = "SKU-100"
                zero_kwargs[arg_name] = ""
                negative_kwargs[arg_name] = "   "

        vectors: list[tuple[str, dict[str, Any], bool]] = [
            ("happy_path", happy_kwargs, True),
            ("zero_or_empty_boundary", zero_kwargs, False),
            ("negative_or_whitespace_boundary", negative_kwargs, False),
        ]
        return vectors

    def _synthesize_pytest_code(self, functions: list[DiscoveredFunction]) -> str:
        """Synthesize an executable pytest suite covering discovered functions and contracts."""
        lines: list[str] = [
            '"""Auto-generated unit and contract test suite by nexcoder-testing."""',
            "",
            "from __future__ import annotations",
            "",
            "import pytest",
            "",
        ]

        for fn in functions:
            mod_import = fn.relative_path.removesuffix(".py").replace("/", ".")
            vectors = self._build_vectors(fn)
            happy_kwargs = vectors[0][1]
            zero_kwargs = vectors[1][1]

            happy_call = ", ".join(f"{k}={v!r}" for k, v in happy_kwargs.items())
            zero_call = ", ".join(f"{k}={v!r}" for k, v in zero_kwargs.items())

            lines.extend(
                [
                    f"def test_{fn.name}_happy_path() -> None:",
                    f"    from {mod_import} import {fn.name}",
                    f"    result = {fn.name}({happy_call})",
                    "    assert result is not None",
                    "",
                    f"def test_{fn.name}_zero_boundary_contract() -> None:",
                    f"    from {mod_import} import {fn.name}",
                    "    try:",
                    f"        {fn.name}({zero_call})",
                    "    except (ValueError, TypeError):",
                    "        pass",
                    "",
                ]
            )

        if not functions:
            lines.extend(
                [
                    "def test_placeholder_contract() -> None:",
                    "    assert True",
                    "",
                ]
            )

        return "\n".join(lines)

    def run(
        self,
        target_root: Path,
        module_paths: list[str] | None = None,
        agent_id: str = "agent-unit",
    ) -> tuple[list[TestCaseExecution], list[Finding], list[GeneratedTestArtifact]]:
        """Discover functions, synthesize unit/contract tests, and execute vectors in-process."""
        functions = self.discover_functions(target_root, module_paths=module_paths)
        test_cases: list[TestCaseExecution] = []
        findings: list[Finding] = []
        artifacts: list[GeneratedTestArtifact] = []

        pytest_content = self._synthesize_pytest_code(functions)
        artifacts.append(
            GeneratedTestArtifact(
                name=f"{agent_id}_unit_contract_suite",
                scope=TestScope.UNIT,
                file_name=f"test_generated_unit_{agent_id.replace('-', '_')}.py",
                content=pytest_content,
                target_reference=str(target_root),
            )
        )

        loaded_modules: dict[Path, Any] = {}
        for fn in functions:
            if fn.module_path not in loaded_modules:
                try:
                    spec = importlib.util.spec_from_file_location(
                        f"_nexcoder_target_{fn.module_path.stem}",
                        fn.module_path,
                    )
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        import sys

                        sys.modules[spec.name] = mod
                        spec.loader.exec_module(mod)
                        loaded_modules[fn.module_path] = mod
                except Exception as exc:
                    test_cases.append(
                        TestCaseExecution(
                            test_id=f"{agent_id}:import:{fn.relative_path}",
                            scope=TestScope.UNIT,
                            name=f"import_{fn.module_path.stem}",
                            target=fn.relative_path,
                            passed=False,
                            error_message=str(exc),
                        )
                    )
                    continue

            mod = loaded_modules.get(fn.module_path)
            if mod is None:
                continue
            callable_fn = getattr(mod, fn.name, None)
            if not callable(callable_fn):
                continue

            for vec_name, kwargs, is_happy in self._build_vectors(fn):
                t0 = time.perf_counter()
                test_id = f"{agent_id}:unit:{fn.name}:{vec_name}"
                try:
                    res = callable_fn(**kwargs)
                    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                    test_cases.append(
                        TestCaseExecution(
                            test_id=test_id,
                            scope=TestScope.UNIT,
                            name=f"test_{fn.name}_{vec_name}",
                            target=f"{fn.relative_path}:{fn.name}",
                            passed=True,
                            duration_ms=elapsed_ms,
                            details={"kwargs": kwargs, "result": repr(res)},
                        )
                    )
                except (ValueError, TypeError) as controlled_exc:
                    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                    passed = not is_happy
                    test_cases.append(
                        TestCaseExecution(
                            test_id=test_id,
                            scope=TestScope.UNIT,
                            name=f"test_{fn.name}_{vec_name}",
                            target=f"{fn.relative_path}:{fn.name}",
                            passed=passed,
                            duration_ms=elapsed_ms,
                            error_message=None if passed else str(controlled_exc),
                            details={"kwargs": kwargs, "exception": type(controlled_exc).__name__},
                        )
                    )
                except Exception as unhandled_exc:
                    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                    exc_type = type(unhandled_exc).__name__
                    test_cases.append(
                        TestCaseExecution(
                            test_id=test_id,
                            scope=TestScope.UNIT,
                            name=f"test_{fn.name}_{vec_name}",
                            target=f"{fn.relative_path}:{fn.name}",
                            passed=False,
                            duration_ms=elapsed_ms,
                            error_message=f"{exc_type}: {unhandled_exc}",
                            details={"kwargs": kwargs, "exception": exc_type},
                        )
                    )
                    is_div_zero = isinstance(unhandled_exc, ZeroDivisionError)
                    findings.append(
                        Finding(
                            id=f"UNIT-{fn.name.upper()}-{vec_name.upper()}",
                            scanner="nexcoder-testing-unit",
                            rule_id="UNIT-CONTRACT-001",
                            title=f"Unhandled {exc_type} in '{fn.name}' on {vec_name}",
                            description=(
                                f"Function '{fn.name}' in '{fn.relative_path}' raised an unhandled {exc_type} "
                                f"({unhandled_exc}) when invoked with boundary inputs {kwargs}."
                            ),
                            severity=Severity.HIGH if is_div_zero else Severity.MEDIUM,
                            category=FindingCategory.SAST,
                            location=Location(
                                file_path=fn.relative_path,
                                line_start=fn.lineno,
                            ),
                            cwe_ids=["CWE-20", "CWE-369"] if is_div_zero else ["CWE-20"],
                            remediation=Remediation(
                                summary=(
                                    f"Validate boundary parameters in '{fn.name}' before computation and raise "
                                    "a controlled ValueError on invalid inputs (for example, guard divisor <= 0)."
                                ),
                            ),
                        )
                    )

        return test_cases, findings, artifacts
