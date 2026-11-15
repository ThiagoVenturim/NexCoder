from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.check_injection_guard import is_path_allowlisted, scan_file


def test_parameterized_query_passes(tmp_path: Path):
    clean_file = tmp_path / "clean_db.py"
    clean_file.write_text(
        """
import sqlite3

def get_user(conn: sqlite3.Connection, user_id: str):
    query = "SELECT id, username, email FROM users WHERE id = ? AND active = ?"
    return conn.execute(query, (user_id, 1)).fetchone()
""",
        encoding="utf-8",
    )
    violations = scan_file(clean_file)
    assert len(violations) == 0


def test_concatenated_sql_is_blocked(tmp_path: Path):
    vuln_file = tmp_path / "vuln_db.py"
    vuln_file.write_text(
        """
def find_user(cursor, user_input: str):
    cursor.execute("SELECT * FROM users WHERE username = '" + user_input + "'")
""",
        encoding="utf-8",
    )
    violations = scan_file(vuln_file)
    assert any("sql-injection" in v.rule for v in violations)


def test_fstring_sql_is_blocked(tmp_path: Path):
    vuln_file = tmp_path / "vuln_fstring.py"
    vuln_file.write_text(
        """
def delete_item(cursor, item_id: str):
    cursor.execute(f"DELETE FROM items WHERE id = {item_id}")
""",
        encoding="utf-8",
    )
    violations = scan_file(vuln_file)
    assert any("sql-injection" in v.rule for v in violations)


def test_eval_exec_with_dynamic_input_is_blocked(tmp_path: Path):
    vuln_file = tmp_path / "vuln_eval.py"
    vuln_file.write_text(
        """
def run_user_code(user_input: str):
    eval(user_input)
    exec(user_input)
""",
        encoding="utf-8",
    )
    violations = scan_file(vuln_file)
    assert any(v.rule == "security.dynamic-execution" for v in violations)


def test_subprocess_shell_true_is_blocked(tmp_path: Path):
    vuln_file = tmp_path / "vuln_shell.py"
    vuln_file.write_text(
        """
import subprocess

def run_cmd(user_cmd: str):
    subprocess.run(user_cmd, shell=True)
""",
        encoding="utf-8",
    )
    violations = scan_file(vuln_file)
    assert any(v.rule == "command-injection.shell-true" for v in violations)


def test_unfirewalled_llm_invoke_is_blocked(tmp_path: Path):
    vuln_file = tmp_path / "vuln_llm.py"
    vuln_file.write_text(
        """
def ask_ai(llm, user_prompt: str):
    return llm.invoke(f"System: do task. User: {user_prompt}")
""",
        encoding="utf-8",
    )
    violations = scan_file(vuln_file)
    assert any("prompt-injection" in v.rule for v in violations)


def test_allowlist_permits_scanner_definitions():
    scanner_path = Path("packages/security/src/nexcoder_security/scanners/review_scanners.py")
    assert is_path_allowlisted(scanner_path) is True
    # Allowlisted file yields zero violations
    violations = scan_file(scanner_path)
    assert len(violations) == 0


def test_monorepo_injection_guard_passes_cleanly():
    res = subprocess.run(
        [sys.executable, "scripts/check_injection_guard.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"check_injection_guard failed: {res.stderr}\n{res.stdout}"
    assert "Injection guard passed cleanly" in res.stdout
