"""Tests for nexcoder-serving CLI interface."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml
from nexcoder_serving.cli import app, main
from typer.testing import CliRunner

runner = CliRunner()


def test_serving_cli_help() -> None:
    # Assert that help renders and shows the command description. Do not assert on
    # individual option names: Rich wraps/truncates them by terminal width, which is
    # a rendering detail, not CLI behavior. Option handling is covered by the tests
    # that invoke the actual commands below.
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Generate a docker-compose.yml file for local model serving." in result.output


def test_serving_cli_compose_default(tmp_path: Path) -> None:
    out_file = tmp_path / "compose-default.yml"
    result = runner.invoke(app, ["--output", str(out_file)])
    assert result.exit_code == 0
    assert "Generated compose configuration for profile 'vllm'" in result.output
    assert out_file.exists()

    content = yaml.safe_load(out_file.read_text(encoding="utf-8"))
    assert "services" in content
    assert "vllm" in content["services"]


def test_serving_cli_compose_ollama(tmp_path: Path) -> None:
    out_file = tmp_path / "sub" / "compose-ollama.yml"
    result = runner.invoke(
        app,
        [
            "--profile",
            "ollama",
            "--output",
            str(out_file),
            "--model",
            "codellama:7b",
            "--port",
            "11434",
        ],
    )
    assert result.exit_code == 0
    assert "Generated compose configuration for profile 'ollama'" in result.output
    assert out_file.exists()

    content = yaml.safe_load(out_file.read_text(encoding="utf-8"))
    assert "services" in content
    assert "ollama" in content["services"]


def test_serving_cli_compose_invalid_port(tmp_path: Path) -> None:
    out_file = tmp_path / "compose-err.yml"
    result = runner.invoke(app, ["--output", str(out_file), "--port", "invalid-port"])
    assert result.exit_code != 0


def test_serving_cli_main_entrypoint() -> None:
    with patch("nexcoder_serving.cli.app") as mock_app:
        main()
        mock_app.assert_called_once()
