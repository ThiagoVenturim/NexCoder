from __future__ import annotations

import json

from nexcoder_core.llm.fake import FakeChatModel
from nexcoder_ideation.jury.committee import JuryCommittee
from nexcoder_ideation.jury.personas import STANDARD_JURY_PERSONAS
from nexcoder_ideation.jury.rubric import DEFAULT_RUBRIC
from nexcoder_ideation.models import (
    ComplianceRisk,
    LegalPrivacyData,
    MarketResearchData,
    ResearchSquadReport,
    RubricCriterion,
    StructuredIdea,
    ValueHypothesis,
    VerdictDecision,
)


def _sample_idea() -> StructuredIdea:
    return StructuredIdea(
        title="Automated Test Generation Agent",
        summary="Synthesizes end-to-end integration tests from captured API specs.",
        problem="Writing integration tests is tedious and leads to low test coverage.",
        target_audience=[],
        value_hypothesis=ValueHypothesis(
            problem_statement="Test suites lag behind feature development",
            proposed_solution="Autonomous test synthesizer with mock isolation",
            key_benefit="100% test coverage without manual test scripting",
        ),
        domain_tags=["qa", "testing", "developer-tools"],
    )


def _sample_report(high_risk: bool = False) -> ResearchSquadReport:
    report = ResearchSquadReport(
        idea_id="idea-test-123",
        market=MarketResearchData(tam_estimate="$14.2 Billion (Global)"),
        legal_privacy=LegalPrivacyData(
            risks=[
                ComplianceRisk(
                    area="Data Privacy",
                    risk_level="high" if high_risk else "low",
                    mitigation_strategy="Anonymize test payloads",
                )
            ]
        ),
    )
    return report


def test_standard_jury_personas_completeness() -> None:
    assert len(STANDARD_JURY_PERSONAS) == 6
    slugs = [p.slug for p in STANDARD_JURY_PERSONAS]
    expected = ["investor", "cto", "end-user", "security", "market", "devil-advocate"]
    assert slugs == expected


def test_public_rubric_completeness() -> None:
    assert len(DEFAULT_RUBRIC) == 6
    for crit in RubricCriterion:
        assert crit in DEFAULT_RUBRIC
        assert DEFAULT_RUBRIC[crit].weight > 0.0


def test_jury_verdict_go_consensus() -> None:
    committee = JuryCommittee(quorum_threshold=0.6)
    idea = _sample_idea()
    report = _sample_report(high_risk=False)

    verdict = committee.evaluate(idea, report)

    assert verdict.total_jurors == 6
    assert verdict.go_votes >= 4  # 4 or 5 out of 6
    assert verdict.consensus_reached is True
    assert verdict.verdict == VerdictDecision.GO
    assert len(verdict.ballots) == 6
    assert "average_scores" in verdict.model_dump()
    assert verdict.average_scores["feasibility"] > 3.0
    assert len(verdict.dissenting_opinions) >= 1  # devil-advocate pivots


def test_jury_verdict_no_go_on_high_risk() -> None:
    # Set high quorum threshold or high risk
    committee = JuryCommittee(quorum_threshold=0.7)
    idea = _sample_idea()
    report = _sample_report(high_risk=True)

    verdict = committee.evaluate(idea, report)
    # With high risk, security and investor downvote
    assert verdict.no_go_votes >= 1


def test_jury_with_fake_model() -> None:
    fake_ballot = {
        "vote": "go",
        "scores": {
            "problem": 4.8,
            "market": 4.5,
            "differentiation": 4.6,
            "feasibility": 4.2,
            "risk": 4.0,
            "cost": 4.3,
        },
        "reasoning": "Model-evaluated ballot: Exceptional value proposition.",
        "key_recommendations": ["Accelerate to planning layer"],
        "red_flags": [],
    }
    # 6 responses for 6 jurors
    fake_model = FakeChatModel(responses=[json.dumps(fake_ballot)] * 6)
    committee = JuryCommittee(model=fake_model)

    verdict = committee.evaluate(_sample_idea(), _sample_report())

    assert verdict.verdict == VerdictDecision.GO
    assert verdict.go_votes == 6
    assert verdict.consensus_reached is True
    assert verdict.average_scores["problem"] == 4.8


def test_refine_and_rejudge_cycle() -> None:
    committee = JuryCommittee(quorum_threshold=0.6)
    idea = _sample_idea()
    report = _sample_report()

    verdicts = committee.refine_and_rejudge(idea, report, rounds=2)
    assert len(verdicts) >= 1
    assert verdicts[0].verdict == VerdictDecision.GO
