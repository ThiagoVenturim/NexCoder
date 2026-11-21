"""Unit tests for nexcoder-mlops command line interface."""

from __future__ import annotations

from pathlib import Path

from nexcoder_mlops.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_cli_prepare_dataset(tmp_path: Path) -> None:
    data_dir = tmp_path / "cli_data"
    result = runner.invoke(app, ["prepare-dataset", "--output-dir", str(data_dir), "--synthetic-count", "6"])
    assert result.exit_code == 0
    assert (data_dir / "train.jsonl").exists()
    assert (data_dir / "manifest.json").exists()


def test_cli_estimate_cost() -> None:
    result = runner.invoke(app, ["estimate-cost", "--tokens", "100000", "--params-b", "7.0"])
    assert result.exit_code == 0
    assert "Estimated Cost" in result.output


def test_cli_export_infra(tmp_path: Path) -> None:
    infra_dir = tmp_path / "cli_infra"
    result = runner.invoke(app, ["export-infra", "--output-dir", str(infra_dir)])
    assert result.exit_code == 0
    assert (infra_dir / "docker-compose.training.yml").exists()
    assert (infra_dir / "k8s-training-job.yaml").exists()


def test_cli_train_and_evaluate(tmp_path: Path) -> None:
    # Prepare data first
    data_dir = tmp_path / "data"
    runner.invoke(app, ["prepare-dataset", "--output-dir", str(data_dir), "--synthetic-count", "6"])

    ckpt_dir = tmp_path / "checkpoints"
    train_res = runner.invoke(
        app,
        [
            "train",
            "--dataset-path",
            str(data_dir / "train.jsonl"),
            "--epochs",
            "1",
            "--output-dir",
            str(ckpt_dir),
        ],
    )
    assert train_res.exit_code == 0
    assert "Training finished with status: completed" in train_res.output

    eval_res = runner.invoke(app, ["evaluate", "--test-path", str(data_dir / "test.jsonl")])
    assert eval_res.exit_code == 0
    assert "Evaluation Report" in eval_res.output


def test_cli_run_pipeline(tmp_path: Path) -> None:
    ckpt_dir = tmp_path / "pipeline_ckpts"
    result = runner.invoke(app, ["run-pipeline", "--synthetic-count", "4", "--output-dir", str(ckpt_dir)])
    assert result.exit_code == 0
    assert "MLOps Pipeline Run" in result.output
