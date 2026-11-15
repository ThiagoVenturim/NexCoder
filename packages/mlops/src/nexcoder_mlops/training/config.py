"""Configuration schemas for fine-tuning methods (LoRA, QLoRA, SFT) and distributed training."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class FineTuneMethod(StrEnum):
    SFT = "sft"
    LORA = "lora"
    QLORA = "qlora"


class DistributedStrategy(StrEnum):
    NONE = "none"
    DDP = "ddp"
    FSDP = "fsdp"
    DEEPSPEED_STAGE2 = "deepspeed_stage2"
    DEEPSPEED_STAGE3 = "deepspeed_stage3"


class LoRAConfig(BaseModel):
    """Low-Rank Adaptation hyperparameters."""

    r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: list[str] = Field(
        default_factory=lambda: ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    )
    bias: str = "none"
    task_type: str = "CAUSAL_LM"


class QLoRAConfig(BaseModel):
    """Quantized LoRA (4-bit/8-bit bitsandbytes) settings."""

    load_in_4bit: bool = True
    bnb_4bit_quant_type: str = "nf4"
    bnb_4bit_use_double_quant: bool = True
    bnb_4bit_compute_dtype: str = "bfloat16"
    lora: LoRAConfig = Field(default_factory=LoRAConfig)


class DistributedConfig(BaseModel):
    """Distributed training and memory-optimization configurations."""

    strategy: DistributedStrategy = DistributedStrategy.NONE
    num_gpus: int = 1
    zero_stage: int = 2
    gradient_clipping: float = 1.0


class TrainingArgumentsConfig(BaseModel):
    """Training hyperparameter definitions matching standard open-source trainers."""

    output_dir: str = "./outputs/checkpoints"
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    lr_scheduler_type: str = "cosine"
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    logging_steps: int = 5
    save_steps: int = 50
    fp16: bool = False
    bf16: bool = True
    max_seq_length: int = 2048


class FineTuneConfig(BaseModel):
    """Master configuration for an SFT/LoRA/QLoRA training run."""

    base_model: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    method: FineTuneMethod = FineTuneMethod.LORA
    dataset_path: str = "./data/train.jsonl"
    val_dataset_path: str | None = None
    lora: LoRAConfig = Field(default_factory=LoRAConfig)
    qlora: QLoRAConfig = Field(default_factory=QLoRAConfig)
    training_args: TrainingArgumentsConfig = Field(default_factory=TrainingArgumentsConfig)
    distributed: DistributedConfig = Field(default_factory=DistributedConfig)
    experiment_name: str = "nexcoder-finetune"
