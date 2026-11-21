"""Parser transforming high-level natural language descriptions into ArchitectureSpec models."""

from __future__ import annotations

import re

from nexcoder_iac.models import (
    AIServingSpec,
    ArchitectureSpec,
    ArchitectureTier,
    DatabaseEngine,
    DatabaseSpec,
    IaCTarget,
    ServiceSpec,
)


class HighLevelSpecParser:
    """Parses high-level prompts into structured ArchitectureSpec objects."""

    @classmethod
    def parse(
        cls,
        description: str,
        target_override: IaCTarget | None = None,
        tier_override: ArchitectureTier | None = None,
        name: str = "app",
    ) -> ArchitectureSpec:
        """Parse natural language description with deterministic heuristic fallback."""
        text = description.lower()

        # 1. Determine target platform
        target = target_override
        if not target:
            if any(k in text for k in ["aws", "amazon", "ec2", "ecs"]):
                target = IaCTarget.AWS
            elif any(k in text for k in ["hetzner", "hcloud"]):
                target = IaCTarget.HETZNER
            elif any(k in text for k in ["digitalocean", "droplet"]):
                target = IaCTarget.DIGITALOCEAN
            elif any(k in text for k in ["gcp", "google cloud"]):
                target = IaCTarget.GCP
            elif any(k in text for k in ["azure", "microsoft"]):
                target = IaCTarget.AZURE
            elif any(k in text for k in ["vm", "vps", "servidor unico", "dedicated"]):
                target = IaCTarget.VM
            else:
                target = IaCTarget.LOCAL_COMPOSE

        # 2. Determine sizing tier
        tier = tier_override
        if not tier:
            if any(k in text for k in ["prod", "production", "producao", "alta disponibilidade", "ha", "large"]):
                tier = ArchitectureTier.PRODUCTION
            elif any(k in text for k in ["starter", "basico", "pequeno", "micro", "small"]):
                tier = ArchitectureTier.STARTER
            else:
                tier = ArchitectureTier.STANDARD

        # 3. Detect Database
        database: DatabaseSpec | None = None
        if any(k in text for k in ["postgres", "postgresql", "pg"]):
            database = DatabaseSpec(
                engine=DatabaseEngine.POSTGRES,
                version="16",
                database_name=f"{name.replace('-', '_')}_db",
                port=5432,
                storage_gb=20 if tier != ArchitectureTier.PRODUCTION else 100,
                managed=(target != IaCTarget.LOCAL_COMPOSE and tier != ArchitectureTier.STARTER),
            )
        elif any(k in text for k in ["mysql", "mariadb"]):
            database = DatabaseSpec(
                engine=DatabaseEngine.MYSQL,
                version="8.0",
                database_name=f"{name.replace('-', '_')}_db",
                port=3306,
                storage_gb=20 if tier != ArchitectureTier.PRODUCTION else 100,
                managed=(target != IaCTarget.LOCAL_COMPOSE and tier != ArchitectureTier.STARTER),
            )

        # 4. Detect Cache / Queue
        has_redis = any(k in text for k in ["redis", "cache"])
        has_worker = any(k in text for k in ["worker", "fila", "queue", "celery", "rabbitmq"])

        # 5. Detect reverse proxy / load balancer
        has_proxy = any(k in text for k in ["nginx", "proxy", "balanceador", "load balancer", "alb", "caddy"])

        # 6. Detect AI Serving (reusing nexcoder-serving)
        ai_spec: AIServingSpec | None = None
        if any(k in text for k in ["vllm", "ollama", "llm", "serving", "modelo"]):
            profile = "ollama" if "ollama" in text else "vllm"
            ai_spec = AIServingSpec(
                enabled=True,
                profile=profile,
                model_name="Qwen/Qwen2.5-Coder-7B-Instruct",
                gpu_count="all" if target == IaCTarget.LOCAL_COMPOSE else "1",
                port=8000 if profile == "vllm" else 11434,
            )

        # 7. Detect primary service image and language
        image = "python:3.11-slim"
        port = 8000
        if any(k in text for k in ["node", "nodejs", "express", "nest"]):
            image = "node:20-alpine"
            port = 3000
        elif any(k in text for k in ["golang", "go "]):
            image = "golang:1.22-alpine"
            port = 8080
        elif "rust" in text:
            image = "rust:1.77-slim"
            port = 8080

        # Construct primary service
        primary_svc = ServiceSpec(
            name="web",
            image=image,
            port=port,
            replicas=1 if tier != ArchitectureTier.PRODUCTION else 2,
            cpu_cores=1.0 if tier != ArchitectureTier.STARTER else 0.5,
            memory_mb=1024 if tier != ArchitectureTier.STARTER else 512,
            environment_vars=["ENVIRONMENT=production", f"PORT={port}"],
        )
        services = [primary_svc]

        if has_worker:
            worker_svc = ServiceSpec(
                name="worker",
                image=image,
                port=0,
                replicas=1 if tier != ArchitectureTier.PRODUCTION else 2,
                cpu_cores=1.0 if tier != ArchitectureTier.STARTER else 0.5,
                memory_mb=1024 if tier != ArchitectureTier.STARTER else 512,
                environment_vars=["ROLE=worker", "ENVIRONMENT=production"],
            )
            services.append(worker_svc)

        # Sanitize app name
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name).strip("-") or "application"

        return ArchitectureSpec(
            name=clean_name,
            description=description.strip(),
            tier=tier,
            target=target,
            services=services,
            database=database,
            cache=has_redis,
            queue_worker=has_worker,
            load_balancer=has_proxy or (tier == ArchitectureTier.PRODUCTION),
            ai_serving=ai_spec,
        )
