"""Cost estimation and reference pricing catalog for infrastructure targets."""

from __future__ import annotations

from nexcoder_iac.models import ArchitectureSpec, ArchitectureTier, DatabaseEngine, IaCTarget

# Reference monthly costs (USD) for typical starter/standard/production tiers
PRICING_TABLE: dict[IaCTarget, dict[str, dict[ArchitectureTier, float]]] = {
    IaCTarget.LOCAL_COMPOSE: {
        "compute": {ArchitectureTier.STARTER: 0.0, ArchitectureTier.STANDARD: 0.0, ArchitectureTier.PRODUCTION: 0.0},
        "database": {ArchitectureTier.STARTER: 0.0, ArchitectureTier.STANDARD: 0.0, ArchitectureTier.PRODUCTION: 0.0},
        "networking": {
            ArchitectureTier.STARTER: 0.0,
            ArchitectureTier.STANDARD: 0.0,
            ArchitectureTier.PRODUCTION: 0.0,
        },
    },
    IaCTarget.VM: {
        "compute": {
            ArchitectureTier.STARTER: 6.0,
            ArchitectureTier.STANDARD: 18.0,
            ArchitectureTier.PRODUCTION: 48.0,
        },
        "database": {
            ArchitectureTier.STARTER: 0.0,
            ArchitectureTier.STANDARD: 0.0,
            ArchitectureTier.PRODUCTION: 0.0,
        },
        "networking": {
            ArchitectureTier.STARTER: 1.0,
            ArchitectureTier.STANDARD: 2.0,
            ArchitectureTier.PRODUCTION: 5.0,
        },
    },
    IaCTarget.HETZNER: {
        "compute": {
            ArchitectureTier.STARTER: 4.5,  # CX22 (2 vCPU, 4GB RAM)
            ArchitectureTier.STANDARD: 14.0,  # CPX31 (4 vCPU, 8GB RAM)
            ArchitectureTier.PRODUCTION: 32.0,  # CPX41 (8 vCPU, 16GB RAM)
        },
        "database": {
            ArchitectureTier.STARTER: 0.0,  # container on VM
            ArchitectureTier.STANDARD: 8.0,  # dedicated volume
            ArchitectureTier.PRODUCTION: 18.0,  # dedicated database node
        },
        "networking": {
            ArchitectureTier.STARTER: 0.0,
            ArchitectureTier.STANDARD: 2.0,
            ArchitectureTier.PRODUCTION: 6.0,
        },
    },
    IaCTarget.DIGITALOCEAN: {
        "compute": {
            ArchitectureTier.STARTER: 6.0,  # Basic Droplet 1GB
            ArchitectureTier.STANDARD: 24.0,  # Basic Droplet 4GB
            ArchitectureTier.PRODUCTION: 48.0,  # General Purpose Droplet 8GB
        },
        "database": {
            ArchitectureTier.STARTER: 15.0,  # Managed DB 1GB
            ArchitectureTier.STANDARD: 30.0,  # Managed DB 2GB
            ArchitectureTier.PRODUCTION: 60.0,  # Managed DB 4GB + Standby
        },
        "networking": {
            ArchitectureTier.STARTER: 0.0,
            ArchitectureTier.STANDARD: 12.0,  # Load Balancer
            ArchitectureTier.PRODUCTION: 12.0,
        },
    },
    IaCTarget.AWS: {
        "compute": {
            ArchitectureTier.STARTER: 10.5,  # t4g.small / t3.micro
            ArchitectureTier.STANDARD: 38.0,  # t4g.medium / ECS Fargate
            ArchitectureTier.PRODUCTION: 140.0,  # t4g.xlarge / Multi-AZ ECS
        },
        "database": {
            ArchitectureTier.STARTER: 18.0,  # db.t4g.micro single-AZ
            ArchitectureTier.STANDARD: 55.0,  # db.t4g.small single-AZ
            ArchitectureTier.PRODUCTION: 160.0,  # db.t4g.medium Multi-AZ
        },
        "networking": {
            ArchitectureTier.STARTER: 3.0,  # NAT/traffic
            ArchitectureTier.STANDARD: 25.0,  # ALB
            ArchitectureTier.PRODUCTION: 35.0,  # ALB + WAF
        },
    },
    IaCTarget.GCP: {
        "compute": {
            ArchitectureTier.STARTER: 9.0,  # e2-small / Cloud Run
            ArchitectureTier.STANDARD: 34.0,  # e2-medium / Cloud Run
            ArchitectureTier.PRODUCTION: 120.0,  # e2-standard-4
        },
        "database": {
            ArchitectureTier.STARTER: 15.0,  # Cloud SQL db-f1-micro
            ArchitectureTier.STANDARD: 48.0,  # Cloud SQL db-g1-small
            ArchitectureTier.PRODUCTION: 145.0,  # Cloud SQL HA
        },
        "networking": {
            ArchitectureTier.STARTER: 2.0,
            ArchitectureTier.STANDARD: 20.0,
            ArchitectureTier.PRODUCTION: 30.0,
        },
    },
    IaCTarget.AZURE: {
        "compute": {
            ArchitectureTier.STARTER: 12.0,  # B1s / Container Apps
            ArchitectureTier.STANDARD: 42.0,  # B2s / Container Apps
            ArchitectureTier.PRODUCTION: 135.0,  # D2s v5
        },
        "database": {
            ArchitectureTier.STARTER: 16.0,  # Flexible Server B1ms
            ArchitectureTier.STANDARD: 52.0,  # Flexible Server B2s
            ArchitectureTier.PRODUCTION: 150.0,  # Flexible Server Zone Redundant
        },
        "networking": {
            ArchitectureTier.STARTER: 3.0,
            ArchitectureTier.STANDARD: 22.0,  # App Gateway / LB
            ArchitectureTier.PRODUCTION: 35.0,
        },
    },
}

AI_SERVING_MONTHLY_COST: dict[IaCTarget, dict[str, float]] = {
    IaCTarget.LOCAL_COMPOSE: {"ollama": 0.0, "vllm": 0.0},
    IaCTarget.VM: {"ollama": 25.0, "vllm": 75.0},
    IaCTarget.HETZNER: {"ollama": 35.0, "vllm": 95.0},  # GPU server / high memory
    IaCTarget.DIGITALOCEAN: {"ollama": 45.0, "vllm": 120.0},
    IaCTarget.AWS: {"ollama": 80.0, "vllm": 350.0},  # g4dn.xlarge GPU
    IaCTarget.GCP: {"ollama": 75.0, "vllm": 320.0},  # n1-standard + T4
    IaCTarget.AZURE: {"ollama": 85.0, "vllm": 360.0},  # NC6s_v3
}


def estimate_monthly_cost(spec: ArchitectureSpec) -> float:
    """Calculate estimated monthly infrastructure cost in USD based on target and specification."""
    target_table = PRICING_TABLE.get(spec.target, PRICING_TABLE[IaCTarget.LOCAL_COMPOSE])
    tier = spec.tier

    # Base compute cost
    compute_cost = target_table["compute"].get(tier, 0.0)

    # Multiply compute for additional service replicas/count if more than 1
    total_service_count = max(len(spec.services), 1)
    if total_service_count > 1 and spec.target != IaCTarget.LOCAL_COMPOSE:
        compute_cost += (total_service_count - 1) * (compute_cost * 0.4)

    # Database cost
    db_cost = 0.0
    if spec.database and spec.database.engine != DatabaseEngine.NONE:
        db_cost = target_table["database"].get(tier, 0.0)

    # Networking / Load Balancer cost
    net_cost = target_table["networking"].get(tier, 0.0)
    if not spec.load_balancer:
        net_cost = net_cost * 0.2

    # Queue / Cache additions
    extra_cost = 0.0
    if spec.cache and spec.target != IaCTarget.LOCAL_COMPOSE:
        extra_cost += 10.0 if tier == ArchitectureTier.STARTER else 25.0
    if spec.queue_worker and spec.target != IaCTarget.LOCAL_COMPOSE:
        extra_cost += 8.0 if tier == ArchitectureTier.STARTER else 20.0

    # AI Serving addition
    if spec.ai_serving and spec.ai_serving.enabled:
        profile = spec.ai_serving.profile.lower()
        serving_costs = AI_SERVING_MONTHLY_COST.get(spec.target, {})
        extra_cost += serving_costs.get(profile, 50.0)

    total = compute_cost + db_cost + net_cost + extra_cost
    return round(total, 2)
