"""End-to-end pipeline tests verifying dataset prep, toy fine-tune, eval, tracking, serving, and audit."""

from __future__ import annotations

from pathlib import Path

from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_control.metering.budgets import BudgetManager
from nexcoder_control.metering.cost_tracker import CostTracker
from nexcoder_mlops.pipeline.mlops_pipeline import MLOpsPipeline
from nexcoder_mlops.tracking.experiment import ExperimentTracker
from nexcoder_mlops.training.config import FineTuneConfig, FineTuneMethod


def test_end_to_end_mlops_pipeline_offline(tmp_path: Path) -> None:
    # Setup audit and budget dependencies
    cost_tracker = CostTracker()
    budget_mgr = BudgetManager(cost_tracker)
    audit_log = AppendOnlyAuditLog()
    exp_tracker = ExperimentTracker(log_dir=tmp_path / "exp_logs")

    pipeline = MLOpsPipeline(
        experiment_tracker=exp_tracker,
        budget_manager=budget_mgr,
        audit_log=audit_log,
    )

    cfg = FineTuneConfig(
        base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        method=FineTuneMethod.LORA,
        experiment_name="e2e-offline-test",
    )
    cfg.training_args.output_dir = str(tmp_path / "checkpoints")
    cfg.training_args.num_train_epochs = 2
    cfg.training_args.learning_rate = 0.05

    # Run the full pipeline
    result = pipeline.run_pipeline(
        config=cfg,
        create_synthetic_if_empty=True,
        synthetic_count=8,
        param_count_billions=7.0,
        export_infra=True,
    )

    assert result.status == "success"
    assert result.dataset_manifest.total_samples == 8
    assert len(result.dataset_manifest.version_hash) == 64

    # Verify training results
    assert result.training_result.epochs_completed == 2
    assert result.training_result.total_steps > 0
    assert Path(result.training_result.checkpoint_dir).exists()

    # Verify evaluation
    assert result.evaluation_report.total_samples > 0
    assert 0.0 <= result.evaluation_report.exact_match_rate <= 1.0

    # Verify experiment tracker recorded run
    assert result.experiment_run.status == "completed"
    assert "final_train_loss" in result.experiment_run.metrics
    assert "eval_token_f1" in result.experiment_run.metrics

    # Verify serving docker compose configuration
    assert "services" in result.serving_compose_config
    assert "vllm" in result.serving_compose_config["services"]

    # Verify infra artifacts
    assert result.infra_artifacts is not None
    assert len(result.infra_artifacts.files) == 4

    # Verify cryptographic audit trail
    assert len(audit_log._events) == 1
    event = audit_log._events[0]
    assert event.event_type == "mlops.training.completed"
    assert event.actor == "nexcoder-mlops"

    is_valid, msg = audit_log.verify_integrity()
    assert is_valid is True
    assert "1 events intact" in msg

    # Summary string check
    summary = result.summary()
    assert "MLOps Pipeline Run" in summary
    assert "Qwen/Qwen2.5-Coder-7B-Instruct" in summary
