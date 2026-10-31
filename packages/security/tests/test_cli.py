import json
from pathlib import Path

from faccoder_security.cli import main


def test_cli_help(capsys):
    rc = main([])
    assert rc == 0
    captured = capsys.readouterr()
    assert "faccoder-security" in captured.out


def test_cli_scan_offline(tmp_path: Path, capsys):
    f = tmp_path / "app.py"
    f.write_text("eval('1+1')", encoding="utf-8")

    rc = main(["scan", str(tmp_path), "--offline"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Total findings:" in captured.out
    assert "semgrep" in captured.out.lower() or "bandit" in captured.out.lower()


def test_cli_scan_json_output(tmp_path: Path, capsys):
    f = tmp_path / "requirements.txt"
    f.write_text("requests==2.31.0\n", encoding="utf-8")

    rc = main(["scan", str(tmp_path), "--offline", "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["scanner"] == "multi-scanner-engine"
    assert len(data["findings"]) > 0


def test_cli_gate_block(tmp_path: Path, capsys):
    f = tmp_path / "vuln.py"
    f.write_text("import subprocess\nsubprocess.call('ls', shell=True)\n", encoding="utf-8")

    rc = main(["gate", str(tmp_path), "--offline"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "Release BLOCKED" in captured.out


def test_cli_gate_pass(tmp_path: Path, capsys):
    f = tmp_path / "clean.py"
    f.write_text("def hello(): return 'world'\n", encoding="utf-8")

    rc = main(["gate", str(tmp_path), "--offline"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Release APPROVED" in captured.out


def test_cli_sbom(tmp_path: Path, capsys):
    f = tmp_path / "requirements.txt"
    f.write_text("fastapi==0.111.0\n", encoding="utf-8")

    rc = main(["sbom", str(tmp_path), "--offline"])
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["bomFormat"] == "CycloneDX"


def test_cli_init_app_security(tmp_path: Path, capsys):
    rc = main(["init-app-security", str(tmp_path), "--name", "DemoProject"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "SECURITY.md" in captured.out
    assert (tmp_path / "SECURITY.md").exists()
