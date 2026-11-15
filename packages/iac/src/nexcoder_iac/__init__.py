"""nexcoder-iac: Infrastructure as Code generation, catalog, cost estimation, and audit."""

from __future__ import annotations

from nexcoder_iac.catalog import ArchitectureCatalog
from nexcoder_iac.credentials import (
    generate_env_example,
    get_required_env_vars,
    scan_for_secrets,
    verify_user_credentials,
)
from nexcoder_iac.engine import IaCEngine
from nexcoder_iac.generators.ansible import AnsibleGenerator
from nexcoder_iac.generators.compose import ComposeGenerator
from nexcoder_iac.generators.parser import HighLevelSpecParser
from nexcoder_iac.generators.terraform import TerraformGenerator
from nexcoder_iac.models import (
    AIServingSpec,
    ApplyResult,
    ArchitectureSpec,
    ArchitectureTier,
    DatabaseEngine,
    DatabaseSpec,
    GeneratedFile,
    IaCArtifacts,
    IaCTarget,
    IaCTool,
    PlanAction,
    PlanPreview,
    ResourcePlan,
    ServiceSpec,
)
from nexcoder_iac.pipeline import create_iac_pipeline, run_iac_workflow
from nexcoder_iac.pricing import estimate_monthly_cost

__version__ = "0.1.0"

__all__ = [
    "AIServingSpec",
    "AnsibleGenerator",
    "ApplyResult",
    "ArchitectureCatalog",
    "ArchitectureSpec",
    "ArchitectureTier",
    "ComposeGenerator",
    "DatabaseEngine",
    "DatabaseSpec",
    "GeneratedFile",
    "HighLevelSpecParser",
    "IaCArtifacts",
    "IaCEngine",
    "IaCTarget",
    "IaCTool",
    "PlanAction",
    "PlanPreview",
    "ResourcePlan",
    "ServiceSpec",
    "TerraformGenerator",
    "create_iac_pipeline",
    "estimate_monthly_cost",
    "generate_env_example",
    "get_required_env_vars",
    "run_iac_workflow",
    "scan_for_secrets",
    "verify_user_credentials",
]
