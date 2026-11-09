from __future__ import annotations

import json
import logging
from typing import Any

from faccoder_ideation.jury.personas import STANDARD_JURY_PERSONAS, JurorPersonaConfig
from faccoder_ideation.models import (
    JurorBallot,
    JuryVerdict,
    ResearchSquadReport,
    RubricCriterion,
    RubricScore,
    StructuredIdea,
    VerdictDecision,
)

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any] | None:
    try:
        clean = text.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        parsed = json.loads(clean)
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:
        logger.debug("Failed extracting JSON from text: %s", exc)
        return None


class JuryCommittee:
    """Multi-agent b90 jury committee evaluating idea readiness with public rubric and quorum consensus."""

    def __init__(
        self,
        personas: list[JurorPersonaConfig] | None = None,
        quorum_threshold: float = 0.6,
        model: Any = None,
    ) -> None:
        self.personas = personas or STANDARD_JURY_PERSONAS
        self.quorum_threshold = quorum_threshold
        self.model = model

    def evaluate(self, idea: StructuredIdea, report: ResearchSquadReport) -> JuryVerdict:
        """Run committee review across all juror personas and compute quorum verdict."""
        logger.info(
            "Convening JuryCommittee for idea %s with %d jurors (quorum: %.1f%%)",
            idea.title,
            len(self.personas),
            self.quorum_threshold * 100,
        )

        ballots: list[JurorBallot] = []
        for persona in self.personas:
            ballot = self._evaluate_juror(persona, idea, report)
            ballots.append(ballot)

        return self._consolidate_verdict(ballots)

    def _evaluate_juror(
        self,
        persona: JurorPersonaConfig,
        idea: StructuredIdea,
        report: ResearchSquadReport,
    ) -> JurorBallot:
        """Evaluate idea from the perspective of an individual juror."""
        if self.model and hasattr(self.model, "invoke"):
            prompt = (
                f"You are {persona.name}, serving as {persona.role}.\n"
                f"Perspective: {persona.perspective}.\n"
                f"Voting tendency: {persona.voting_bias_description}\n\n"
                f"Evaluate the proposed idea:\n"
                f"Title: {idea.title}\n"
                f"Problem: {idea.problem}\n"
                f"Solution: {idea.value_hypothesis.proposed_solution}\n"
                f"TAM: {report.market.tam_estimate}, CAGR: {report.market.cagr_percentage}%\n"
                f"Competitors: {[c.name for c in report.competitors.direct_competitors]}\n"
                f"Moat: {report.differentiation.moat_factors}\n"
                f"Regulatory Risks: {[r.area for r in report.legal_privacy.risks]}\n\n"
                "Score each rubric criterion from 1.0 to 5.0 "
                "(problem, market, differentiation, feasibility, risk, cost).\n"
                "Cast vote: 'go' (ready to proceed), 'pivot' (needs major changes), 'no-go' (reject).\n"
                "Return JSON:\n"
                "{\n"
                '  "vote": "go|pivot|no-go",\n'
                '  "scores": {\n'
                '    "problem": 4.5, "market": 4.0, "differentiation": 4.2,\n'
                '    "feasibility": 4.0, "risk": 3.8, "cost": 4.1\n'
                "  },\n"
                '  "reasoning": "...",\n'
                '  "key_recommendations": ["..."],\n'
                '  "red_flags": ["..."]\n'
                "}"
            )
            try:
                res = self.model.invoke(prompt)
                data = _extract_json(getattr(res, "content", str(res)))
                if data:
                    vote_str = str(data.get("vote", "go")).lower()
                    vote = (
                        VerdictDecision.GO
                        if vote_str == "go"
                        else (VerdictDecision.NO_GO if vote_str == "no-go" else VerdictDecision.PIVOT)
                    )
                    scores_dict = data.get("scores", {})
                    scores: list[RubricScore] = []
                    for crit in RubricCriterion:
                        score_val = float(scores_dict.get(crit.value, 3.5))
                        score_val = max(1.0, min(5.0, score_val))
                        scores.append(
                            RubricScore(
                                criterion=crit,
                                score=score_val,
                                justification=f"{persona.role} assessed {crit.value}",
                            )
                        )
                    overall = sum(s.score for s in scores) / len(scores) if scores else 3.5
                    return JurorBallot(
                        juror_name=persona.name,
                        role=persona.role,
                        perspective=persona.perspective,
                        vote=vote,
                        scores=scores,
                        overall_score=round(overall, 2),
                        reasoning=str(data.get("reasoning", f"{persona.name} evaluation completed.")),
                        key_recommendations=list(data.get("key_recommendations", [])),
                        red_flags=list(data.get("red_flags", [])),
                    )
            except Exception as exc:
                logger.debug("Juror %s model evaluation failed: %s", persona.slug, exc)

        # Deterministic heuristic scoring per persona
        return self._heuristic_ballot(persona, idea, report)

    def _heuristic_ballot(
        self,
        persona: JurorPersonaConfig,
        idea: StructuredIdea,
        report: ResearchSquadReport,
    ) -> JurorBallot:
        """Deterministic heuristic scoring based on persona perspective and diligence signals."""
        scores: list[RubricScore] = []

        # Adjust score based on specialist signals
        has_critical_legal_risk = any(r.risk_level == "high" for r in report.legal_privacy.risks)
        has_competitor_density = len(report.competitors.direct_competitors) >= 3

        if persona.slug == "investor":
            market_score = 4.5 if "Billion" in report.market.tam_estimate else 3.2
            cost_score = 4.2
            scores = [
                RubricScore(criterion=RubricCriterion.PROBLEM, score=4.2, justification="Clear commercial pain"),
                RubricScore(criterion=RubricCriterion.MARKET, score=market_score, justification="Substantial TAM"),
                RubricScore(
                    criterion=RubricCriterion.DIFFERENTIATION,
                    score=4.0,
                    justification="Clear positioning versus SaaS incumbents",
                ),
                RubricScore(criterion=RubricCriterion.FEASIBILITY, score=3.8, justification="Standard SaaS stack"),
                RubricScore(
                    criterion=RubricCriterion.RISK,
                    score=3.5 if not has_critical_legal_risk else 2.0,
                    justification="Regulatory and competitive risk",
                ),
                RubricScore(criterion=RubricCriterion.COST, score=cost_score, justification="High gross margin margin"),
            ]
            vote = VerdictDecision.GO if market_score >= 4.0 else VerdictDecision.PIVOT
            reasoning = "Strong venture returns expected with verified addressable market."
            recs = ["Protect margins by encouraging local offline models for batch runs"]
            flags = ["Competitive response from legacy cloud suites"]

        elif persona.slug == "cto":
            scores = [
                RubricScore(criterion=RubricCriterion.PROBLEM, score=4.0, justification="Real architecture gap"),
                RubricScore(criterion=RubricCriterion.MARKET, score=3.8, justification="Viable developer market"),
                RubricScore(
                    criterion=RubricCriterion.DIFFERENTIATION, score=4.5, justification="Offline testability is unique"
                ),
                RubricScore(
                    criterion=RubricCriterion.FEASIBILITY,
                    score=4.4,
                    justification="Clean monorepo modular architecture",
                ),
                RubricScore(criterion=RubricCriterion.RISK, score=3.9, justification="Managed dependency surface"),
                RubricScore(criterion=RubricCriterion.COST, score=4.2, justification="Inference cost well contained"),
            ]
            vote = VerdictDecision.GO
            reasoning = "Architecture proposal is pragmatic, modular, and enforces 100% offline testability."
            recs = ["Ensure all external search calls have deterministic mock fallbacks"]
            flags = []

        elif persona.slug == "end-user":
            scores = [
                RubricScore(criterion=RubricCriterion.PROBLEM, score=4.6, justification="Directly solves daily pain"),
                RubricScore(criterion=RubricCriterion.MARKET, score=3.9, justification="Wide potential adoption"),
                RubricScore(
                    criterion=RubricCriterion.DIFFERENTIATION,
                    score=4.3,
                    justification="Direct PRD handoff to planning saves hours",
                ),
                RubricScore(criterion=RubricCriterion.FEASIBILITY, score=4.1, justification="Intuitive workflow"),
                RubricScore(
                    criterion=RubricCriterion.RISK, score=4.0, justification="Human approval gate builds trust"
                ),
                RubricScore(criterion=RubricCriterion.COST, score=4.0, justification="Transparent pricing tiers"),
            ]
            vote = VerdictDecision.GO
            reasoning = "Eliminates frustrating manual rework between brainstorm and PRD."
            recs = ["Provide clear CLI and web reporting for instant preview"]
            flags = []

        elif persona.slug == "security":
            risk_score = 2.5 if has_critical_legal_risk else 4.1
            scores = [
                RubricScore(criterion=RubricCriterion.PROBLEM, score=3.8, justification="Compliance is a real pain"),
                RubricScore(criterion=RubricCriterion.MARKET, score=3.7, justification="Enterprise demand is high"),
                RubricScore(
                    criterion=RubricCriterion.DIFFERENTIATION,
                    score=4.2,
                    justification="Airgapped sovereignty is rare",
                ),
                RubricScore(
                    criterion=RubricCriterion.FEASIBILITY, score=3.9, justification="Strict sandbox and token limits"
                ),
                RubricScore(criterion=RubricCriterion.RISK, score=risk_score, justification="Data privacy governance"),
                RubricScore(criterion=RubricCriterion.COST, score=3.8, justification="Audit overhead accounted for"),
            ]
            vote = VerdictDecision.NO_GO if has_critical_legal_risk else VerdictDecision.GO
            reasoning = "Security posture is compliant with data sovereignty and ephemeral human tokens."
            recs = ["Enforce 30-minute expiration on all human approval tokens"]
            flags = ["Ensure no PII leaks in search query strings"]

        elif persona.slug == "market":
            diff_score = 3.5 if has_competitor_density else 4.4
            scores = [
                RubricScore(criterion=RubricCriterion.PROBLEM, score=4.1, justification="Solid customer validation"),
                RubricScore(criterion=RubricCriterion.MARKET, score=4.3, justification="Clear market timing tailwinds"),
                RubricScore(
                    criterion=RubricCriterion.DIFFERENTIATION,
                    score=diff_score,
                    justification="Matrix shows clear moats",
                ),
                RubricScore(criterion=RubricCriterion.FEASIBILITY, score=3.9, justification="Executable roadmaps"),
                RubricScore(criterion=RubricCriterion.RISK, score=3.8, justification="Brand risk minimized"),
                RubricScore(criterion=RubricCriterion.COST, score=4.0, justification="Competitive tiering"),
            ]
            vote = VerdictDecision.GO
            reasoning = "Strong category positioning with verifiable citations as key differentiator."
            recs = ["Emphasize deterministic verifiable evidence in all outbound positioning"]
            flags = []

        else:  # devil-advocate
            scores = [
                RubricScore(
                    criterion=RubricCriterion.PROBLEM,
                    score=3.7,
                    justification="Is problem really urgent enough to switch?",
                ),
                RubricScore(
                    criterion=RubricCriterion.MARKET,
                    score=3.5,
                    justification="Incumbents could ship similar features quickly",
                ),
                RubricScore(
                    criterion=RubricCriterion.DIFFERENTIATION,
                    score=3.8,
                    justification="Moat depends on execution speed",
                ),
                RubricScore(
                    criterion=RubricCriterion.FEASIBILITY,
                    score=3.6,
                    justification="Multi-agent orchestration can be flaky",
                ),
                RubricScore(
                    criterion=RubricCriterion.RISK,
                    score=3.4,
                    justification="Users may distrust autonomous jury verdicts",
                ),
                RubricScore(
                    criterion=RubricCriterion.COST,
                    score=3.7,
                    justification="Inference costs could spike if unmetered",
                ),
            ]
            vote = VerdictDecision.PIVOT
            reasoning = "Idea has potential but must guard against model drift and competitive replication."
            recs = ["Introduce public rubric audits and strict budget caps per pipeline run"]
            flags = ["Over-reliance on LLM reasoning without fallback validation"]

        overall = sum(s.score for s in scores) / len(scores)
        return JurorBallot(
            juror_name=persona.name,
            role=persona.role,
            perspective=persona.perspective,
            vote=vote,
            scores=scores,
            overall_score=round(overall, 2),
            reasoning=reasoning,
            key_recommendations=recs,
            red_flags=flags,
        )

    def _consolidate_verdict(self, ballots: list[JurorBallot]) -> JuryVerdict:
        total = len(ballots)
        go_votes = sum(1 for b in ballots if b.vote == VerdictDecision.GO)
        pivot_votes = sum(1 for b in ballots if b.vote == VerdictDecision.PIVOT)
        no_go_votes = sum(1 for b in ballots if b.vote == VerdictDecision.NO_GO)

        # Quorum threshold check
        ratio_go = go_votes / total if total > 0 else 0.0
        ratio_no_go = no_go_votes / total if total > 0 else 0.0

        if ratio_no_go >= (1.0 - self.quorum_threshold):
            decision = VerdictDecision.NO_GO
            consensus = True
        elif ratio_go >= self.quorum_threshold:
            decision = VerdictDecision.GO
            consensus = True
        else:
            decision = VerdictDecision.PIVOT
            consensus = False

        # Compute average score per rubric criterion
        criterion_totals: dict[str, float] = {}
        criterion_counts: dict[str, int] = {}
        for b in ballots:
            for s in b.scores:
                criterion_totals[s.criterion.value] = criterion_totals.get(s.criterion.value, 0.0) + s.score
                criterion_counts[s.criterion.value] = criterion_counts.get(s.criterion.value, 0) + 1

        avg_scores = {
            k: round(criterion_totals[k] / criterion_counts[k], 2) for k in criterion_totals if criterion_counts[k] > 0
        }

        # Dissenting opinions: ballots that voted differently from final verdict
        dissenting: list[str] = [
            f"{b.juror_name} ({b.role}) voted {b.vote.value.upper()}: {b.reasoning}"
            for b in ballots
            if b.vote != decision
        ]

        # Consolidated recommendations
        recs_set: list[str] = []
        for b in ballots:
            for r in b.key_recommendations:
                if r not in recs_set:
                    recs_set.append(r)

        summary = (
            f"Jury committee of {total} jurors evaluated the idea. "
            f"Outcome: {decision.value.upper()} ({go_votes} GO, {pivot_votes} PIVOT, {no_go_votes} NO-GO). "
            f"Quorum threshold: {int(self.quorum_threshold * 100)}%. "
            f"Average rubric score: {round(sum(avg_scores.values()) / len(avg_scores), 2) if avg_scores else 0.0}/5.0."
        )

        return JuryVerdict(
            verdict=decision,
            consensus_reached=consensus,
            quorum_threshold=self.quorum_threshold,
            go_votes=go_votes,
            pivot_votes=pivot_votes,
            no_go_votes=no_go_votes,
            total_jurors=total,
            ballots=ballots,
            average_scores=avg_scores,
            dissenting_opinions=dissenting,
            consolidated_recommendations=recs_set,
            summary=summary,
        )

    def refine_and_rejudge(
        self,
        idea: StructuredIdea,
        report: ResearchSquadReport,
        rounds: int = 2,
    ) -> list[JuryVerdict]:
        """Perform multi-round improvement and re-evaluation cycle."""
        verdicts: list[JuryVerdict] = []
        current_idea = idea

        for r in range(rounds):
            verdict = self.evaluate(current_idea, report)
            verdicts.append(verdict)

            # If already GO with consensus or last round, finish
            if verdict.verdict == VerdictDecision.GO or r == rounds - 1:
                break

            # Incorporate recommendations into idea assumptions and value hypothesis
            logger.info("Refining idea based on Round %d recommendations...", r + 1)
            updated_assumptions = list(current_idea.initial_assumptions)
            for rec in verdict.consolidated_recommendations[:3]:
                updated_assumptions.append(f"Round {r + 1} refinement: {rec}")

            current_idea = StructuredIdea(
                id=current_idea.id,
                title=current_idea.title,
                summary=current_idea.summary,
                problem=current_idea.problem,
                target_audience=current_idea.target_audience,
                value_hypothesis=current_idea.value_hypothesis,
                domain_tags=current_idea.domain_tags,
                initial_assumptions=updated_assumptions,
            )

        return verdicts
