"""Serving configuration and Docker Compose generation for vLLM and Ollama profiles."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ServingProfile(StrEnum):
    VLLM = "vllm"
    OLLAMA = "ollama"


class ServingConfig(BaseModel):
    profile: ServingProfile = ServingProfile.VLLM
    model_name: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    host: str = "127.0.0.1"
    port: int = 8000
    max_model_len: int = 8192
    gpu_memory_utilization: float = 0.90
    gpu_count: str = "all"
    hf_token_env: str = "HUGGING_FACE_HUB_TOKEN"
    extra_args: list[str] = Field(default_factory=list)


def generate_compose_config(config: ServingConfig) -> dict[str, Any]:
    """Generate a Docker Compose dictionary for the requested profile."""
    if config.profile == ServingProfile.VLLM:
        return {
            "version": "3.8",
            "services": {
                "vllm": {
                    "image": "vllm/vllm-openai:latest",
                    "container_name": "faccoder-serving-vllm",
                    "profiles": ["vllm"],
                    "environment": {
                        "HUGGING_FACE_HUB_TOKEN": f"${{{config.hf_token_env}:-}}",
                        "MODEL_NAME": config.model_name,
                        "MAX_MODEL_LEN": str(config.max_model_len),
                        "GPU_MEMORY_UTILIZATION": str(config.gpu_memory_utilization),
                    },
                    "command": [
                        "--model",
                        config.model_name,
                        "--port",
                        str(config.port),
                        "--max-model-len",
                        str(config.max_model_len),
                        "--gpu-memory-utilization",
                        str(config.gpu_memory_utilization),
                        *config.extra_args,
                    ],
                    "ports": [f"{config.port}:{config.port}"],
                    "deploy": {
                        "resources": {
                            "reservations": {
                                "devices": [
                                    {
                                        "driver": "nvidia",
                                        "count": config.gpu_count,
                                        "capabilities": ["gpu"],
                                    }
                                ]
                            }
                        }
                    },
                    "restart": "unless-stopped",
                }
            },
        }

    # Ollama profile
    return {
        "version": "3.8",
        "services": {
            "ollama": {
                "image": "ollama/ollama:latest",
                "container_name": "faccoder-serving-ollama",
                "profiles": ["ollama"],
                "environment": {
                    "OLLAMA_KEEP_ALIVE": "24h",
                    "OLLAMA_HOST": f"{config.host}:{config.port}",
                },
                "volumes": ["ollama_models:/root/.ollama"],
                "ports": [f"{config.port}:{config.port}"],
                "restart": "unless-stopped",
            }
        },
        "volumes": {
            "ollama_models": {
                "name": "faccoder_serving_ollama_models",
            }
        },
    }


def get_serving_endpoint(profile: ServingProfile, host: str = "127.0.0.1", port: int | None = None) -> str:
    """Return the standard OpenAI-compatible base URL for the serving engine."""
    actual_port = port or (8000 if profile == ServingProfile.VLLM else 11434)
    if profile == ServingProfile.VLLM:
        return f"http://{host}:{actual_port}/v1"
    return f"http://{host}:{actual_port}/v1"


def validate_compose_file(path: str | Path) -> bool:
    """Validate that a compose file exists and contains the expected services."""
    p = Path(path)
    if not p.is_file():
        return False
    content = p.read_text(encoding="utf-8")
    return "vllm" in content or "ollama" in content
