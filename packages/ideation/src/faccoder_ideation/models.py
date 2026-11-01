from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class VerdictDecision(StrEnum):
    """Jury quorum decision options."""

    GO = "go"
    PIVOT = "pivot"
    NO_GO = "no-go"


class RawIdea(BaseModel):
    """Unstructured initial idea provided by a user."""

    raw_text: str = Field(..., min_length=5, description="Initial free-text idea description.")
    author: str = Field(default="user", description="Identifier of the idea submitter.")
    context: dict[str, Any] = Field(default_factory=dict, description="Optional extra business or technical context.")


class AudienceSegment(BaseModel):
    """Identified target customer or user segment."""

    name: str
    description: str
    pain_points: list[str] = Field(default_factory=list)
    willingness_to_pay: str = "medium"  # low, medium, high


class ValueHypothesis(BaseModel):
    """Core value proposition and expected outcome."""

    problem_statement: str
    proposed_solution: str
    key_benefit: str
    differentiation_summary: str = ""
    primary_metric: str = ""


class StructuredIdea(BaseModel):
    """Structured idea produced by idea-analyst agent."""

    id: str = Field(default_factory=lambda: f"idea-{uuid.uuid4().hex[:8]}")
    title: str
    summary: str
    problem: str
    target_audience: list[AudienceSegment] = Field(default_factory=list)
    value_hypothesis: ValueHypothesis
    domain_tags: list[str] = Field(default_factory=list)
    initial_assumptions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ResearchSource(BaseModel):
    """Source citation captured during research."""

    id: str = Field(default_factory=lambda: f"src-{uuid.uuid4().hex[:6]}")
    title: str
    url: str
    snippet: str
    provider: str = "mock"  # tavily, serpapi, brave, duckduckgo, mock
    relevance_score: float = 1.0
    published_date: str | None = None


class ResearchFinding(BaseModel):
    """Specific finding produced by a research squad specialist."""

    agent_name: str
    topic: str
    key_insights: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    sources: list[ResearchSource] = Field(default_factory=list)
    confidence: float = 1.0


class MarketResearchData(BaseModel):
    """Market size, trends, and growth indicators."""

    tam_estimate: str = "N/A"  # Total Addressable Market
    sam_estimate: str = "N/A"  # Serviceable Addressable Market
    som_estimate: str = "N/A"  # Serviceable Obtainable Market
    cagr_percentage: float | None = None
    market_trends: list[str] = Field(default_factory=list)
    growth_drivers: list[str] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)


class CompetitorProfile(BaseModel):
    """Direct or indirect competitor details."""

    name: str
    website: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    pricing_model: str = ""
    market_share_estimate: str = ""


class CompetitorScoutData(BaseModel):
    """Direct and indirect market competitors found."""

    direct_competitors: list[CompetitorProfile] = Field(default_factory=list)
    indirect_competitors: list[CompetitorProfile] = Field(default_factory=list)
    market_leaders: list[str] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)


class DifferentiationItem(BaseModel):
    """Comparison dimension against competitor offerings."""

    feature_dimension: str
    our_approach: str
    competitors_approach: str
    advantage_level: str = "high"  # low, medium, high, parity


class DifferentiatorData(BaseModel):
    """Differentiation matrix and defensibility strategy."""

    differentiation_matrix: list[DifferentiationItem] = Field(default_factory=list)
    positioning_statement: str = ""
    moat_factors: list[str] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)


class GapData(BaseModel):
    """Unaddressed customer complaints and market voids."""

    unmet_needs: list[str] = Field(default_factory=list)
    customer_complaints: list[str] = Field(default_factory=list)
    underserved_niches: list[str] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)


class SyntheticPersona(BaseModel):
    """Representative persona generated from user voice analysis."""

    name: str
    role_or_title: str
    daily_goals: list[str] = Field(default_factory=list)
    major_frustrations: list[str] = Field(default_factory=list)
    quote: str = ""


class UserVoiceData(BaseModel):
    """User feedback patterns and synthetic personas with evidence."""

    personas: list[SyntheticPersona] = Field(default_factory=list)
    evidence_points: list[str] = Field(default_factory=list)
    interview_simulations: list[dict[str, str]] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)


class PricingTier(BaseModel):
    """Recommended pricing tier."""

    name: str
    price_point: str
    billing_period: str = "monthly"
    target_persona: str = ""
    features_included: list[str] = Field(default_factory=list)


class PricingData(BaseModel):
    """Pricing strategy and willingness-to-pay findings."""

    recommended_model: str = "usage_based"  # freemium, tiered, usage_based, flat
    pricing_tiers: list[PricingTier] = Field(default_factory=list)
    margin_considerations: str = ""
    sources: list[ResearchSource] = Field(default_factory=list)


class ComplianceRisk(BaseModel):
    """Identified regulatory or legal risk item."""

    area: str  # GDPR, LGPD, HIPAA, Copyright, AI ethics
    risk_level: str = "medium"  # low, medium, high
    mitigation_strategy: str


class LegalPrivacyData(BaseModel):
    """Legal, compliance, and data privacy evaluation."""

    applicable_frameworks: list[str] = Field(default_factory=list)
    risks: list[ComplianceRisk] = Field(default_factory=list)
    data_retention_policy_advice: str = ""
    sources: list[ResearchSource] = Field(default_factory=list)


class ResearchSquadReport(BaseModel):
    """Consolidated report across all research squad members."""

    idea_id: str
    market: MarketResearchData = Field(default_factory=MarketResearchData)
    competitors: CompetitorScoutData = Field(default_factory=CompetitorScoutData)
    differentiation: DifferentiatorData = Field(default_factory=DifferentiatorData)
    gaps: GapData = Field(default_factory=GapData)
    user_voice: UserVoiceData = Field(default_factory=UserVoiceData)
    pricing: PricingData = Field(default_factory=PricingData)
    legal_privacy: LegalPrivacyData = Field(default_factory=LegalPrivacyData)
    all_sources: list[ResearchSource] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RubricCriterion(StrEnum):
    """Standard rubric evaluation dimensions."""

    PROBLEM = "problem"
    MARKET = "market"
    DIFFERENTIATION = "differentiation"
    FEASIBILITY = "feasibility"
    RISK = "risk"
    COST = "cost"


class RubricScore(BaseModel):
    """Score for a specific rubric dimension."""

    criterion: RubricCriterion
    score: float = Field(..., ge=1.0, le=5.0, description="Score on 1.0 to 5.0 scale.")
    justification: str


class JurorBallot(BaseModel):
    """Vote and review submitted by an individual committee juror."""

    juror_name: str
    role: str
    perspective: str
    vote: VerdictDecision
    scores: list[RubricScore] = Field(default_factory=list)
    overall_score: float = Field(default=3.0, ge=1.0, le=5.0)
    reasoning: str
    key_recommendations: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)


class JuryVerdict(BaseModel):
    """Consolidated outcome of the b90 jury committee evaluation."""

    verdict: VerdictDecision
    consensus_reached: bool
    quorum_threshold: float = 0.6
    go_votes: int
    pivot_votes: int
    no_go_votes: int
    total_jurors: int
    ballots: list[JurorBallot] = Field(default_factory=list)
    average_scores: dict[str, float] = Field(default_factory=dict)
    dissenting_opinions: list[str] = Field(default_factory=list)
    consolidated_recommendations: list[str] = Field(default_factory=list)
    summary: str
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ComponentSpec(BaseModel):
    """Architectural building block specification."""

    name: str
    purpose: str
    technology_choices: list[str] = Field(default_factory=list)
    data_stores: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class ArchitectureProposal(BaseModel):
    """Preliminary system architecture draft for the proposed idea."""

    system_name: str
    components: list[ComponentSpec] = Field(default_factory=list)
    data_flow_description: str
    integration_points: list[str] = Field(default_factory=list)
    security_controls: list[str] = Field(default_factory=list)
    deployment_model: str = "Cloud-native / Containerized"


class GateStatus(StrEnum):
    """Lifecycle status of the human approval gate."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class HumanApprovalGate(BaseModel):
    """b85 human gate status before proceeding to planning layer."""

    required: bool = True
    status: GateStatus = GateStatus.PENDING
    token_hash: str = ""
    created_at: float = Field(default_factory=time.time)
    expires_at: float = Field(default_factory=lambda: time.time() + 1800.0)  # 30 minutes default
    consumed: bool = False
    approved: bool = False
    approved_by: str | None = None
    approval_timestamp: datetime | None = None
    comments: str = ""


class IdeationOutput(BaseModel):
    """Full deliverable package produced by the ideation floor."""

    structured_idea: StructuredIdea
    research_report: ResearchSquadReport
    jury_verdict: JuryVerdict
    architecture: ArchitectureProposal
    approval_gate: HumanApprovalGate = Field(default_factory=HumanApprovalGate)
    markdown_report: str = ""
    html_report: str = ""
