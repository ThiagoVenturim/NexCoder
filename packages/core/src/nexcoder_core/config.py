"""Project configuration.

Configuration comes from ``faccoder.yaml`` (searched from the current directory
upwards) and can be overridden by environment variables. Secrets never live in
the YAML file: the file names the environment variable that holds each key.

Example ``faccoder.yaml``::

    preset: hybrid            # all-open-source | all-paid | hybrid | local-vllm
    tiers:                    # optional overrides of the preset
      large: {provider: anthropic, model: claude-opus-5-5}
    embeddings: {provider: sentence-transformers, model: BAAI/bge-m3}
    langfuse: {enabled: true}
    budget: {max_usd_per_run: 5.0, max_delegation_depth: 2}
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from faccoder_core.llm.presets import PRESETS

Tier = Literal["small", "medium", "large"]

CONFIG_FILENAMES = ("faccoder.yaml", "faccoder.yml", ".faccoder.yaml")


class ModelSpec(BaseModel):
    """One model endpoint: which provider, which model, and how to reach it."""

    provider: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    # Several keys (comma separated in the env var) enable rotation with cooldown.
    api_keys_env: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    extra: dict = Field(default_factory=dict)
    fallbacks: list[ModelSpec] = Field(default_factory=list)


class EmbeddingSpec(BaseModel):
    provider: str = "sentence-transformers"
    model: str = "BAAI/bge-m3"
    base_url: str | None = None
    api_key_env: str | None = None
    dimensions: int | None = None


class RerankerSpec(BaseModel):
    provider: str = "cross-encoder"
    model: str = "BAAI/bge-reranker-v2-m3"
    enabled: bool = True


class LangfuseSpec(BaseModel):
    enabled: bool = True
    host_env: str = "LANGFUSE_HOST"
    public_key_env: str = "LANGFUSE_PUBLIC_KEY"
    secret_key_env: str = "LANGFUSE_SECRET_KEY"


class BudgetSpec(BaseModel):
    max_usd_per_run: float = 5.0
    max_delegation_depth: int = 2
    max_tool_calls_per_agent: int = 40
    context_budget_ratio: float = 0.60
    default_context_window: int = 32768


class StorageSpec(BaseModel):
    backend: Literal["sqlite", "postgres"] = "sqlite"
    path: str = ".faccoder/index.sqlite"
    dsn_env: str = "FACCODER_POSTGRES_DSN"


class FaccoderConfig(BaseModel):
    preset: str = "hybrid"
    tiers: dict[str, ModelSpec] = Field(default_factory=dict)
    embeddings: EmbeddingSpec = Field(default_factory=EmbeddingSpec)
    reranker: RerankerSpec = Field(default_factory=RerankerSpec)
    langfuse: LangfuseSpec = Field(default_factory=LangfuseSpec)
    budget: BudgetSpec = Field(default_factory=BudgetSpec)
    storage: StorageSpec = Field(default_factory=StorageSpec)
    project_root: str = "."

    def model_for(self, tier: str) -> ModelSpec:
        """Resolve a tier to a concrete model: explicit override, then preset."""
        if tier in self.tiers:
            return self.tiers[tier]
        preset = PRESETS.get(self.preset)
        if preset is None:
            raise ValueError(f"Unknown preset '{self.preset}'. Available: {', '.join(sorted(PRESETS))}")
        if tier not in preset["tiers"]:
            raise ValueError(f"Tier '{tier}' is not defined in preset '{self.preset}'")
        return ModelSpec(**preset["tiers"][tier])


def find_config_file(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        for name in CONFIG_FILENAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def load_config(path: str | Path | None = None) -> FaccoderConfig:
    """Load configuration from a file (or the nearest faccoder.yaml) plus env overrides.

    Environment overrides:
        FACCODER_PRESET   replaces ``preset``
    """
    file_path = Path(path) if path else find_config_file()
    data: dict = {}
    if file_path and file_path.is_file():
        data = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
        data.setdefault("project_root", str(file_path.parent))

    if os.environ.get("FACCODER_PRESET"):
        data["preset"] = os.environ["FACCODER_PRESET"]

    return FaccoderConfig.model_validate(data)
