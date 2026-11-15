"""Docker Compose generator for local containerized deployment targets."""

from __future__ import annotations

import yaml
from nexcoder_serving.compose import ServingConfig, ServingProfile, generate_compose_config

from nexcoder_iac.credentials import generate_env_example, get_required_env_vars, scan_for_secrets
from nexcoder_iac.generators.base import BaseGenerator
from nexcoder_iac.models import (
    ArchitectureSpec,
    DatabaseEngine,
    GeneratedFile,
    IaCArtifacts,
    IaCTarget,
    IaCTool,
)
from nexcoder_iac.pricing import estimate_monthly_cost


class ComposeGenerator(BaseGenerator):
    """Generates Docker Compose configuration files and local running instructions."""

    def generate(self, spec: ArchitectureSpec) -> IaCArtifacts:
        services_dict: dict[str, dict] = {}
        volumes_dict: dict[str, dict] = {}
        networks_dict: dict[str, dict] = {"app-network": {"driver": "bridge"}}

        # 1. Database service if requested
        if spec.database and spec.database.engine != DatabaseEngine.NONE:
            db_engine = spec.database.engine
            db_name = spec.database.database_name
            if db_engine == DatabaseEngine.POSTGRES:
                services_dict["db"] = {
                    "image": f"postgres:{spec.database.version}-alpine",
                    "container_name": f"{spec.name}-postgres",
                    "restart": "unless-stopped",
                    "environment": {
                        "POSTGRES_DB": f"${{DB_NAME:-{db_name}}}",
                        "POSTGRES_USER": "${DB_USER:-appuser}",
                        "POSTGRES_PASSWORD": "${DB_PASSWORD:-localdevpass}",
                    },
                    "ports": [f"{spec.database.port}:5432"],
                    "volumes": [f"{spec.name}_pgdata:/var/lib/postgresql/data"],
                    "networks": ["app-network"],
                }
                volumes_dict[f"{spec.name}_pgdata"] = {"name": f"{spec.name}_pgdata"}
            elif db_engine == DatabaseEngine.MYSQL:
                services_dict["db"] = {
                    "image": f"mysql:{spec.database.version}",
                    "container_name": f"{spec.name}-mysql",
                    "restart": "unless-stopped",
                    "environment": {
                        "MYSQL_DATABASE": f"${{DB_NAME:-{db_name}}}",
                        "MYSQL_USER": "${DB_USER:-appuser}",
                        "MYSQL_PASSWORD": "${DB_PASSWORD:-localdevpass}",
                        "MYSQL_ROOT_PASSWORD": "${DB_ROOT_PASSWORD:-rootpass}",
                    },
                    "ports": [f"{spec.database.port}:3306"],
                    "volumes": [f"{spec.name}_mysqldata:/var/lib/mysql"],
                    "networks": ["app-network"],
                }
                volumes_dict[f"{spec.name}_mysqldata"] = {"name": f"{spec.name}_mysqldata"}

        # 2. Cache / Queue (Redis) if requested
        if spec.cache:
            services_dict["redis"] = {
                "image": "redis:7-alpine",
                "container_name": f"{spec.name}-redis",
                "restart": "unless-stopped",
                "ports": ["6379:6379"],
                "volumes": [f"{spec.name}_redisdata:/data"],
                "networks": ["app-network"],
            }
            volumes_dict[f"{spec.name}_redisdata"] = {"name": f"{spec.name}_redisdata"}

        # 3. AI Serving service if requested (reusing nexcoder-serving)
        if spec.ai_serving and spec.ai_serving.enabled:
            profile_enum = (
                ServingProfile.VLLM if spec.ai_serving.profile.lower() == "vllm" else ServingProfile.OLLAMA
            )
            serving_cfg = ServingConfig(
                profile=profile_enum,
                model_name=spec.ai_serving.model_name,
                port=spec.ai_serving.port,
            )
            serving_compose = generate_compose_config(serving_cfg)
            for s_name, s_def in serving_compose.get("services", {}).items():
                s_def["networks"] = ["app-network"]
                services_dict[s_name] = s_def
            for v_name, v_def in serving_compose.get("volumes", {}).items():
                volumes_dict[v_name] = v_def

        # 4. Application services
        for svc in spec.services:
            svc_env = {}
            for ev in svc.environment_vars:
                if "=" in ev:
                    k, v = ev.split("=", 1)
                    svc_env[k] = v
                else:
                    svc_env[ev] = f"${{{ev}:-}}"

            svc_entry: dict = {
                "image": svc.image,
                "container_name": f"{spec.name}-{svc.name}",
                "restart": "unless-stopped",
                "environment": svc_env,
                "networks": ["app-network"],
            }
            if svc.port > 0:
                svc_entry["ports"] = [f"{svc.port}:{svc.port}"]

            depends = []
            if "db" in services_dict:
                depends.append("db")
            if "redis" in services_dict:
                depends.append("redis")
            if spec.ai_serving and spec.ai_serving.enabled:
                depends.append("vllm" if spec.ai_serving.profile.lower() == "vllm" else "ollama")
            if depends:
                svc_entry["depends_on"] = depends

            services_dict[svc.name] = svc_entry

        # 5. Reverse proxy (Nginx) if load balancer requested
        if spec.load_balancer:
            services_dict["proxy"] = {
                "image": "nginx:alpine",
                "container_name": f"{spec.name}-proxy",
                "restart": "unless-stopped",
                "ports": ["80:80"],
                "networks": ["app-network"],
                "depends_on": [svc.name for svc in spec.services if svc.port > 0],
            }

        compose_root: dict = {
            "version": "3.8",
            "services": services_dict,
            "networks": networks_dict,
        }
        if volumes_dict:
            compose_root["volumes"] = volumes_dict

        compose_yaml = yaml.dump(compose_root, sort_keys=False, default_flow_style=False)
        env_example = generate_env_example(IaCTarget.LOCAL_COMPOSE, spec)

        # Instructions
        instructions = (
            f"# Running {spec.name} locally with Docker Compose\n\n"
            "## 1. Setup Environment\n"
            "```bash\n"
            "cp .env.example .env\n"
            "# Edit .env with your local credentials if needed\n"
            "```\n\n"
            "## 2. Start Services\n"
            "```bash\n"
            "docker compose up -d\n"
            "```\n\n"
            "## 3. View Status and Logs\n"
            "```bash\n"
            "docker compose ps\n"
            "docker compose logs -f\n"
            "```\n\n"
            "## 4. Teardown\n"
            "```bash\n"
            "docker compose down -v\n"
            "```\n"
        )

        files = [
            GeneratedFile(
                filename="docker-compose.yml",
                content=compose_yaml,
                file_type="yaml",
                description="Docker Compose multi-container stack definition",
            ),
            GeneratedFile(
                filename=".env.example",
                content=env_example,
                file_type="env",
                description="Sample environment configuration with safe placeholders",
            ),
            GeneratedFile(
                filename="README.md",
                content=instructions,
                file_type="markdown",
                description="Local deployment setup and teardown instructions",
            ),
        ]

        # Scan for accidental secrets
        for f in files:
            findings = scan_for_secrets(f.content)
            if findings:
                raise ValueError(f"Secret detected in generated file {f.filename}: {findings}")

        monthly_cost = estimate_monthly_cost(spec)
        return IaCArtifacts(
            spec=spec,
            target=IaCTarget.LOCAL_COMPOSE,
            tool=IaCTool.COMPOSE,
            files=files,
            instructions=instructions,
            required_env_vars=get_required_env_vars(IaCTarget.LOCAL_COMPOSE),
            estimated_monthly_cost_usd=monthly_cost,
        )
