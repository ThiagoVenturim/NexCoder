from __future__ import annotations

from nexcoder_ideation.intake import IdeaAnalyst
from nexcoder_ideation.jury.committee import JuryCommittee
from nexcoder_ideation.jury.personas import STANDARD_JURY_PERSONAS, JurorPersonaConfig
from nexcoder_ideation.jury.rubric import DEFAULT_RUBRIC, RubricDefinition
from nexcoder_ideation.models import (
    ArchitectureProposal,
    AudienceSegment,
    ComponentSpec,
    GateStatus,
    HumanApprovalGate,
    IdeationOutput,
    JurorBallot,
    JuryVerdict,
    RawIdea,
    ResearchFinding,
    ResearchSource,
    ResearchSquadReport,
    RubricCriterion,
    RubricScore,
    StructuredIdea,
    ValueHypothesis,
    VerdictDecision,
)
from nexcoder_ideation.output.architecture import ArchitectureDesigner
from nexcoder_ideation.output.gate import HumanGateManager
from nexcoder_ideation.output.prd import PRDGenerator
from nexcoder_ideation.output.report import ReportGenerator
from nexcoder_ideation.pipeline import IdeationPipeline
from nexcoder_ideation.research.base import BaseResearcher
from nexcoder_ideation.research.specialists import (
    CompetitorScout,
    DifferentiatorAnalyst,
    GapHunter,
    LegalPrivacyResearcher,
    MarketResearcher,
    PricingResearcher,
    UserVoiceResearcher,
)
from nexcoder_ideation.research.squad import ResearchSquad
from nexcoder_ideation.search.base import SearchProvider
from nexcoder_ideation.search.providers import (
    DuckDuckGoSearchProvider,
    MockSearchProvider,
    get_search_provider,
)

__all__ = [
    "ArchitectureDesigner",
    "ArchitectureProposal",
    "AudienceSegment",
    "BaseResearcher",
    "CompetitorScout",
    "ComponentSpec",
    "DEFAULT_RUBRIC",
    "DifferentiatorAnalyst",
    "DuckDuckGoSearchProvider",
    "GapHunter",
    "GateStatus",
    "HumanApprovalGate",
    "HumanGateManager",
    "IdeaAnalyst",
    "IdeationOutput",
    "IdeationPipeline",
    "JurorBallot",
    "JurorPersonaConfig",
    "JuryCommittee",
    "JuryVerdict",
    "LegalPrivacyResearcher",
    "MarketResearcher",
    "MockSearchProvider",
    "PRDGenerator",
    "PricingResearcher",
    "RawIdea",
    "ReportGenerator",
    "ResearchFinding",
    "ResearchSource",
    "ResearchSquad",
    "ResearchSquadReport",
    "RubricCriterion",
    "RubricDefinition",
    "RubricScore",
    "STANDARD_JURY_PERSONAS",
    "SearchProvider",
    "StructuredIdea",
    "UserVoiceResearcher",
    "ValueHypothesis",
    "VerdictDecision",
    "get_search_provider",
]
