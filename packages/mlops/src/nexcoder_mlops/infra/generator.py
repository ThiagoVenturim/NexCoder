"""Generates Docker Compose, Kubernetes Jobs, and training scripts with isolated credentials."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from nexcoder_mlops.infra.gpu_config import CloudProvider, GPUType
from nexcoder_mlops.training.config import FineTuneConfig, FineTuneMethod
from nexcoder_mlops.training.engine import ScriptGenerator


class GeneratedInfraFile(BaseModel):
    filename: str
    content: str
    description: str


class TrainingInfraArtifacts(BaseModel):
    files: list[GeneratedInfraFile]
    instructions: str
    gpu_type: GPUType
    provider: CloudProvider


def scan_for_secrets(content: str) -> list[str]:
    """Check text for potential hardcoded secrets or API tokens."""
    patterns = [
        (r"(?i)(hf_[a-zA-Z0-9]{34,})", "Hugging Face token"),
        (r"(?i)(sk-[a-zA-Z0-9]{32,})", "OpenAI secret key"),
        (r"(?i)(ghp_[a-zA-Z0-9]{36,})", "GitHub personal access token"),
        (r"(?i)(AKIA[0-9A-Z]{16})", "AWS Access Key ID"),
    ]
    findings = []
    for pat, label in patterns:
        if re.search(pat, content):
            findings.append(label)
    return findings


class InfraGenerator:
    """Produces container and orchestrator configurations for remote or on-premise GPU fine-tuning."""

    @staticmethod
    def generate_compose(config: FineTuneConfig, gpu_count: int = 1) -> str:
        """Produce Docker Compose manifest targeting NVIDIA Container Toolkit."""
        is_qlora = config.method == FineTuneMethod.QLORA
        image = "pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime" if not is_qlora else "bitsandbytes/cuda121:latest"

        return f"""version: "3.8"
services:
  trainer:
    image: {image}
    container_name: nexcoder-mlops-trainer
    working_dir: /workspace
    volumes:
      - .:/workspace
      - ./data:/workspace/data
      - ./outputs:/workspace/outputs
    environment:
      - HF_TOKEN=${{HF_TOKEN:-}}
      - WANDB_API_KEY=${{WANDB_API_KEY:-}}
      - CUDA_VISIBLE_DEVICES=all
      - PYTHONUNBUFFERED=1
    command: ["python", "train.py"]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: {gpu_count}
              capabilities: [gpu]
    restart: "no"
"""

    @staticmethod
    def generate_k8s_job(config: FineTuneConfig, gpu_count: int = 1) -> str:
        """Produce Kubernetes batch/v1 Job manifest with GPU resource limits."""
        return f"""apiVersion: batch/v1
kind: Job
metadata:
  name: nexcoder-training-{config.experiment_name.replace('_', '-')}
  labels:
    app: nexcoder-mlops
    experiment: {config.experiment_name.replace('_', '-')}
spec:
  backoffLimit: 1
  template:
    metadata:
      labels:
        app: nexcoder-mlops
    spec:
      restartPolicy: Never
      containers:
        - name: trainer
          image: pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime
          command: ["python", "train.py"]
          resources:
            limits:
              nvidia.com/gpu: "{gpu_count}"
              memory: 32Gi
              cpu: "8"
            requests:
              nvidia.com/gpu: "{gpu_count}"
              memory: 16Gi
              cpu: "4"
          env:
            - name: HF_TOKEN
              valueFrom:
                secretKeyRef:
                  name: nexcoder-secrets
                  key: hf-token
                  optional: true
            - name: WANDB_API_KEY
              valueFrom:
                secretKeyRef:
                  name: nexcoder-secrets
                  key: wandb-api-key
                  optional: true
          volumeMounts:
            - name: dataset-storage
              mountPath: /workspace/data
            - name: checkpoint-storage
              mountPath: /workspace/outputs
      volumes:
        - name: dataset-storage
          persistentVolumeClaim:
            claimName: nexcoder-datasets-pvc
        - name: checkpoint-storage
          persistentVolumeClaim:
            claimName: nexcoder-checkpoints-pvc
"""

    @staticmethod
    def generate_env_example() -> str:
        return """# User credentials for cloud / GPU training
# DO NOT COMMIT REAL SECRETS TO SOURCE CONTROL
HF_TOKEN=your_huggingface_hub_token_here
WANDB_API_KEY=your_weights_and_biases_key_here
AWS_ACCESS_KEY_ID=your_aws_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_here
RUNPOD_API_KEY=your_runpod_api_key_here
"""

    @classmethod
    def generate_all(
        cls,
        config: FineTuneConfig,
        gpu_type: GPUType = GPUType.A100_40GB,
        provider: CloudProvider = CloudProvider.RUNPOD,
    ) -> TrainingInfraArtifacts:
        compose_content = cls.generate_compose(config)
        k8s_content = cls.generate_k8s_job(config)
        script_content = ScriptGenerator.generate_training_script(config)
        env_example = cls.generate_env_example()

        files = [
            GeneratedInfraFile(
                filename="docker-compose.training.yml",
                content=compose_content,
                description="Docker Compose file for local or cloud GPU training",
            ),
            GeneratedInfraFile(
                filename="k8s-training-job.yaml",
                content=k8s_content,
                description="Kubernetes batch/v1 Job specification for cloud clusters",
            ),
            GeneratedInfraFile(
                filename="train.py",
                content=script_content,
                description="Standalone training script with HuggingFace PEFT/TRL",
            ),
            GeneratedInfraFile(
                filename=".env.example",
                content=env_example,
                description="Sample environment file with user-supplied credential placeholders",
            ),
        ]

        # Scan for accidental secrets
        for f in files:
            findings = scan_for_secrets(f.content)
            if findings:
                raise ValueError(f"Secret detected in generated file {f.filename}: {findings}")

        instructions = (
            f"# Training Infrastructure for {config.experiment_name}\n\n"
            f"Target GPU: `{gpu_type}` on `{provider}`.\n\n"
            "## 1. Setup Credentials\n"
            "```bash\n"
            "cp .env.example .env\n"
            "# Fill your personal HF_TOKEN or Cloud API keys in .env\n"
            "```\n\n"
            "## 2. Run with Docker Compose (GPU Machine)\n"
            "```bash\n"
            "docker compose -f docker-compose.training.yml up\n"
            "```\n\n"
            "## 3. Run on Kubernetes Cluster\n"
            "```bash\n"
            "kubectl apply -f k8s-training-job.yaml\n"
            "```\n"
        )

        return TrainingInfraArtifacts(
            files=files,
            instructions=instructions,
            gpu_type=gpu_type,
            provider=provider,
        )

    @classmethod
    def write_artifacts(cls, artifacts: TrainingInfraArtifacts, target_dir: str | Path) -> None:
        out = Path(target_dir)
        out.mkdir(parents=True, exist_ok=True)
        for f in artifacts.files:
            (out / f.filename).write_text(f.content, encoding="utf-8")
        (out / "README.md").write_text(artifacts.instructions, encoding="utf-8")
