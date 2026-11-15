"""Experiment tracking, metrics logging, artifact lineage, and local/file persistence."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class MetricRecord(BaseModel):
    """Timestamped metric measurement."""

    key: str
    value: float
    step: int | None = None
    timestamp: float = Field(default_factory=time.time)


class ExperimentRun(BaseModel):
    """Complete record of a training run including hyperparameters and lineage."""

    run_id: str
    experiment_name: str
    base_model: str
    dataset_version: str = ""
    status: str = "running"
    params: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    metric_series: list[MetricRecord] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    start_time: float = Field(default_factory=time.time)
    end_time: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def duration(self) -> float:
        if self.end_time is not None:
            return round(self.end_time - self.start_time, 2)
        return round(time.time() - self.start_time, 2)


class ExperimentTracker:
    """Thread-safe experiment tracker supporting in-memory storage and JSON persistence."""

    def __init__(self, log_dir: str | Path | None = None) -> None:
        self.log_dir = Path(log_dir) if log_dir else None
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        self._runs: dict[str, ExperimentRun] = {}
        self._active_run: ExperimentRun | None = None
        self._lock = threading.Lock()

    def start_run(
        self,
        experiment_name: str,
        base_model: str,
        dataset_version: str = "",
        run_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> ExperimentRun:
        """Initialize and activate a new experiment run."""
        with self._lock:
            rid = run_id or f"exp_{int(time.time())}_{len(self._runs) + 1}"
            run = ExperimentRun(
                run_id=rid,
                experiment_name=experiment_name,
                base_model=base_model,
                dataset_version=dataset_version,
                params=params or {},
            )
            self._runs[rid] = run
            self._active_run = run
            self._save_run(run)
            return run

    def log_param(self, key: str, value: Any) -> None:
        with self._lock:
            if not self._active_run:
                raise RuntimeError("No active experiment run. Call start_run first.")
            self._active_run.params[key] = value
            self._save_run(self._active_run)

    def log_params(self, params: dict[str, Any]) -> None:
        with self._lock:
            if not self._active_run:
                raise RuntimeError("No active experiment run. Call start_run first.")
            self._active_run.params.update(params)
            self._save_run(self._active_run)

    def log_metric(self, key: str, value: float, step: int | None = None) -> None:
        with self._lock:
            if not self._active_run:
                raise RuntimeError("No active experiment run. Call start_run first.")
            self._active_run.metrics[key] = value
            self._active_run.metric_series.append(MetricRecord(key=key, value=value, step=step))
            self._save_run(self._active_run)

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        with self._lock:
            if not self._active_run:
                raise RuntimeError("No active experiment run. Call start_run first.")
            for k, v in metrics.items():
                self._active_run.metrics[k] = v
                self._active_run.metric_series.append(MetricRecord(key=k, value=v, step=step))
            self._save_run(self._active_run)

    def log_artifact(self, name: str, path: str) -> None:
        with self._lock:
            if not self._active_run:
                raise RuntimeError("No active experiment run. Call start_run first.")
            self._active_run.artifacts[name] = path
            self._save_run(self._active_run)

    def end_run(self, status: str = "completed") -> ExperimentRun:
        with self._lock:
            if not self._active_run:
                raise RuntimeError("No active experiment run.")
            self._active_run.status = status
            self._active_run.end_time = time.time()
            completed_run = self._active_run
            self._save_run(completed_run)
            self._active_run = None
            return completed_run

    def get_run(self, run_id: str) -> ExperimentRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self) -> list[ExperimentRun]:
        with self._lock:
            return list(self._runs.values())

    def _save_run(self, run: ExperimentRun) -> None:
        if self.log_dir:
            run_file = self.log_dir / f"{run.run_id}.json"
            run_file.write_text(run.model_dump_json(indent=2), encoding="utf-8")
