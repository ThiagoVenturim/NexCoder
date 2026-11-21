from __future__ import annotations

from typing import Any


def research_idea(
    idea: str,
    dry_run: bool = True,
    domain_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Research an idea using the specialist research squad."""
    try:
        from nexcoder_ideation.intake import IdeaAnalyst
        from nexcoder_ideation.models import RawIdea
        from nexcoder_ideation.research.squad import ResearchSquad
        from nexcoder_ideation.search.providers import MockSearchProvider, get_search_provider
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Ideation package not available: {exc}",
        }

    raw = RawIdea(raw_text=idea)
    analyst = IdeaAnalyst()
    structured = analyst.analyze(raw)
    if domain_tags:
        structured.domain_tags = list(set(structured.domain_tags + domain_tags))

    search_provider = MockSearchProvider() if dry_run else get_search_provider()
    squad = ResearchSquad(search_provider=search_provider)
    report = squad.run(structured)

    return {
        "status": "success",
        "idea_id": report.idea_id,
        "title": structured.title,
        "summary": structured.summary,
        "problem": structured.problem,
        "domain_tags": structured.domain_tags,
        "market": report.market.model_dump(),
        "competitors": report.competitors.model_dump(),
        "differentiation": report.differentiation.model_dump(),
        "gaps": report.gaps.model_dump(),
        "pricing": report.pricing.model_dump(),
        "legal_privacy": report.legal_privacy.model_dump(),
    }


def judge_idea(
    idea: str,
    report_data: dict[str, Any] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Evaluate an idea through the jury committee."""
    try:
        from nexcoder_ideation.intake import IdeaAnalyst
        from nexcoder_ideation.jury.committee import JuryCommittee
        from nexcoder_ideation.models import RawIdea, ResearchSquadReport
        from nexcoder_ideation.research.squad import ResearchSquad
        from nexcoder_ideation.search.providers import MockSearchProvider, get_search_provider
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Ideation package not available: {exc}",
        }

    raw = RawIdea(raw_text=idea)
    analyst = IdeaAnalyst()
    structured = analyst.analyze(raw)

    if report_data:
        report = ResearchSquadReport.model_validate(report_data)
    else:
        search_provider = MockSearchProvider() if dry_run else get_search_provider()
        report = ResearchSquad(search_provider=search_provider).run(structured)

    committee = JuryCommittee(quorum_threshold=0.6)
    verdict = committee.evaluate(structured, report)

    return {
        "status": "success",
        "verdict": verdict.verdict.value,
        "go_votes": verdict.go_votes,
        "pivot_votes": verdict.pivot_votes,
        "no_go_votes": verdict.no_go_votes,
        "total_jurors": verdict.total_jurors,
        "consensus_reached": verdict.consensus_reached,
        "average_scores": verdict.average_scores,
        "ballots": [b.model_dump() for b in verdict.ballots],
        "dissenting_opinions": verdict.dissenting_opinions,
    }
