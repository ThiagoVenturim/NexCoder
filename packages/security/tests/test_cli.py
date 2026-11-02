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

    rc = main(["gate", str(tmp_path), "--offline", "--policy", "default"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "Release BLOCKED" in captured.out


def test_cli_gate_pass(tmp_path: Path, capsys):
    f = tmp_path / "clean.py"
    f.write_text("def hello(): return 'world'\n", encoding="utf-8")

    rc = main(["gate", str(tmp_path), "--offline", "--policy", "default"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Release APPROVED" in captured.out


def test_cli_gate_require_sbom(tmp_path: Path, capsys):
    f = tmp_path / "clean.py"
    f.write_text("def hello(): return 'world'\n", encoding="utf-8")

    # 1. Without requirements/SBOM -> blocked by require_sbom
    rc_fail = main(["gate", str(tmp_path), "--offline", "--require-sbom", "--policy", "default"])
    assert rc_fail == 1
    out_fail = capsys.readouterr().out
    assert "Release BLOCKED" in out_fail

    # 2. Add requirements.txt so Syft generates valid SBOM -> passes
    req = tmp_path / "requirements.txt"
    req.write_text("pydantic==2.8.2\n", encoding="utf-8")
    rc_pass = main(["gate", str(tmp_path), "--offline", "--require-sbom", "--policy", "default"])
    assert rc_pass == 0
    out_pass = capsys.readouterr().out
    assert "Release APPROVED" in out_pass


def test_cli_gate_production_policy(monkeypatch, tmp_path: Path, capsys):
    f = tmp_path / "clean.py"
    f.write_text("def hello(): return 'world'\n", encoding="utf-8")
    req = tmp_path / "requirements.txt"
    req.write_text("pydantic==2.8.2\n", encoding="utf-8")

    # 1. In production policy with fallbacks (e.g. offline scan), gate blocks release
    rc_prod = main(["gate", str(tmp_path), "--offline", "--policy", "production"])
    assert rc_prod == 1
    out_prod = capsys.readouterr().out
    assert "Release BLOCKED" in out_prod
    assert "fallback" in out_prod.lower()

    # 2. In CI environment, production policy is used by default
    monkeypatch.setenv("CI", "1")
    rc_ci = main(["gate", str(tmp_path), "--offline"])
    assert rc_ci == 1
    out_ci = capsys.readouterr().out
    assert "Release BLOCKED" in out_ci

    # 3. Explicitly allowing fallbacks overrides production restriction
    rc_allowed = main(["gate", str(tmp_path), "--offline", "--allow-fallbacks"])
    assert rc_allowed == 0
    out_allowed = capsys.readouterr().out
    assert "Release APPROVED" in out_allowed


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
