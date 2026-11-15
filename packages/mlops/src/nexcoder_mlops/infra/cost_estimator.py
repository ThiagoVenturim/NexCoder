"""Cost and training duration estimation with budget policy validation."""

from __future__ import annotations

from nexcoder_control.metering.budgets import BudgetManager
from pydantic import BaseModel

from nexcoder_mlops.infra.gpu_config import (
    GPU_CATALOG,
    CloudProvider,
    GPUType,
    calculate_vram_requirement,
)
from nexcoder_mlops.training.config import FineTuneMethod


class TrainingCostEstimate(BaseModel):
    """Detailed breakdown of estimated training duration and dollar cost."""

    gpu_type: GPUType
    provider: CloudProvider
    method: FineTuneMethod
    estimated_duration_hours: float
    estimated_cost_usd: float
    hourly_rate_usd: float
    is_spot: bool
    total_tokens: int
    param_count_billions: float
    required_vram_gb: float
    budget_approved: bool = True
    budget_warning: str | None = None


def estimate_training_cost(
    total_tokens: int,
    param_count_billions: float,
    method: FineTuneMethod = FineTuneMethod.LORA,
    gpu_type: GPUType | None = None,
    provider: CloudProvider = CloudProvider.RUNPOD,
    epochs: int = 3,
    is_spot: bool = True,
    budget_manager: BudgetManager | None = None,
    entity_id: str = "mlops_training",
) -> TrainingCostEstimate:
    """Estimate compute duration and dollar expense, with optional budget verification."""
    req_vram, rec_gpu = calculate_vram_requirement(param_count_billions, method)
    selected_gpu = gpu_type or rec_gpu

    profile = GPU_CATALOG.get(selected_gpu, GPU_CATALOG[GPUType.A100_40GB])
    hourly_rate = profile.spot_hourly_rate_usd if is_spot else profile.hourly_rate_usd

    # Multiply provider margin / pricing factor
    provider_multiplier = {
        CloudProvider.LOCAL: 0.0,
        CloudProvider.RUNPOD: 1.0,
        CloudProvider.LAMBDA: 1.05,
        CloudProvider.GCP: 1.35,
        CloudProvider.AWS: 1.45,
    }.get(provider, 1.0)

    effective_rate = hourly_rate * provider_multiplier

    # Approximate FLOPs calculation:
    # Forward pass: 2P FLOPs/token. Backward pass: 4P FLOPs/token (2P for LoRA).
    flops_per_token = 4.0e9 * param_count_billions if method != FineTuneMethod.SFT else 6.0e9 * param_count_billions
    total_flops = flops_per_token * total_tokens * epochs

    # Realistic hardware MFU (Model FLOPs Utilization): ~35% for A100/H100
    mfu = 0.35
    achievable_tflops = profile.tflops_bf16 * 1e12 * mfu if profile.tflops_bf16 > 0 else 1e12

    duration_seconds = total_flops / achievable_tflops
    # Minimum training overhead of 60 seconds
    duration_seconds = max(60.0, duration_seconds)
    duration_hours = duration_seconds / 3600.0

    total_cost_usd = duration_hours * effective_rate

    # Evaluate against budget policies if BudgetManager is supplied
    budget_approved = True
    budget_warning = None
    if budget_manager:
        try:
            budget_manager.evaluate_entity(
                dimension="pipeline",
                entity_id=entity_id,
                additional_usd=total_cost_usd,
            )
        except Exception as exc:  # noqa: BLE001
            budget_approved = False
            budget_warning = str(exc)

    return TrainingCostEstimate(
        gpu_type=selected_gpu,
        provider=provider,
        method=method,
        estimated_duration_hours=round(duration_hours, 3),
        estimated_cost_usd=round(total_cost_usd, 4),
        hourly_rate_usd=round(effective_rate, 4),
        is_spot=is_spot,
        total_tokens=total_tokens,
        param_count_billions=param_count_billions,
        required_vram_gb=req_vram,
        budget_approved=budget_approved,
        budget_warning=budget_warning,
    )
