from __future__ import annotations

from pydantic import BaseModel, Field

from nexcoder_ideation.models import RubricCriterion


class RubricDefinition(BaseModel):
    """Specification of a rubric evaluation dimension."""

    criterion: RubricCriterion
    title: str
    description: str
    weight: float = 1.0
    key_questions: list[str] = Field(default_factory=list)


DEFAULT_RUBRIC: dict[RubricCriterion, RubricDefinition] = {
    RubricCriterion.PROBLEM: RubricDefinition(
        criterion=RubricCriterion.PROBLEM,
        title="Problem Severity & Validation",
        description="Depth of acute pain, urgency, and empirical verification of customer friction.",
        weight=1.2,
        key_questions=[
            "Is the problem critical, frequent, or painful enough that users actively seek solutions?",
            "Is there verified evidence of current workarounds or costly inefficiencies?",
        ],
    ),
    RubricCriterion.MARKET: RubricDefinition(
        criterion=RubricCriterion.MARKET,
        title="Market Opportunity & TAM",
        description="Size of addressable market, expansion trends, and commercial demand.",
        weight=1.0,
        key_questions=[
            "Is the total addressable market large enough to support a viable product line?",
            "Are growth tailwinds (CAGR, regulatory catalysts) supporting market expansion?",
        ],
    ),
    RubricCriterion.DIFFERENTIATION: RubricDefinition(
        criterion=RubricCriterion.DIFFERENTIATION,
        title="Differentiation & Moat",
        description="Distinctive architectural or workflow advantage against established incumbents.",
        weight=1.1,
        key_questions=[
            "Does the product offer a 10x improvement on a critical dimension (e.g. speed, verification)?",
            "Can the advantage be defended against rapid replication by well-funded rivals?",
        ],
    ),
    RubricCriterion.FEASIBILITY: RubricDefinition(
        criterion=RubricCriterion.FEASIBILITY,
        title="Technical Feasibility",
        description="Engineering pragmatism, availability of underlying technologies, and delivery horizon.",
        weight=1.2,
        key_questions=[
            "Can this architecture be reliably implemented with proven software patterns?",
            "Are external dependencies (models, APIs, runtimes) stable and deterministically testable?",
        ],
    ),
    RubricCriterion.RISK: RubricDefinition(
        criterion=RubricCriterion.RISK,
        title="Risk & Compliance Surface",
        description="Security vulnerabilities, legal compliance exposure, and adoption blockers.",
        weight=1.0,
        key_questions=[
            "Are data sovereignty, compliance (GDPR/AI Act), and security boundaries respected?",
            "Does the solution expose users to unacceptable operational or reputational risks?",
        ],
    ),
    RubricCriterion.COST: RubricDefinition(
        criterion=RubricCriterion.COST,
        title="Operational Cost & Unit Economics",
        description="Infrastructure burn, inference overhead, and operational maintenance margin.",
        weight=0.9,
        key_questions=[
            "Can the product achieve sustainable gross margins (>75%) at production scale?",
            "Does the inference cost scale sub-linearly with customer value delivered?",
        ],
    ),
}
