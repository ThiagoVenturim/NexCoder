from __future__ import annotations

from pydantic import BaseModel, Field

from faccoder_ideation.models import RubricCriterion


class JurorPersonaConfig(BaseModel):
    """Specification of a committee juror role, perspective, and criterion weights."""

    slug: str
    name: str
    role: str
    perspective: str
    priority_criteria: list[RubricCriterion] = Field(default_factory=list)
    voting_bias_description: str = ""


STANDARD_JURY_PERSONAS: list[JurorPersonaConfig] = [
    JurorPersonaConfig(
        slug="investor",
        name="Elena Vance (Venture Partner)",
        role="Investor & Capital Allocator",
        perspective="Market Size, Unit Economics, Monetization Scalability, and Venture ROI",
        priority_criteria=[RubricCriterion.MARKET, RubricCriterion.COST, RubricCriterion.PROBLEM],
        voting_bias_description="Looks for massive TAM, high margins, and defensible moats. Penalizes low upside.",
    ),
    JurorPersonaConfig(
        slug="cto",
        name="Dr. Aris Thorne (Chief Technology Officer)",
        role="CTO & System Architect",
        perspective="System Architecture, Technical Feasibility, Code Quality, and Complexity Budget",
        priority_criteria=[RubricCriterion.FEASIBILITY, RubricCriterion.DIFFERENTIATION, RubricCriterion.COST],
        voting_bias_description="Demands clean architecture, offline testability, and sensible dependency choices.",
    ),
    JurorPersonaConfig(
        slug="end-user",
        name="Samira Khan (Principal Engineer & Practitioner)",
        role="End-User & Developer Experience Advocate",
        perspective="Daily Workflow Integration, Ergonomics, Immediate Utility, and Low Friction",
        priority_criteria=[RubricCriterion.PROBLEM, RubricCriterion.FEASIBILITY, RubricCriterion.DIFFERENTIATION],
        voting_bias_description="Advocates for usability. Harshly critiques tools that add friction or noise.",
    ),
    JurorPersonaConfig(
        slug="security",
        name="Marcus Vance (Chief Information Security Officer)",
        role="CISO & Compliance Officer",
        perspective="Vulnerability Surface, Data Sovereignty, Regulatory Adherence (GDPR/AI Act)",
        priority_criteria=[RubricCriterion.RISK, RubricCriterion.FEASIBILITY],
        voting_bias_description="Zero tolerance for data leaks, unsecured token storage, or missing audit logs.",
    ),
    JurorPersonaConfig(
        slug="market",
        name="Clara Oswald (VP of Product Marketing)",
        role="Product Strategist & Market Scout",
        perspective="Positioning, Competitive Counter-Moves, Messaging Clarity, and Category Creation",
        priority_criteria=[RubricCriterion.DIFFERENTIATION, RubricCriterion.MARKET, RubricCriterion.PROBLEM],
        voting_bias_description="Requires distinctive positioning against incumbents and clear customer segmentation.",
    ),
    JurorPersonaConfig(
        slug="devil-advocate",
        name="Dr. Julian Croft (Contrarian Challenger)",
        role="Devil's Advocate & Failure Analyst",
        perspective="Worst-Case Scenarios, Hidden Assumptions, Premature Optimization, and Fatal Flaws",
        priority_criteria=[RubricCriterion.RISK, RubricCriterion.PROBLEM, RubricCriterion.COST],
        voting_bias_description="Actively searches for reasons the idea will fail. Identifies blind spots.",
    ),
]
