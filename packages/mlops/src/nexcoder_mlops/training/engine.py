"""Training engine containing offline toy trainer and production script generation."""

from __future__ import annotations

import json
import math
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from nexcoder_mlops.dataset.builder import DataSample, DatasetBuilder
from nexcoder_mlops.training.config import (
    DistributedStrategy,
    FineTuneConfig,
    FineTuneMethod,
)


class TrainingMetricStep(BaseModel):
    """Metric logged at a training step."""

    step: int
    epoch: float
    train_loss: float
    val_loss: float | None = None
    learning_rate: float
    timestamp: float = Field(default_factory=time.time)


class TrainingRunResult(BaseModel):
    """Outcome and artifacts of a training execution."""

    run_id: str
    status: str
    method: FineTuneMethod
    base_model: str
    dataset_version: str = ""
    epochs_completed: int
    total_steps: int
    final_train_loss: float
    final_val_loss: float | None = None
    duration_seconds: float
    checkpoint_dir: str
    metrics_history: list[TrainingMetricStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToyOfflineTrainer:
    """Zero-dependency, offline-safe training engine for unit tests, local dry-runs, and toy fine-tuning.

    Runs an actual numerical parameter optimization loop on vectorized representations of samples,
    reducing loss across steps, recording metrics history, and producing standard adapter artifacts.
    """

    def __init__(self, config: FineTuneConfig) -> None:
        self.config = config

    def _text_to_vector(self, text: str, dim: int = 16) -> list[float]:
        """Deterministic pseudo-embedding for text."""
        vec = [0.0] * dim
        for i, ch in enumerate(text.encode("utf-8")):
            vec[i % dim] += (ch - 96) * 0.05
        # Normalize
        norm = math.sqrt(sum(v * v for v in vec)) + 1e-6
        return [v / norm for v in vec]

    def train(
        self,
        train_samples: list[DataSample] | None = None,
        val_samples: list[DataSample] | None = None,
        dataset_version: str = "",
    ) -> TrainingRunResult:
        start_time = time.time()
        run_id = f"run_{int(start_time)}_{random.randint(1000, 9999)}"  # noqa: S311

        if train_samples is None:
            train_samples = DatasetBuilder.load_jsonl(self.config.dataset_path)
        if val_samples is None and self.config.val_dataset_path:
            val_samples = DatasetBuilder.load_jsonl(self.config.val_dataset_path)

        if not train_samples:
            # Fallback to a synthetic mini dataset if empty
            builder = DatasetBuilder()
            train_samples = builder.create_synthetic_dataset("toy_code", count=4)

        # Setup toy parameters (dim 16 -> dim 16 matrix)
        dim = 16
        random.seed(42)
        weights = [[(random.random() - 0.5) * 0.1 for _ in range(dim)] for _ in range(dim)]  # noqa: S311
        bias = [0.0] * dim

        epochs = self.config.training_args.num_train_epochs
        lr = self.config.training_args.learning_rate
        metrics: list[TrainingMetricStep] = []

        step = 0
        current_loss = 1.0

        for epoch in range(1, epochs + 1):
            epoch_losses = []
            for sample in train_samples:
                step += 1
                x = self._text_to_vector(f"{sample.instruction} {sample.input_text}", dim)
                target = self._text_to_vector(sample.output, dim)

                # Forward: y = W * x + b
                pred = [sum(weights[r][c] * x[c] for c in range(dim)) + bias[r] for r in range(dim)]

                # Loss: MSE between pred and target
                sample_loss = sum((pred[i] - target[i]) ** 2 for i in range(dim)) / dim
                epoch_losses.append(sample_loss)

                # Backward gradients
                grad_pred = [2.0 * (pred[i] - target[i]) / dim for i in range(dim)]

                # Update weights and bias
                for r in range(dim):
                    bias[r] -= lr * grad_pred[r]
                    for c in range(dim):
                        weights[r][c] -= lr * grad_pred[r] * x[c]

                # Learning rate cosine decay approximation
                current_lr = lr * 0.5 * (1.0 + math.cos(math.pi * step / (epochs * len(train_samples) + 1)))

                if step % max(1, self.config.training_args.logging_steps) == 0:
                    val_loss = None
                    if val_samples:
                        v_losses = []
                        for vs in val_samples:
                            vx = self._text_to_vector(f"{vs.instruction} {vs.input_text}", dim)
                            vt = self._text_to_vector(vs.output, dim)
                            vp = [sum(weights[r][c] * vx[c] for c in range(dim)) + bias[r] for r in range(dim)]
                            v_losses.append(sum((vp[i] - vt[i]) ** 2 for i in range(dim)) / dim)
                        val_loss = sum(v_losses) / len(v_losses)

                    current_loss = sum(epoch_losses) / len(epoch_losses)
                    metrics.append(
                        TrainingMetricStep(
                            step=step,
                            epoch=round(epoch + (step % len(train_samples)) / len(train_samples), 2),
                            train_loss=round(current_loss, 6),
                            val_loss=round(val_loss, 6) if val_loss is not None else None,
                            learning_rate=current_lr,
                        )
                    )

        # Save artifacts to output directory
        out_dir = Path(self.config.training_args.output_dir) / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        adapter_config = {
            "base_model_name_or_path": self.config.base_model,
            "peft_type": "LORA",
            "task_type": self.config.lora.task_type,
            "r": self.config.lora.r,
            "lora_alpha": self.config.lora.lora_alpha,
            "lora_dropout": self.config.lora.lora_dropout,
            "target_modules": self.config.lora.target_modules,
            "bias": self.config.lora.bias,
        }
        (out_dir / "adapter_config.json").write_text(json.dumps(adapter_config, indent=2), encoding="utf-8")

        # Serialized weights
        serialized_weights = {"weights": weights, "bias": bias, "dim": dim}
        (out_dir / "adapter_model.bin").write_text(json.dumps(serialized_weights), encoding="utf-8")

        trainer_state = {
            "best_metric": min(m.train_loss for m in metrics) if metrics else current_loss,
            "global_step": step,
            "total_flos": step * 1000000,
            "log_history": [m.model_dump() for m in metrics],
        }
        (out_dir / "trainer_state.json").write_text(json.dumps(trainer_state, indent=2), encoding="utf-8")

        final_val = metrics[-1].val_loss if (metrics and metrics[-1].val_loss is not None) else None
        duration = time.time() - start_time

        return TrainingRunResult(
            run_id=run_id,
            status="completed",
            method=self.config.method,
            base_model=self.config.base_model,
            dataset_version=dataset_version,
            epochs_completed=epochs,
            total_steps=step,
            final_train_loss=metrics[-1].train_loss if metrics else current_loss,
            final_val_loss=final_val,
            duration_seconds=round(duration, 3),
            checkpoint_dir=str(out_dir),
            metrics_history=metrics,
        )


class ScriptGenerator:
    """Generates standalone production training scripts and distributed configuration files."""

    @staticmethod
    def generate_training_script(config: FineTuneConfig) -> str:
        """Generate a production PyTorch + Transformers + TRL SFTTrainer Python script."""
        is_qlora = config.method == FineTuneMethod.QLORA
        quant_block = (
            """
    from transformers import BitsAndBytesConfig
    import torch
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
"""
            if is_qlora
            else "    bnb_config = None"
        )

        return f'''"""Auto-generated production training script by NexCoder MLOps."""
from __future__ import annotations

import os
import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from trl import SFTTrainer

def main():
    base_model_name = "{config.base_model}"
    output_dir = "{config.training_args.output_dir}"

{quant_block}

    tokenizer = AutoTokenizer.from_pretrained(
        base_model_name,
        token=os.environ.get("HF_TOKEN"),
        trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        quantization_config=bnb_config,
        device_map="auto",
        token=os.environ.get("HF_TOKEN"),
        trust_remote_code=True,
    )

    peft_config = LoraConfig(
        r={config.lora.r},
        lora_alpha={config.lora.lora_alpha},
        lora_dropout={config.lora.lora_dropout},
        target_modules={config.lora.target_modules},
        bias="{config.lora.bias}",
        task_type="{config.lora.task_type}",
    )

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs={config.training_args.num_train_epochs},
        per_device_train_batch_size={config.training_args.per_device_train_batch_size},
        gradient_accumulation_steps={config.training_args.gradient_accumulation_steps},
        learning_rate={config.training_args.learning_rate},
        lr_scheduler_type="{config.training_args.lr_scheduler_type}",
        warmup_ratio={config.training_args.warmup_ratio},
        weight_decay={config.training_args.weight_decay},
        logging_steps={config.training_args.logging_steps},
        save_steps={config.training_args.save_steps},
        bf16={config.training_args.bf16},
        fp16={config.training_args.fp16},
        report_to=["tensorboard"],
    )

    dataset = load_dataset("json", data_files="{config.dataset_path}", split="train")

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        peft_config=peft_config,
        max_seq_length={config.training_args.max_seq_length},
        tokenizer=tokenizer,
        args=training_args,
    )

    trainer.train()
    trainer.model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

if __name__ == "__main__":
    main()
'''

    @staticmethod
    def generate_deepspeed_config(config: FineTuneConfig) -> dict[str, Any]:
        """Generate standard DeepSpeed ZeRO-2 or ZeRO-3 JSON configuration."""
        stage = 3 if config.distributed.strategy == DistributedStrategy.DEEPSPEED_STAGE3 else 2
        return {
            "fp16": {"enabled": config.training_args.fp16},
            "bf16": {"enabled": config.training_args.bf16},
            "zero_optimization": {
                "stage": stage,
                "offload_optimizer": {"device": "cpu", "pin_memory": True},
                "offload_param": {"device": "cpu", "pin_memory": True} if stage == 3 else {},
                "overlap_comm": True,
                "contiguous_gradients": True,
                "reduce_bucket_size": "auto",
                "stage3_prefetch_bucket_size": "auto",
                "stage3_param_persistence_threshold": "auto",
            },
            "gradient_accumulation_steps": config.training_args.gradient_accumulation_steps,
            "gradient_clipping": config.distributed.gradient_clipping,
            "train_batch_size": "auto",
            "train_micro_batch_size_per_gpu": config.training_args.per_device_train_batch_size,
        }

    @staticmethod
    def generate_accelerate_config(config: FineTuneConfig) -> dict[str, Any]:
        """Generate Hugging Face Accelerate configuration."""
        use_deepspeed = "deepspeed" in config.distributed.strategy.value
        use_fsdp = config.distributed.strategy == DistributedStrategy.FSDP

        strategy_str = "NO"
        if use_deepspeed:
            strategy_str = "DEEPSPEED"
        elif use_fsdp:
            strategy_str = "FSDP"
        elif config.distributed.num_gpus > 1:
            strategy_str = "MULTI_GPU"

        return {
            "compute_environment": "LOCAL_MACHINE",
            "distributed_type": strategy_str,
            "mixed_precision": "bf16" if config.training_args.bf16 else "fp16",
            "num_processes": config.distributed.num_gpus,
            "gpu_ids": "all",
        }
