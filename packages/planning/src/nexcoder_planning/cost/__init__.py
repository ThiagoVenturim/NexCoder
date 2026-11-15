"""Cost calculator module for estimating build, publication, recurring maintenance, and IP licensing."""

from nexcoder_planning.cost.calculator import ProductCostCalculator
from nexcoder_planning.cost.catalog import PricingCatalog
from nexcoder_planning.cost.control_plane import extract_ai_spec_from_tracker
from nexcoder_planning.cost.models import (
    AISpec,
    CostItemBreakdown,
    CostScenarioDetail,
    CostScope,
    Currency,
    DevelopmentMode,
    InfrastructureTarget,
    InfrastructureTier,
    LicenseBrandSpec,
    ProductCostInput,
    ProductCostReport,
    ProviderSpec,
    ScopeComplexity,
    TeamSpec,
)
from nexcoder_planning.cost.proposal import CommercialProposalGenerator

__all__ = [
    "AISpec",
    "CommercialProposalGenerator",
    "CostItemBreakdown",
    "CostScenarioDetail",
    "CostScope",
    "Currency",
    "DevelopmentMode",
    "InfrastructureTarget",
    "InfrastructureTier",
    "LicenseBrandSpec",
    "PricingCatalog",
    "ProductCostCalculator",
    "ProductCostInput",
    "ProductCostReport",
    "ProviderSpec",
    "ScopeComplexity",
    "TeamSpec",
    "extract_ai_spec_from_tracker",
]
