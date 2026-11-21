"""Langfuse tracking adapter for MLOps training runs with circuit-breaker protection."""

from __future__ import annotations

import logging
import os
from typing import Any

from nexcoder_core.config import NexcoderConfig
from nexcoder_core.observability.langfuse_safe import langfuse_configured

from nexcoder_mlops.tracking.experiment import ExperimentRun

logger = logging.getLogger(__name__)


class LangfuseTracker:
    """Safely logs training runs, dataset versions, and evaluation metrics to Langfuse.

    If Langfuse is not configured or fails, operations are skipped without breaking the pipeline.
    """

    def __init__(self, config: NexcoderConfig | None = None) -> None:
        self.config = config or NexcoderConfig()
        self._enabled = langfuse_configured(self.config)
        self._client: Any | None = None

        if self._enabled:
            try:
                from langfuse import Langfuse

                spec = self.config.langfuse
                self._client = Langfuse(
                    public_key=os.environ.get(spec.public_key_env),
                    secret_key=os.environ.get(spec.secret_key_env),
                    host=os.environ.get(spec.host_env, "http://localhost:3000"),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not instantiate Langfuse client for MLOps tracking: %s", exc)
                self._enabled = False

    @property
    def is_active(self) -> bool:
        return self._enabled and self._client is not None

    def track_training_run(self, run: ExperimentRun) -> bool:
        """Record an experiment run as a trace in Langfuse."""
        if not self.is_active:
            return False

        try:
            trace = self._client.trace(
                name=f"mlops.training.{run.experiment_name}",
                id=run.run_id,
                metadata={
                    "base_model": run.base_model,
                    "dataset_version": run.dataset_version,
                    "status": run.status,
                    "params": run.params,
                    "artifacts": run.artifacts,
                    "duration_seconds": run.duration(),
                },
                tags=["mlops", "training", run.params.get("method", "fine-tune")],
            )

            # Record final metrics as scores
            for metric_name, metric_val in run.metrics.items():
                self._client.score(
                    trace_id=trace.id,
                    name=metric_name,
                    value=float(metric_val),
                    comment=f"Training metric: {metric_name}",
                )

            self._client.flush()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to publish MLOps experiment trace to Langfuse: %s", exc)
            return False
