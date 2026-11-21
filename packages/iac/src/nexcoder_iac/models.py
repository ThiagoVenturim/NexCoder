"""Data models and enums for nexcoder-iac infrastructure engine."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IaCTarget(StrEnum):
    LOCAL_COMPOSE = "local_compose"
    VM = "vm"
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    DIGITALOCEAN = "digitalocean"
    HETZNER = "hetzner"


class IaCTool(StrEnum):
    TERRAFORM = "terraform"
    OPENTOFU = "opentofu"
    ANSIBLE = "ansible"
    COMPOSE = "compose"


class ArchitectureTier(StrEnum):
    STARTER = "starter"
    STANDARD = "standard"
    PRODUCTION = "production"


class PlanAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NOOP = "noop"


class DatabaseEngine(StrEnum):
    NONE = "none"
    POSTGRES = "postgres"
    MYSQL = "mysql"
    REDIS = "redis"
    MONGODB = "mongodb"


class DatabaseSpec(BaseModel):
    engine: DatabaseEngine = DatabaseEngine.POSTGRES
    version: str = "16"
    database_name: str = "appdb"
    port: int = 5432
    storage_gb: int = 20
    managed: bool = True


class ServiceSpec(BaseModel):
    name: str = "web"
    image: str = "python:3.11-slim"
    port: int = 8000
    replicas: int = 1
    cpu_cores: float = 1.0
    memory_mb: int = 1024
    environment_vars: list[str] = Field(default_factory=list)
    volumes: list[str] = Field(default_factory=list)
    healthcheck_path: str = "/health"
    is_gpu: bool = False


class AIServingSpec(BaseModel):
    enabled: bool = False
    profile: str = "vllm"
    model_name: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    gpu_count: str = "1"
    port: int = 8000


class ArchitectureSpec(BaseModel):
    name: str = "application"
    description: str = "Application infrastructure"
    tier: ArchitectureTier = ArchitectureTier.STANDARD
    target: IaCTarget = IaCTarget.LOCAL_COMPOSE
    services: list[ServiceSpec] = Field(default_factory=list)
    database: DatabaseSpec | None = None
    cache: bool = False
    queue_worker: bool = False
    load_balancer: bool = False
    domain: str | None = None
    ai_serving: AIServingSpec | None = None


class GeneratedFile(BaseModel):
    filename: str
    content: str
    file_type: str = "text"
    description: str = ""


class IaCArtifacts(BaseModel):
    spec: ArchitectureSpec
    target: IaCTarget
    tool: IaCTool
    files: list[GeneratedFile] = Field(default_factory=list)
    instructions: str = ""
    required_env_vars: list[str] = Field(default_factory=list)
    estimated_monthly_cost_usd: float = 0.0

    def get_file(self, filename: str) -> GeneratedFile | None:
        for f in self.files:
            if f.filename == filename:
                return f
        return None


class ResourcePlan(BaseModel):
    resource_id: str
    resource_type: str
    action: PlanAction = PlanAction.CREATE
    reason: str = "New resource"
    estimated_cost_usd_month: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)


class PlanPreview(BaseModel):
    plan_id: str
    target: IaCTarget
    tool: IaCTool
    planned_resources: list[ResourcePlan] = Field(default_factory=list)
    total_estimated_cost_usd_month: float = 0.0
    execution_summary: str = ""
    approval_required: bool = True
    dry_run: bool = True
    warnings: list[str] = Field(default_factory=list)


class ApplyResult(BaseModel):
    success: bool
    plan_id: str
    target: IaCTarget
    status: str = "applied"
    applied_resources: list[str] = Field(default_factory=list)
    message: str = ""
    audit_event_id: str | None = None
    dry_run: bool = True
