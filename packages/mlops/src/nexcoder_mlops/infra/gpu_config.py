"""Hardware specifications, VRAM estimation, and GPU profiles for LLM fine-tuning."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from nexcoder_mlops.training.config import FineTuneMethod


class GPUType(StrEnum):
    A100_40GB = "a100_40gb"
    A100_80GB = "a100_80gb"
    H100_80GB = "h100_80gb"
    L40S_48GB = "l40s_48gb"
    T4_16GB = "t4_16gb"
    RTX_4090_24GB = "rtx_4090_24gb"
    MPS = "mps"
    CPU = "cpu"


class CloudProvider(StrEnum):
    AWS = "aws"
    GCP = "gcp"
    RUNPOD = "runpod"
    LAMBDA = "lambda"
    LOCAL = "local"


class GPUProfile(BaseModel):
    """Hardware profile and market pricing for GPU instances."""

    gpu_type: GPUType
    vram_gb: int
    tflops_bf16: float
    hourly_rate_usd: float
    spot_hourly_rate_usd: float


GPU_CATALOG: dict[GPUType, GPUProfile] = {
    GPUType.H100_80GB: GPUProfile(
        gpu_type=GPUType.H100_80GB,
        vram_gb=80,
        tflops_bf16=989.0,
        hourly_rate_usd=3.49,
        spot_hourly_rate_usd=2.49,
    ),
    GPUType.A100_80GB: GPUProfile(
        gpu_type=GPUType.A100_80GB,
        vram_gb=80,
        tflops_bf16=312.0,
        hourly_rate_usd=2.19,
        spot_hourly_rate_usd=1.39,
    ),
    GPUType.A100_40GB: GPUProfile(
        gpu_type=GPUType.A100_40GB,
        vram_gb=40,
        tflops_bf16=312.0,
        hourly_rate_usd=1.49,
        spot_hourly_rate_usd=0.99,
    ),
    GPUType.L40S_48GB: GPUProfile(
        gpu_type=GPUType.L40S_48GB,
        vram_gb=48,
        tflops_bf16=366.0,
        hourly_rate_usd=1.29,
        spot_hourly_rate_usd=0.79,
    ),
    GPUType.RTX_4090_24GB: GPUProfile(
        gpu_type=GPUType.RTX_4090_24GB,
        vram_gb=24,
        tflops_bf16=165.0,
        hourly_rate_usd=0.74,
        spot_hourly_rate_usd=0.44,
    ),
    GPUType.T4_16GB: GPUProfile(
        gpu_type=GPUType.T4_16GB,
        vram_gb=16,
        tflops_bf16=65.0,
        hourly_rate_usd=0.35,
        spot_hourly_rate_usd=0.19,
    ),
    GPUType.MPS: GPUProfile(
        gpu_type=GPUType.MPS,
        vram_gb=32,
        tflops_bf16=40.0,
        hourly_rate_usd=0.0,
        spot_hourly_rate_usd=0.0,
    ),
    GPUType.CPU: GPUProfile(
        gpu_type=GPUType.CPU,
        vram_gb=16,
        tflops_bf16=5.0,
        hourly_rate_usd=0.0,
        spot_hourly_rate_usd=0.0,
    ),
}


def calculate_vram_requirement(
    param_count_billions: float,
    method: FineTuneMethod,
    max_seq_len: int = 2048,
    batch_size: int = 2,
    lora_r: int = 16,
) -> tuple[float, GPUType]:
    """Estimate required VRAM in gigabytes and recommend minimal viable GPU.

    Returns (required_vram_gb, recommended_gpu).
    """
    if method == FineTuneMethod.QLORA:
        # Base model quantized to 4-bit (0.5 bytes per parameter)
        model_memory = param_count_billions * 0.55
        # LoRA trainable parameters (~1-2% of total params) in 16-bit with AdamW states (16 bytes/param)
        lora_params = param_count_billions * 0.015 * (lora_r / 16.0)
        optimizer_memory = lora_params * 16.0 * 1e-3
    elif method == FineTuneMethod.LORA:
        # Base model in 16-bit (2.0 bytes per parameter)
        model_memory = param_count_billions * 2.1
        lora_params = param_count_billions * 0.015 * (lora_r / 16.0)
        optimizer_memory = lora_params * 16.0 * 1e-3
    else:
        # Full SFT: 2 bytes model + 16 bytes optimizer states per param
        model_memory = param_count_billions * 2.1
        optimizer_memory = param_count_billions * 16.0

    # Activation memory roughly proportional to batch size and seq length squared
    activation_memory = (batch_size * max_seq_len * 128) / (1024**3) * 1.5

    # Base CUDA context overhead (~1.5 GB)
    cuda_overhead = 1.5

    total_required = (model_memory + optimizer_memory + activation_memory + cuda_overhead) * 1.25

    # Find smallest matching GPU
    for gpu_type in [
        GPUType.T4_16GB,
        GPUType.RTX_4090_24GB,
        GPUType.A100_40GB,
        GPUType.L40S_48GB,
        GPUType.A100_80GB,
        GPUType.H100_80GB,
    ]:
        if GPU_CATALOG[gpu_type].vram_gb >= total_required:
            return round(total_required, 2), gpu_type

    return round(total_required, 2), GPUType.H100_80GB
