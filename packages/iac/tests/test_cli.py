"""Tests for nexcoder-iac command-line interface."""

from nexcoder_iac.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_cli_catalog_list():
    result = runner.invoke(app, ["catalog", "list"])
    assert result.exit_code == 0
    assert "simple_app" in result.output
    assert "microservices" in result.output


def test_cli_catalog_show():
    result = runner.invoke(app, ["catalog", "show", "simple_app"])
    assert result.exit_code == 0
    assert "Architecture: web-app" in result.output
    assert "Estimated Cost" in result.output


def test_cli_generate_local(tmp_path):
    out_dir = tmp_path / "iac_out"
    result = runner.invoke(
        app,
        [
            "generate",
            "--desc",
            "App python com postgres",
            "--target",
            "local_compose",
            "--out-dir",
            str(out_dir),
        ],
    )
    assert result.exit_code == 0
    assert "Generated IaC" in result.output
    assert (out_dir / "docker-compose.yml").exists()
    assert (out_dir / ".env.example").exists()


def test_cli_estimate():
    result = runner.invoke(app, ["estimate", "--arch", "app_database", "--target", "aws", "--tier", "standard"])
    assert result.exit_code == 0
    assert "Target:       aws" in result.output
    assert "Estimated:" in result.output
