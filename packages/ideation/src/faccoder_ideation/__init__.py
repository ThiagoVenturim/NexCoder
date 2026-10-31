from __future__ import annotations

from faccoder_ideation.intake import IdeaAnalyst
from faccoder_ideation.jury.committee import JuryCommittee
from faccoder_ideation.jury.personas import STANDARD_JURY_PERSONAS, JurorPersonaConfig
from faccoder_ideation.jury.rubric import DEFAULT_RUBRIC, RubricDefinition
from faccoder_ideation.models import (
    ArchitectureProposal,
    AudienceSegment,
    ComponentSpec,
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
from faccoder_ideation.output.architecture import ArchitectureDesigner
from faccoder_ideation.output.gate import HumanGateManager
from faccoder_ideation.output.prd import PRDGenerator
from faccoder_ideation.output.report import ReportGenerator
from faccoder_ideation.pipeline import IdeationPipeline
from faccoder_ideation.research.base import BaseResearcher
from faccoder_ideation.research.specialists import (
    CompetitorScout,
    DifferentiatorAnalyst,
    GapHunter,
    LegalPrivacyResearcher,
    MarketResearcher,
    PricingResearcher,
    UserVoiceResearcher,
)
from faccoder_ideation.research.squad import ResearchSquad
from faccoder_ideation.search.base import SearchProvider
from faccoder_ideation.search.providers import (
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
