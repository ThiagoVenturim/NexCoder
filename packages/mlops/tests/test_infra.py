"""Unit tests for GPU hardware specs, cost estimation, budget gates, and infra generation."""

from __future__ import annotations

from pathlib import Path

from nexcoder_control.metering.budgets import BudgetManager, BudgetPolicy
from nexcoder_control.metering.cost_tracker import CostTracker
from nexcoder_mlops.infra.cost_estimator import estimate_training_cost
from nexcoder_mlops.infra.generator import InfraGenerator, scan_for_secrets
from nexcoder_mlops.infra.gpu_config import (
    CloudProvider,
    GPUType,
    calculate_vram_requirement,
)
from nexcoder_mlops.training.config import FineTuneConfig, FineTuneMethod


def test_vram_calculation_methods() -> None:
    # 7B model QLoRA
    vram_qlora, gpu_qlora = calculate_vram_requirement(7.0, FineTuneMethod.QLORA)
    assert vram_qlora < 16.0
    assert gpu_qlora in [GPUType.T4_16GB, GPUType.RTX_4090_24GB]

    # 7B model LoRA 16-bit
    vram_lora, gpu_lora = calculate_vram_requirement(7.0, FineTuneMethod.LORA)
    assert vram_lora > vram_qlora
    assert gpu_lora in [GPUType.RTX_4090_24GB, GPUType.A100_40GB]

    # 70B model SFT requires high-end GPU
    vram_sft, gpu_sft = calculate_vram_requirement(70.0, FineTuneMethod.SFT)
    assert vram_sft > 100.0
    assert gpu_sft == GPUType.H100_80GB


def test_cost_estimation_and_budget_enforcement() -> None:
    # Basic estimation
    est = estimate_training_cost(
        total_tokens=100000,
        param_count_billions=7.0,
        method=FineTuneMethod.LORA,
        gpu_type=GPUType.A100_40GB,
        provider=CloudProvider.RUNPOD,
    )
    assert est.estimated_cost_usd > 0.0
    assert est.budget_approved is True

    # Budget gate validation
    cost_tracker = CostTracker()
    budget_mgr = BudgetManager(cost_tracker)
    budget_mgr.add_policy(
        BudgetPolicy(
            dimension="pipeline",
            entity_id="mlops_training",
            limit_usd=10.0,
            enforce_hard_limit=True,
        )
    )

    # Within $10 budget
    est_ok = estimate_training_cost(
        total_tokens=50000,
        param_count_billions=7.0,
        gpu_type=GPUType.RTX_4090_24GB,
        budget_manager=budget_mgr,
        entity_id="mlops_training",
    )
    assert est_ok.budget_approved is True

    # Stricter budget ($0.0001) that should fail
    budget_strict = BudgetManager(cost_tracker)
    budget_strict.add_policy(
        BudgetPolicy(
            dimension="pipeline",
            entity_id="mlops_strict",
            limit_usd=0.00001,
            enforce_hard_limit=True,
        )
    )
    est_fail = estimate_training_cost(
        total_tokens=5000000,
        param_count_billions=70.0,
        gpu_type=GPUType.H100_80GB,
        budget_manager=budget_strict,
        entity_id="mlops_strict",
    )
    assert est_fail.budget_approved is False
    assert est_fail.budget_warning is not None


def test_infra_generator_and_secret_scanning(tmp_path: Path) -> None:
    cfg = FineTuneConfig(base_model="Qwen/Qwen2.5-Coder-7B-Instruct", method=FineTuneMethod.LORA)
    artifacts = InfraGenerator.generate_all(cfg, gpu_type=GPUType.A100_40GB, provider=CloudProvider.RUNPOD)

    assert len(artifacts.files) == 4
    filenames = [f.filename for f in artifacts.files]
    assert "docker-compose.training.yml" in filenames
    assert "k8s-training-job.yaml" in filenames
    assert "train.py" in filenames
    assert ".env.example" in filenames

    # Secret scanner should catch accidental real tokens
    clean_sample = "HF_TOKEN=your_token_here\n"
    assert scan_for_secrets(clean_sample) == []

    leaked_sample = "HF_TOKEN=hf_abcdefghijklmnopqrstuvwxyz0123456789\n"
    assert len(scan_for_secrets(leaked_sample)) > 0

    # Write artifacts to disk
    InfraGenerator.write_artifacts(artifacts, tmp_path / "infra")
    assert (tmp_path / "infra" / "docker-compose.training.yml").exists()
    assert (tmp_path / "infra" / "README.md").exists()
