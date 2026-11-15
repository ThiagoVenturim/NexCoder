# NexCoder MLOps: Model Training, Fine-Tuning, and Lifecycle Management

This document outlines the architecture, workflows, and operations of the `nexcoder-mlops` engine. NexCoder not only orchestrates model inference and agent workflows, but also empowers engineers to train, fine-tune, evaluate, track, and deploy specialized language models.

---

## Architecture Overview

```
+-----------------------------------------------------------------------------------+
|                                  nexcoder-mlops                                   |
|                                                                                   |
|  +--------------------+   +--------------------+   +---------------------------+  |
|  |      Dataset       |   |      Training      |   |        Evaluation         |  |
|  | - Synthetic Gen    |   | - LoRA / QLoRA /SFT|   | - Exact Match & Token F1  |  |
|  | - PII Anonymizer   |   | - ToyOfflineTrainer|   | - Perplexity & Benchmarks |  |
|  | - SHA-256 Manifest |   | - HF / TRL Scripts |   | - LLM-as-a-Judge          |  |
|  +---------+----------+   +---------+----------+   +-------------+-------------+  |
|            |                        |                            |                |
|  +---------v----------+   +---------v----------+   +-------------v-------------+  |
|  |  GPU Infra & Cost  |   | Experiment Tracking|   |     Serving Export        |  |
|  | - VRAM Calculator  |   | - Metrics & Series |   | - vLLM Profile Compose    |  |
|  | - Compose & K8s Job|   | - Langfuse Traces  |   | - Ollama Modelfile        |  |
|  | - Budget Gates     |   | - Checkpoint Store |   | - Adapter Registration    |  |
|  +--------------------+   +--------------------+   +---------------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## 1. Dataset Preparation & Lineage

The dataset module (`nexcoder_mlops.dataset`) handles data curation for supervised fine-tuning:

- **Format Adaptation**: Supports ChatML (`messages`), Alpaca (`instruction`, `input`, `output`), ShareGPT (`conversations`), and standard prompt/completion formats.
- **Quality Filtering & Deduplication**: Removes samples failing length thresholds and eliminates duplicate records via content hashing.
- **PII & Secret Anonymization**: Reuses `Anonymizer` from `nexcoder-serving` to replace emails, IPs, CPFs, and API keys with structured placeholders before data touches disk or GPUs.
- **Immutable Version Manifest**: Computes deterministic SHA-256 hashes of dataset splits (`DatasetManifest`), ensuring complete reproducibility and lineage back to training runs.

---

## 2. Supervised Fine-Tuning (LoRA, QLoRA, SFT)

NexCoder provides a dual-mode training architecture:

### A. Zero-Dependency Offline Toy Trainer (`ToyOfflineTrainer`)
For local tests, CI/CD pipelines, and dry-run validation, `ToyOfflineTrainer` runs entirely offline without requiring GPUs, PyTorch, or large model weights. It optimizes vectorized representations of samples, records genuine loss curves, and generates valid adapter artifacts (`adapter_config.json`, `adapter_model.bin`, `trainer_state.json`).

### B. Production Script Generator (`ScriptGenerator`)
Generates standalone, production-ready Python training scripts for deployment on GPU clusters or cloud instances:
- **LoRA / QLoRA**: Integrates Hugging Face `transformers`, `peft` (`LoraConfig`), and `trl` (`SFTTrainer`) with 4-bit NormalFloat4 (`nf4`) double quantization via `bitsandbytes`.
- **Distributed Training**: Generates DeepSpeed ZeRO-2/ZeRO-3 configuration JSON and Hugging Face Accelerate configuration YAML.

---

## 3. Evaluation & LLM Judge

The evaluation module (`nexcoder_mlops.evaluation`) validates fine-tuned model performance:
- **Token Overlap F1 & Exact Match**: Measures token precision, recall, and exact match rates against held-out validation sets.
- **Perplexity Estimation**: Tracks cross-entropy loss exponential across epochs.
- **Regression Detection**: Compares baseline vs fine-tuned scorecard to detect capability regressions.
- **LLM-as-a-Judge**: Reuses `LLMJudge` from `nexcoder-serving` for automated qualitative evaluation of answer faithfulness and relevance.

---

## 4. Experiment Tracking & Langfuse Integration

- **Local & File Tracking**: `ExperimentTracker` records hyperparameters, step-level metrics, and artifact pointers to disk as JSON records.
- **Langfuse Integration**: `LangfuseTracker` bridges training metrics and dataset versions into Langfuse traces with circuit-breaker protection. If Langfuse is unreachable or unconfigured, the training pipeline continues uninterrupted.

---

## 5. GPU Hardware & Cloud Infrastructure

### Hardware Profiles & VRAM Calculation
The VRAM estimator calculates memory requirements across model parameter sizes, quantization levels (4-bit QLoRA vs 16-bit LoRA vs full SFT), batch sizes, and sequence lengths:

```python
from nexcoder_mlops import calculate_vram_requirement, FineTuneMethod

vram_gb, gpu = calculate_vram_requirement(
    param_count_billions=7.0,
    method=FineTuneMethod.QLORA,
)
print(f"Required VRAM: {vram_gb} GB, Recommended: {gpu}")
```

### Supported GPU Profiles
- **NVIDIA H100 (80GB)**: High-throughput large model training (70B+ parameters).
- **NVIDIA A100 (40GB / 80GB)**: Standard workhorse for 7B-32B fine-tuning.
- **NVIDIA L40S (48GB)**: High-density FP8/BF16 fine-tuning.
- **NVIDIA RTX 4090 (24GB)**: Cost-efficient consumer GPU for QLoRA fine-tuning.
- **NVIDIA T4 (16GB)**: Entry-level inference and mini LoRA adaptation.
- **Apple Silicon MPS & CPU**: Local development and prototyping.

### User Credential Isolation
Training configurations strictly forbid embedded secrets. Generated `.env.example` templates expose placeholder variables (`HF_TOKEN`, `WANDB_API_KEY`, cloud credentials). Automated secret scanning validates generated files before emission.

### Budget Verification
Integrates with `nexcoder_control.metering.budgets.BudgetManager` to verify estimated costs against predefined project spending policies before provisioning remote GPU compute.

---

## 6. Serving Integration

Once fine-tuning completes, the model artifacts are registered directly into `nexcoder-serving`:
- Generates Docker Compose configurations for vLLM with `--enable-lora` and adapter module mappings.
- Compatible with Ollama `Modelfile` definitions (`ADAPTER ./checkpoint`).
