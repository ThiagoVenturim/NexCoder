"""Unit tests for repository scanner across TODOs, dependencies, security, and lint."""

from pathlib import Path

from nexcoder_continuous_improvement.auto_improve.scanner import RepoScanner
from nexcoder_continuous_improvement.issues.planning_bridge import FindingCategory


def test_scanner_detects_todos(tmp_path: Path) -> None:
    src_file = tmp_path / "module.py"
    src_file.write_text(
        "# TODO: optimize database connection pool\n"
        "def connect():\n"
        "    pass\n"
        "# FIXME: resolve intermittent timeout issue\n",
        encoding="utf-8",
    )

    scanner = RepoScanner(root_path=tmp_path)
    findings = scanner.scan_todos()

    assert len(findings) == 2
    assert all(f.category == FindingCategory.TODO_DEBT for f in findings)
    assert any("optimize database" in f.title for f in findings)
    assert any("intermittent timeout" in f.title for f in findings)
    assert any(f.priority == "high" for f in findings)


def test_scanner_detects_unpinned_dependencies(tmp_path: Path) -> None:
    toml_file = tmp_path / "pyproject.toml"
    toml_file.write_text(
        '[project]\nname = "demo"\ndependencies = [\n    "unpinned-pkg",\n    "pinned-pkg>=1.0.0",\n]\n',
        encoding="utf-8",
    )

    scanner = RepoScanner(root_path=tmp_path)
    findings = scanner.scan_dependencies()

    assert len(findings) == 1
    assert findings[0].category == FindingCategory.DEPENDENCY
    assert "unpinned-pkg" in findings[0].title


def test_scanner_detects_security_risks(tmp_path: Path) -> None:
    sec_file = tmp_path / "insecure.py"
    sec_file.write_text(
        "import subprocess\n"
        "def run_command(cmd):\n"
        "    subprocess.call(cmd, shell=True)\n"
        "    eval('1 + 1')\n",
        encoding="utf-8",
    )

    scanner = RepoScanner(root_path=tmp_path)
    findings = scanner.scan_security_risks()

    assert len(findings) >= 2
    assert all(f.category == FindingCategory.SECURITY for f in findings)
    assert any("eval" in f.title for f in findings)
    assert any("shell=True" in f.title for f in findings)


def test_scanner_detects_syntax_errors(tmp_path: Path) -> None:
    bad_syntax = tmp_path / "broken.py"
    bad_syntax.write_text("def broken_func(\n", encoding="utf-8")

    scanner = RepoScanner(root_path=tmp_path)
    findings = scanner.scan_lint_and_hygiene()

    assert len(findings) >= 1
    assert any(f.category == FindingCategory.LINT and "syntax" in f.title.lower() for f in findings)


def test_scanner_detects_wildcard_imports(tmp_path: Path) -> None:
    wildcard_file = tmp_path / "wildcard.py"
    wildcard_file.write_text("from math import *\n", encoding="utf-8")

    scanner = RepoScanner(root_path=tmp_path)
    findings = scanner.scan_lint_and_hygiene()

    assert any("wildcard" in f.title.lower() for f in findings)


def test_scanner_detects_coverage_gaps(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "packages" / "untested-pkg"
    (pkg_dir / "src").mkdir(parents=True)
    (pkg_dir / "src" / "code.py").write_text("x = 1\n", encoding="utf-8")

    scanner = RepoScanner(root_path=tmp_path)
    findings = scanner.scan_test_coverage_gaps()

    assert len(findings) == 1
    assert findings[0].category == FindingCategory.LOW_COVERAGE
    assert "untested-pkg" in findings[0].title
