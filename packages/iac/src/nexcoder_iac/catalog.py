"""Reference architecture catalog from basic to advanced architectures with sizing tiers."""

from __future__ import annotations

from typing import Any

from nexcoder_iac.models import (
    AIServingSpec,
    ArchitectureSpec,
    ArchitectureTier,
    DatabaseEngine,
    DatabaseSpec,
    IaCTarget,
    ServiceSpec,
)


def get_simple_app_spec(
    target: IaCTarget = IaCTarget.LOCAL_COMPOSE,
    tier: ArchitectureTier = ArchitectureTier.STANDARD,
    app_name: str = "web-app",
    image: str = "python:3.11-slim",
    port: int = 8000,
) -> ArchitectureSpec:
    """Basic single-server / single-container architecture."""
    cpu = 0.5 if tier == ArchitectureTier.STARTER else (1.0 if tier == ArchitectureTier.STANDARD else 2.0)
    memory = 512 if tier == ArchitectureTier.STARTER else (1024 if tier == ArchitectureTier.STANDARD else 2048)

    service = ServiceSpec(
        name=app_name,
        image=image,
        port=port,
        replicas=1 if tier != ArchitectureTier.PRODUCTION else 2,
        cpu_cores=cpu,
        memory_mb=memory,
        environment_vars=["PORT=8000", "ENVIRONMENT=production"],
        healthcheck_path="/health",
    )
    return ArchitectureSpec(
        name=app_name,
        description=f"Simple application ({tier.value} tier)",
        tier=tier,
        target=target,
        services=[service],
        database=None,
        cache=False,
        queue_worker=False,
        load_balancer=(tier == ArchitectureTier.PRODUCTION),
    )


def get_app_database_spec(
    target: IaCTarget = IaCTarget.LOCAL_COMPOSE,
    tier: ArchitectureTier = ArchitectureTier.STANDARD,
    app_name: str = "api-backend",
    image: str = "python:3.11-slim",
    port: int = 8000,
    db_engine: DatabaseEngine = DatabaseEngine.POSTGRES,
) -> ArchitectureSpec:
    """Web app + relational database + reverse proxy."""
    cpu = 0.5 if tier == ArchitectureTier.STARTER else (1.0 if tier == ArchitectureTier.STANDARD else 2.0)
    memory = 512 if tier == ArchitectureTier.STARTER else (1024 if tier == ArchitectureTier.STANDARD else 2048)
    db_storage = 10 if tier == ArchitectureTier.STARTER else (20 if tier == ArchitectureTier.STANDARD else 100)

    service = ServiceSpec(
        name=app_name,
        image=image,
        port=port,
        replicas=1 if tier != ArchitectureTier.PRODUCTION else 2,
        cpu_cores=cpu,
        memory_mb=memory,
        environment_vars=["PORT=8000", "DATABASE_URL=postgres://${DB_USER}:${DB_PASSWORD}@db:5432/${DB_NAME}"],
        healthcheck_path="/health",
    )
    database = DatabaseSpec(
        engine=db_engine,
        version="16" if db_engine == DatabaseEngine.POSTGRES else "8.0",
        database_name=f"{app_name.replace('-', '_')}_db",
        port=5432 if db_engine == DatabaseEngine.POSTGRES else 3306,
        storage_gb=db_storage,
        managed=(target != IaCTarget.LOCAL_COMPOSE and tier != ArchitectureTier.STARTER),
    )
    return ArchitectureSpec(
        name=app_name,
        description=f"Web application with {db_engine.value} database ({tier.value} tier)",
        tier=tier,
        target=target,
        services=[service],
        database=database,
        cache=False,
        queue_worker=False,
        load_balancer=(tier != ArchitectureTier.STARTER),
    )


def get_queue_worker_spec(
    target: IaCTarget = IaCTarget.LOCAL_COMPOSE,
    tier: ArchitectureTier = ArchitectureTier.STANDARD,
    app_name: str = "async-app",
    image: str = "python:3.11-slim",
) -> ArchitectureSpec:
    """Web app + cache/broker (Redis) + background worker + database."""
    cpu = 0.5 if tier == ArchitectureTier.STARTER else (1.0 if tier == ArchitectureTier.STANDARD else 2.0)
    memory = 512 if tier == ArchitectureTier.STARTER else (1024 if tier == ArchitectureTier.STANDARD else 2048)

    web_service = ServiceSpec(
        name=f"{app_name}-api",
        image=image,
        port=8000,
        replicas=1 if tier != ArchitectureTier.PRODUCTION else 3,
        cpu_cores=cpu,
        memory_mb=memory,
        environment_vars=["PORT=8000", "REDIS_URL=redis://redis:6379/0", "DATABASE_URL=postgres://..."],
    )
    worker_service = ServiceSpec(
        name=f"{app_name}-worker",
        image=image,
        port=0,
        replicas=1 if tier != ArchitectureTier.PRODUCTION else 2,
        cpu_cores=cpu,
        memory_mb=memory,
        environment_vars=["ROLE=worker", "REDIS_URL=redis://redis:6379/0", "DATABASE_URL=postgres://..."],
    )
    database = DatabaseSpec(
        engine=DatabaseEngine.POSTGRES,
        version="16",
        database_name=f"{app_name.replace('-', '_')}_db",
        storage_gb=20 if tier == ArchitectureTier.STARTER else 50,
        managed=(target != IaCTarget.LOCAL_COMPOSE and tier != ArchitectureTier.STARTER),
    )
    return ArchitectureSpec(
        name=app_name,
        description=f"Asynchronous queue-worker architecture with Redis and Postgres ({tier.value} tier)",
        tier=tier,
        target=target,
        services=[web_service, worker_service],
        database=database,
        cache=True,
        queue_worker=True,
        load_balancer=(tier != ArchitectureTier.STARTER),
    )


def get_microservices_spec(
    target: IaCTarget = IaCTarget.LOCAL_COMPOSE,
    tier: ArchitectureTier = ArchitectureTier.STANDARD,
    cluster_name: str = "microservices-platform",
) -> ArchitectureSpec:
    """Advanced microservices architecture: API gateway + Auth service + Core service + DB + Redis."""
    gateway = ServiceSpec(
        name="api-gateway",
        image="nginx:alpine",
        port=80,
        replicas=1 if tier != ArchitectureTier.PRODUCTION else 2,
        cpu_cores=0.5,
        memory_mb=256,
        environment_vars=["UPSTREAM_SERVICES=auth:8001,core:8002"],
    )
    auth = ServiceSpec(
        name="auth-service",
        image="python:3.11-slim",
        port=8001,
        replicas=1 if tier != ArchitectureTier.PRODUCTION else 2,
        cpu_cores=0.5 if tier == ArchitectureTier.STARTER else 1.0,
        memory_mb=512,
        environment_vars=["SERVICE_NAME=auth", "PORT=8001"],
    )
    core = ServiceSpec(
        name="core-service",
        image="python:3.11-slim",
        port=8002,
        replicas=1 if tier != ArchitectureTier.PRODUCTION else 3,
        cpu_cores=1.0 if tier == ArchitectureTier.STARTER else 2.0,
        memory_mb=1024,
        environment_vars=["SERVICE_NAME=core", "PORT=8002"],
    )
    database = DatabaseSpec(
        engine=DatabaseEngine.POSTGRES,
        version="16",
        database_name="platform_db",
        storage_gb=50 if tier != ArchitectureTier.PRODUCTION else 200,
        managed=(target != IaCTarget.LOCAL_COMPOSE),
    )
    return ArchitectureSpec(
        name=cluster_name,
        description=f"Microservices architecture with API Gateway, Auth and Core services ({tier.value} tier)",
        tier=tier,
        target=target,
        services=[gateway, auth, core],
        database=database,
        cache=True,
        queue_worker=True,
        load_balancer=True,
    )


def get_ai_serving_spec(
    target: IaCTarget = IaCTarget.LOCAL_COMPOSE,
    tier: ArchitectureTier = ArchitectureTier.STANDARD,
    app_name: str = "ai-platform",
    profile: str = "vllm",
    model_name: str = "Qwen/Qwen2.5-Coder-7B-Instruct",
) -> ArchitectureSpec:
    """Web app + vLLM or Ollama serving node + Database (reusing nexcoder-serving)."""
    api = ServiceSpec(
        name="rag-api",
        image="python:3.11-slim",
        port=8000,
        replicas=1 if tier != ArchitectureTier.PRODUCTION else 2,
        cpu_cores=1.0,
        memory_mb=2048,
        environment_vars=[
            "PORT=8000",
            "LLM_ENDPOINT=http://serving:8000/v1" if profile == "vllm" else "http://serving:11434/v1",
        ],
    )
    serving = AIServingSpec(
        enabled=True,
        profile=profile,
        model_name=model_name,
        gpu_count="all" if target == IaCTarget.LOCAL_COMPOSE else "1",
        port=8000 if profile == "vllm" else 11434,
    )
    database = DatabaseSpec(
        engine=DatabaseEngine.POSTGRES,
        version="16",
        database_name="rag_knowledge_db",
        storage_gb=20 if tier == ArchitectureTier.STARTER else 100,
        managed=(target != IaCTarget.LOCAL_COMPOSE and tier != ArchitectureTier.STARTER),
    )
    return ArchitectureSpec(
        name=app_name,
        description=f"AI-enabled architecture with {profile} serving and vector-ready database ({tier.value} tier)",
        tier=tier,
        target=target,
        services=[api],
        database=database,
        cache=True,
        queue_worker=False,
        load_balancer=(tier != ArchitectureTier.STARTER),
        ai_serving=serving,
    )


class ArchitectureCatalog:
    """Registry and factory of reference architectures."""

    ARCHITECTURES: dict[str, dict[str, Any]] = {
        "simple_app": {
            "name": "simple_app",
            "title": "Simple Web Application",
            "description": "Single container or VM running a web server (FastAPI, Node, Go).",
            "factory": get_simple_app_spec,
        },
        "app_database": {
            "name": "app_database",
            "title": "Web Application + Database",
            "description": "Web service with managed or containerized relational database (Postgres/MySQL).",
            "factory": get_app_database_spec,
        },
        "queue_worker": {
            "name": "queue_worker",
            "title": "Queue and Background Worker",
            "description": "Web app with asynchronous background tasks, Redis broker, and database.",
            "factory": get_queue_worker_spec,
        },
        "microservices": {
            "name": "microservices",
            "title": "Microservices Suite",
            "description": "API Gateway, Auth, Core business service, Redis cache, and managed database.",
            "factory": get_microservices_spec,
        },
        "ai_serving": {
            "name": "ai_serving",
            "title": "AI Model Serving & RAG Application",
            "description": "vLLM or Ollama serving node alongside web API and knowledge database.",
            "factory": get_ai_serving_spec,
        },
    }

    @classmethod
    def list_architectures(cls) -> list[dict[str, str]]:
        return [
            {
                "id": k,
                "title": v["title"],
                "description": v["description"],
            }
            for k, v in cls.ARCHITECTURES.items()
        ]

    @classmethod
    def get(
        cls,
        name: str,
        target: IaCTarget = IaCTarget.LOCAL_COMPOSE,
        tier: ArchitectureTier = ArchitectureTier.STANDARD,
        **kwargs: Any,
    ) -> ArchitectureSpec:
        if name not in cls.ARCHITECTURES:
            valid = ", ".join(cls.ARCHITECTURES.keys())
            raise ValueError(f"Unknown architecture '{name}'. Available: {valid}")
        factory = cls.ARCHITECTURES[name]["factory"]
        return factory(target=target, tier=tier, **kwargs)
