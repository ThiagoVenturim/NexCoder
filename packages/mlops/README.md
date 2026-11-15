# NexCoder MLOps

MLOps lifecycle engine for NexCoder: dataset curation, supervised fine-tuning (LoRA, QLoRA, SFT), offline validation, evaluation metrics, experiment tracking with Langfuse, and cloud/GPU infrastructure generation.

## Key Capabilities

- **Dataset Preparation**: Synthetic generation, quality cleaning, deduplication, PII anonymization, deterministic splitting, and SHA-256 version hashing.
- **Fine-Tuning Engine**: Support for LoRA, QLoRA (4-bit/8-bit bitsandbytes), and SFT. Includes production PyTorch/Transformers/TRL script generation and a zero-dependency offline toy trainer for deterministic local test loops.
- **Evaluation**: Exact Match, token overlap F1, perplexity estimation, regression checking against base models, and LLM-as-a-judge scoring via `nexcoder-serving`.
- **Experiment Tracking**: Hyperparameter logging, loss series recording, artifact lineage, and safe Langfuse tracing protected by circuit breakers.
- **GPU Infrastructure & Costing**: VRAM calculator, hardware profiling (A100, H100, L40S, RTX 4090, Apple MPS), Docker Compose and Kubernetes Job generation with strict credential isolation, and budget policy validation via `nexcoder-control`.
- **Serving Integration**: Exports fine-tuned checkpoints and adapters directly into `nexcoder-serving` compose configurations.

## Installation

```bash
pip install -e packages/mlops
```

## Quick Start (Offline Toy Fine-Tuning)

```python
from nexcoder_mlops import (
    DatasetBuilder,
    FineTuneConfig,
    FineTuneMethod,
    MLOpsPipeline,
)

# 1. Prepare configuration
config = FineTuneConfig(
    base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
    method=FineTuneMethod.LORA,
    experiment_name="quickstart-lora",
)

# 2. Run the full pipeline offline
pipeline = MLOpsPipeline()
result = pipeline.run_pipeline(config, synthetic_count=8)

print(result.summary())
print("Checkpoint location:", result.training_result.checkpoint_dir)
```

## CLI Usage

```bash
# 1. Prepare dataset
nexcoder-mlops prepare-dataset --output-dir ./data --synthetic-count 20

# 2. Run offline training
nexcoder-mlops train --dataset-path ./data/train.jsonl --epochs 2

# 3. Estimate training cost on cloud GPUs
nexcoder-mlops estimate-cost --tokens 1000000 --params-b 7.0 --gpu a100_40gb --provider runpod

# 4. Generate GPU infrastructure manifests (Compose and Kubernetes)
nexcoder-mlops export-infra --output-dir ./infra --gpu a100_40gb

# 5. Execute full end-to-end pipeline
nexcoder-mlops run-pipeline --base-model Qwen/Qwen2.5-Coder-7B-Instruct --method lora
```

## Origin

This package is part of the NexCoder suite, originating from the open-source engineering ecosystem inspired by ApoIA and lochome.
