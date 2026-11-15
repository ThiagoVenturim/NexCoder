"""Domain models for product cost calculation across build, publish, maintain, and license."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Currency(StrEnum):
    """Supported valuation currencies."""

    BRL = "BRL"
    USD = "USD"


class ScopeComplexity(StrEnum):
    """Product development scope complexity tier."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    ENTERPRISE = "enterprise"


class DevelopmentMode(StrEnum):
    """Delivery execution model."""

    HUMAN_TEAM = "human_team"
    HYBRID = "hybrid"
    AI_ONLY = "ai_only"


class InfrastructureTarget(StrEnum):
    """Infrastructure cloud or on-premise target (aligns with nexcoder_iac)."""

    LOCAL_COMPOSE = "local_compose"
    VM = "vm"
    HETZNER = "hetzner"
    DIGITALOCEAN = "digitalocean"
    AWS = "aws"
    GCP = "gcp"


class InfrastructureTier(StrEnum):
    """Infrastructure performance and redundancy tier."""

    STARTER = "starter"
    STANDARD = "standard"
    PRODUCTION = "production"


class CostScope(BaseModel):
    """Scope specification defining functional complexity and architectural style."""

    project_name: str
    description: str = ""
    complexity: ScopeComplexity = ScopeComplexity.MEDIUM
    feature_count: int = 10
    estimated_screens: int = 5
    estimated_endpoints: int = 12
    stack: str = "python_fastapi_react"
    architecture_style: str = "modular_monolith"


class TeamSpec(BaseModel):
    """Engineering squad parameters for human delivery."""

    total_hours: float | None = None
    hourly_rate: float | None = None
    roles: dict[str, int] = Field(default_factory=lambda: {"senior": 1, "mid": 1, "qa_engineer": 1})
    role_rates: dict[str, float] = Field(default_factory=dict)


class AISpec(BaseModel):
    """Model token consumption and AI agent execution parameters."""

    estimated_tokens_input: int = 500_000
    estimated_tokens_output: int = 150_000
    model_tier: str = "medium"  # small, medium, large
    estimated_runs: int = 20
    control_plane_cost_usd: float | None = None
    control_plane_metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderSpec(BaseModel):
    """Third-party hosting, database, domain, and SaaS service selections."""

    hosting_target: InfrastructureTarget = InfrastructureTarget.HETZNER
    hosting_tier: InfrastructureTier = InfrastructureTier.STANDARD
    database_type: str = "standard"  # container, managed, cluster
    domain_tld: str = "com_br"  # com_br, com, io, ai
    email_provider: str = "google_workspace"  # none, ses, google_workspace, proton
    cdn_security: str = "cloudflare_free"  # cloudflare_free, cloudflare_pro, cloudfront_waf
    storage_backup: str = "s3_standard"  # local, s3_standard, s3_redundant
    monitoring: str = "standard_cloud"  # free_tier, standard_cloud, datadog_pro
    commercial_licenses_monthly: float = 0.0


class LicenseBrandSpec(BaseModel):
    """Intellectual property, trademark, and recurring governance options."""

    trademark_jurisdiction: str = "inpi_br"  # inpi_br, uspto_us, none
    trademark_classes_count: int = 1
    include_legal_assistance: bool = True
    software_license_initial_cost: float = 0.0
    software_license_annual_cost: float = 0.0


class ProductCostInput(BaseModel):
    """Comprehensive input payload for product cost estimation."""

    scope: CostScope
    mode: DevelopmentMode = DevelopmentMode.HYBRID
    team: TeamSpec = Field(default_factory=TeamSpec)
    ai: AISpec = Field(default_factory=AISpec)
    providers: ProviderSpec = Field(default_factory=ProviderSpec)
    license_brand: LicenseBrandSpec = Field(default_factory=LicenseBrandSpec)
    currency: Currency = Currency.BRL
    exchange_rate_usd_to_brl: float = 5.50
    contingency_percentage: float = 0.10


class CostItemBreakdown(BaseModel):
    """Granular cost element detailing category, amount, period, and source."""

    item_id: str
    name: str
    category: str
    amount: float
    currency: Currency
    billing_period: Literal["one_time", "monthly", "annual"]
    source: str
    notes: str = ""


class CostScenarioDetail(BaseModel):
    """Complete cost summary and itemized line items for a specific execution scenario."""

    scenario: Literal["basic", "medium", "high"]
    description: str
    development_cost: float
    publication_cost: float
    monthly_recurring_cost: float
    annual_recurring_cost: float
    license_and_brand_initial_cost: float
    license_and_brand_annual_cost: float
    contingency_cost: float
    year_one_total: float
    subsequent_years_annual_total: float
    breakdown_items: list[CostItemBreakdown] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class ProductCostReport(BaseModel):
    """Aggregated financial estimation report across scenarios with sources and proposal."""

    project_name: str
    currency: Currency
    exchange_rate_usd_to_brl: float
    development_mode: DevelopmentMode
    scenarios: dict[str, CostScenarioDetail]
    recommended_scenario: str = "medium"
    pricing_sources: list[str] = Field(default_factory=list)
    control_plane_integration: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=str)

    def summary_table(self) -> str:
        """Render a clean text table comparing basic, medium, and high scenarios."""
        c = self.currency.value
        header = f"| Item / Metrica | Basico ({c}) | Medio ({c}) | Alto ({c}) |"
        sep = "|---|---|---|---|"
        rows = [header, sep]

        keys = [
            ("Desenvolvimento", "development_cost"),
            ("Publicacao (Setup)", "publication_cost"),
            ("Licenca e Marca (Inicial)", "license_and_brand_initial_cost"),
            ("Recorrente Mensal", "monthly_recurring_cost"),
            ("Recorrente Anual", "annual_recurring_cost"),
            ("Contingencia", "contingency_cost"),
            ("Total Ano 1", "year_one_total"),
            ("Total Anos Seguintes (Anual)", "subsequent_years_annual_total"),
        ]

        for label, attr in keys:
            b_val = getattr(self.scenarios.get("basic"), attr, 0.0)
            m_val = getattr(self.scenarios.get("medium"), attr, 0.0)
            h_val = getattr(self.scenarios.get("high"), attr, 0.0)
            rows.append(f"| {label} | {b_val:,.2f} | {m_val:,.2f} | {h_val:,.2f} |")

        return "\n".join(rows)
