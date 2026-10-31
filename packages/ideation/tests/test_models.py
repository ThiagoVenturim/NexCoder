from __future__ import annotations

import pytest
from faccoder_ideation.models import (
    AudienceSegment,
    HumanApprovalGate,
    JurorBallot,
    JuryVerdict,
    RawIdea,
    ResearchSource,
    RubricCriterion,
    RubricScore,
    StructuredIdea,
    ValueHypothesis,
    VerdictDecision,
)
from pydantic import ValidationError


def test_raw_idea_validation() -> None:
    idea = RawIdea(raw_text="A tool for automated code generation from whiteboard sketches.")
    assert "whiteboard sketches" in idea.raw_text
    assert idea.author == "user"

    with pytest.raises(ValidationError):
        RawIdea(raw_text="tiny")  # min_length=5


def test_structured_idea_creation() -> None:
    structured = StructuredIdea(
        title="Sketch2Code AI",
        summary="Converts hand-drawn wireframes into production code.",
        problem="Frontend teams spend too much time turning drawings into markup.",
        target_audience=[
            AudienceSegment(
                name="Frontend Developers",
                description="Devs building web apps",
                pain_points=["Repetitive CSS styling"],
            )
        ],
        value_hypothesis=ValueHypothesis(
            problem_statement="Manual styling is slow",
            proposed_solution="Deep learning vision to code",
            key_benefit="10x faster prototyping",
        ),
        domain_tags=["ai", "frontend"],
    )
    assert structured.title == "Sketch2Code AI"
    assert structured.id.startswith("idea-")
    assert len(structured.target_audience) == 1
    assert structured.target_audience[0].willingness_to_pay == "medium"


def test_research_source_creation() -> None:
    src = ResearchSource(
        title="2026 Developer Tooling Report",
        url="https://reports.analyst-insights.org/dev-tools",
        snippet="Dev teams report 45% productivity gains with automated assistants.",
        provider="mock",
    )
    assert src.id.startswith("src-")
    assert src.relevance_score == 1.0


def test_rubric_and_ballot() -> None:
    scores = [
        RubricScore(criterion=RubricCriterion.PROBLEM, score=4.5, justification="Clear market pain"),
        RubricScore(criterion=RubricCriterion.FEASIBILITY, score=4.0, justification="Proven technology components"),
        RubricScore(criterion=RubricCriterion.RISK, score=2.5, justification="High competition in AI vision space"),
    ]
    ballot = JurorBallot(
        juror_name="investor-eva",
        role="investor",
        perspective="Market Size and ROI",
        vote=VerdictDecision.GO,
        scores=scores,
        overall_score=4.2,
        reasoning="Strong upside potential with scalable unit economics.",
        key_recommendations=["Focus on enterprise security first"],
    )
    assert ballot.vote == VerdictDecision.GO
    assert len(ballot.scores) == 3


def test_jury_verdict_and_approval_gate() -> None:
    verdict = JuryVerdict(
        verdict=VerdictDecision.GO,
        consensus_reached=True,
        quorum_threshold=0.6,
        go_votes=5,
        pivot_votes=1,
        no_go_votes=0,
        total_jurors=6,
        ballots=[],
        summary="Unanimous support to advance with enterprise focus.",
    )
    assert verdict.verdict == VerdictDecision.GO
    assert verdict.go_votes == 5

    gate = HumanApprovalGate()
    assert gate.required is True
    assert gate.approved is False
