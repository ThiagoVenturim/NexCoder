"""Unit tests for fine-tuning configs, script generation, and offline toy training."""

from __future__ import annotations

import json
from pathlib import Path

from nexcoder_mlops.dataset.builder import DatasetBuilder
from nexcoder_mlops.training.config import (
    DistributedConfig,
    DistributedStrategy,
    FineTuneConfig,
    FineTuneMethod,
)
from nexcoder_mlops.training.engine import (
    ScriptGenerator,
    ToyOfflineTrainer,
)


def test_finetune_config_defaults() -> None:
    cfg = FineTuneConfig()
    assert cfg.base_model == "Qwen/Qwen2.5-Coder-7B-Instruct"
    assert cfg.method == FineTuneMethod.LORA
    assert cfg.lora.r == 16
    assert cfg.qlora.load_in_4bit is True
    assert cfg.distributed.strategy == DistributedStrategy.NONE


def test_script_and_distributed_generation() -> None:
    cfg = FineTuneConfig(
        base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        method=FineTuneMethod.QLORA,
    )
    cfg.distributed = DistributedConfig(
        strategy=DistributedStrategy.DEEPSPEED_STAGE2,
        num_gpus=4,
    )

    script = ScriptGenerator.generate_training_script(cfg)
    assert "BitsAndBytesConfig" in script
    assert "SFTTrainer" in script
    assert "LoraConfig" in script
    assert "Qwen/Qwen2.5-Coder-7B-Instruct" in script

    ds_config = ScriptGenerator.generate_deepspeed_config(cfg)
    assert ds_config["zero_optimization"]["stage"] == 2
    assert "bf16" in ds_config

    accel_config = ScriptGenerator.generate_accelerate_config(cfg)
    assert accel_config["distributed_type"] == "DEEPSPEED"
    assert accel_config["num_processes"] == 4


def test_toy_offline_trainer_execution(tmp_path: Path) -> None:
    builder = DatasetBuilder()
    samples = builder.create_synthetic_dataset(count=6)
    train_samples = samples[:4]
    val_samples = samples[4:]

    cfg = FineTuneConfig(
        base_model="toy-model",
        method=FineTuneMethod.LORA,
    )
    cfg.training_args.output_dir = str(tmp_path / "checkpoints")
    cfg.training_args.num_train_epochs = 3
    cfg.training_args.learning_rate = 0.05
    cfg.training_args.logging_steps = 1

    trainer = ToyOfflineTrainer(cfg)
    result = trainer.train(train_samples=train_samples, val_samples=val_samples, dataset_version="abc12345")

    assert result.status == "completed"
    assert result.total_steps == 12  # 3 epochs * 4 samples
    assert result.final_train_loss >= 0.0
    assert result.final_val_loss is not None
    assert len(result.metrics_history) > 0

    checkpoint_dir = Path(result.checkpoint_dir)
    assert checkpoint_dir.exists()
    assert (checkpoint_dir / "adapter_config.json").exists()
    assert (checkpoint_dir / "adapter_model.bin").exists()
    assert (checkpoint_dir / "trainer_state.json").exists()

    state = json.loads((checkpoint_dir / "trainer_state.json").read_text(encoding="utf-8"))
    assert state["global_step"] == 12
    assert len(state["log_history"]) > 0
