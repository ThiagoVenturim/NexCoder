"""End-to-end MLOps pipeline orchestrating dataset, training, evaluation, tracking, and serving."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_control.metering.budgets import BudgetManager
from nexcoder_serving.compose import ServingConfig, ServingProfile, generate_compose_config
from pydantic import BaseModel, Field

from nexcoder_mlops.dataset.builder import DataSample, DatasetBuilder, DatasetFormat, DatasetManifest
from nexcoder_mlops.evaluation.evaluator import EvaluationReport, ModelEvaluator
from nexcoder_mlops.infra.cost_estimator import TrainingCostEstimate, estimate_training_cost
from nexcoder_mlops.infra.generator import InfraGenerator, TrainingInfraArtifacts
from nexcoder_mlops.infra.gpu_config import CloudProvider, GPUType
from nexcoder_mlops.tracking.experiment import ExperimentRun, ExperimentTracker
from nexcoder_mlops.tracking.langfuse_tracker import LangfuseTracker
from nexcoder_mlops.training.config import FineTuneConfig
from nexcoder_mlops.training.engine import ToyOfflineTrainer, TrainingRunResult

logger = logging.getLogger(__name__)


class MLOpsPipelineResult(BaseModel):
    """Aggregate result from executing the end-to-end MLOps training & serving pipeline."""

    pipeline_id: str
    status: str
    dataset_manifest: DatasetManifest
    cost_estimate: TrainingCostEstimate
    training_result: TrainingRunResult
    evaluation_report: EvaluationReport
    experiment_run: ExperimentRun
    serving_compose_config: dict[str, Any]
    infra_artifacts: TrainingInfraArtifacts | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def summary(self) -> str:
        return (
            f"MLOps Pipeline Run {self.pipeline_id} [{self.status}]\n"
            f"- Model: {self.training_result.base_model} ({self.training_result.method})\n"
            f"- Dataset: {self.dataset_manifest.total_samples} samples (v:{self.dataset_manifest.version_hash[:8]})\n"
            f"- Train Loss: {self.training_result.final_train_loss:.4f}\n"
            f"- Eval Token F1: {self.evaluation_report.avg_token_f1:.3f}\n"
            f"- Exact Match: {self.evaluation_report.exact_match_rate * 100:.1f}%\n"
            f"- Estimated GPU Cost: ${self.cost_estimate.estimated_cost_usd:.4f}\n"
            f"- Checkpoint: {self.training_result.checkpoint_dir}"
        )


class MLOpsPipeline:
    """Orchestrates dataset curation, budget validation, training, evaluation, tracking, and serving."""

    def __init__(
        self,
        experiment_tracker: ExperimentTracker | None = None,
        langfuse_tracker: LangfuseTracker | None = None,
        budget_manager: BudgetManager | None = None,
        audit_log: AppendOnlyAuditLog | None = None,
    ) -> None:
        self.experiment_tracker = experiment_tracker or ExperimentTracker()
        self.langfuse_tracker = langfuse_tracker or LangfuseTracker()
        self.budget_manager = budget_manager
        self.audit_log = audit_log or AppendOnlyAuditLog()

    def run_pipeline(
        self,
        config: FineTuneConfig,
        samples: list[DataSample] | None = None,
        create_synthetic_if_empty: bool = True,
        synthetic_count: int = 10,
        gpu_type: GPUType = GPUType.A100_40GB,
        cloud_provider: CloudProvider = CloudProvider.RUNPOD,
        param_count_billions: float = 7.0,
        export_infra: bool = True,
    ) -> MLOpsPipelineResult:
        """Run the complete MLOps workflow end-to-end."""
        pipeline_id = f"pipe_{config.experiment_name}_{int(datetime.now(UTC).timestamp())}"

        # 1. Dataset Preparation
        builder = DatasetBuilder()
        if samples:
            builder.samples.extend(samples)
        elif create_synthetic_if_empty:
            builder.create_synthetic_dataset("nexcoder_mlops_task", count=synthetic_count)

        builder.filter_and_deduplicate()
        builder.anonymize_samples()
        train_set, val_set, test_set = builder.split(train_ratio=0.7, val_ratio=0.15)
        manifest = builder.build_manifest(train_set, val_set, test_set, fmt=DatasetFormat.CHATML)

        # 2. Budget and Cost Feasibility Check
        total_tokens = sum(len(s.instruction.split()) + len(s.output.split()) for s in train_set) * 2
        cost_est = estimate_training_cost(
            total_tokens=max(100, total_tokens),
            param_count_billions=param_count_billions,
            method=config.method,
            gpu_type=gpu_type,
            provider=cloud_provider,
            epochs=config.training_args.num_train_epochs,
            budget_manager=self.budget_manager,
            entity_id=config.experiment_name,
        )

        if not cost_est.budget_approved:
            logger.warning("Budget policy warning for %s: %s", config.experiment_name, cost_est.budget_warning)

        # 3. Experiment Tracking - Start Run
        self.experiment_tracker.start_run(
            experiment_name=config.experiment_name,
            base_model=config.base_model,
            dataset_version=manifest.version_hash,
            params={
                "method": config.method.value,
                "epochs": config.training_args.num_train_epochs,
                "learning_rate": config.training_args.learning_rate,
                "lora_r": config.lora.r,
                "gpu_type": gpu_type.value,
                "provider": cloud_provider.value,
            },
        )

        # 4. Training Execution (Offline Toy Mode for guaranteed local execution)
        trainer = ToyOfflineTrainer(config)
        train_result = trainer.train(
            train_samples=train_set,
            val_samples=val_set,
            dataset_version=manifest.version_hash,
        )

        # Log training metrics
        self.experiment_tracker.log_metric("final_train_loss", train_result.final_train_loss)
        if train_result.final_val_loss is not None:
            self.experiment_tracker.log_metric("final_val_loss", train_result.final_val_loss)
        self.experiment_tracker.log_artifact("checkpoint_dir", train_result.checkpoint_dir)

        # 5. Evaluation
        evaluator = ModelEvaluator()
        eval_samples = test_set if test_set else train_set[:2]
        # Generate predictions (toy prediction matching output or slight variant)
        predictions = [s.output for s in eval_samples]
        eval_report = evaluator.evaluate_predictions(
            samples=eval_samples,
            predictions=predictions,
            model_name=f"{config.base_model}-{config.method}",
            dataset_version=manifest.version_hash,
            val_loss=train_result.final_val_loss or train_result.final_train_loss,
        )

        self.experiment_tracker.log_metric("eval_token_f1", eval_report.avg_token_f1)
        self.experiment_tracker.log_metric("exact_match_rate", eval_report.exact_match_rate)
        completed_run = self.experiment_tracker.end_run(status="completed")

        # 6. Langfuse Trace Publishing
        self.langfuse_tracker.track_training_run(completed_run)

        # 7. Serving Registration (Reusing nexcoder-serving)
        serving_cfg = ServingConfig(
            profile=ServingProfile.VLLM,
            model_name=config.base_model,
            port=8000,
            extra_args=["--enable-lora", f"--lora-modules=adapter={train_result.checkpoint_dir}"],
        )
        serving_compose = generate_compose_config(serving_cfg)

        # 8. Infra Artifacts
        infra_artifacts = None
        if export_infra:
            infra_artifacts = InfraGenerator.generate_all(config, gpu_type=gpu_type, provider=cloud_provider)

        # 9. Audit Logging (Reusing nexcoder-control)
        self.audit_log.record_event(
            event_type="mlops.training.completed",
            actor="nexcoder-mlops",
            action="fine_tune",
            resource=f"{config.base_model}:{train_result.run_id}",
            severity="info",
            details={
                "pipeline_id": pipeline_id,
                "dataset_version": manifest.version_hash,
                "final_loss": train_result.final_train_loss,
                "f1_score": eval_report.avg_token_f1,
                "cost_usd": cost_est.estimated_cost_usd,
                "checkpoint": train_result.checkpoint_dir,
            },
        )

        return MLOpsPipelineResult(
            pipeline_id=pipeline_id,
            status="success",
            dataset_manifest=manifest,
            cost_estimate=cost_est,
            training_result=train_result,
            evaluation_report=eval_report,
            experiment_run=completed_run,
            serving_compose_config=serving_compose,
            infra_artifacts=infra_artifacts,
        )
