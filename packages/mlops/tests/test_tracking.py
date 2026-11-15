"""Unit tests for experiment tracking, metric series, and Langfuse safe fallback."""

from __future__ import annotations

import json
from pathlib import Path

from nexcoder_mlops.tracking.experiment import ExperimentTracker
from nexcoder_mlops.tracking.langfuse_tracker import LangfuseTracker


def test_experiment_tracker_in_memory_and_file(tmp_path: Path) -> None:
    tracker = ExperimentTracker(log_dir=tmp_path / "logs")
    run = tracker.start_run(
        experiment_name="test_exp",
        base_model="Qwen/Qwen2.5-Coder-7B",
        dataset_version="v_12345",
        params={"lr": 0.001, "epochs": 2},
    )

    tracker.log_param("batch_size", 4)
    tracker.log_metric("train_loss", 0.85, step=1)
    tracker.log_metrics({"train_loss": 0.42, "val_loss": 0.50}, step=2)
    tracker.log_artifact("checkpoint", "/tmp/ckpt")

    completed = tracker.end_run(status="completed")
    assert completed.status == "completed"
    assert completed.params["batch_size"] == 4
    assert completed.metrics["val_loss"] == 0.50
    assert len(completed.metric_series) == 3

    saved_file = tmp_path / "logs" / f"{run.run_id}.json"
    assert saved_file.exists()
    data = json.loads(saved_file.read_text(encoding="utf-8"))
    assert data["run_id"] == run.run_id
    assert data["metrics"]["train_loss"] == 0.42


def test_langfuse_tracker_safe_offline_fallback() -> None:
    tracker = LangfuseTracker()
    assert tracker.is_active is False

    from nexcoder_mlops.tracking.experiment import ExperimentRun

    dummy_run = ExperimentRun(
        run_id="run_dummy",
        experiment_name="offline_test",
        base_model="dummy",
    )
    # Must never raise even when Langfuse is not configured or offline
    result = tracker.track_training_run(dummy_run)
    assert result is False
