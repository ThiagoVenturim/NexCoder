from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from faccoder_agents.engine.blocks.base import BaseBlock
from faccoder_agents.engine.models import BlockResult, BlockStatus

logger = logging.getLogger(__name__)


class CommitteeMember(BaseModel):
    """Juror participating in a multi-agent committee evaluation."""

    name: str
    perspective: str
    weight: float = 1.0
    rubric_criteria: list[str] = Field(default_factory=lambda: ["feasibility", "risk", "maintainability"])


class Ballot(BaseModel):
    """Individual juror vote, rubric scores, and justification."""

    member_name: str
    perspective: str
    vote: str  # "go", "pivot", "no-go"
    scores: dict[str, float] = Field(default_factory=dict)
    reason: str = ""


class CommitteeVerdict(BaseModel):
    """Consolidated outcome of the committee review with quorum consensus."""

    decision: str  # "go", "pivot", "no-go"
    consensus_reached: bool
    quorum_threshold: float
    total_jurors: int
    go_weight: float
    no_go_weight: float
    pivot_weight: float
    ballots: list[Ballot] = Field(default_factory=list)
    average_scores: dict[str, float] = Field(default_factory=dict)
    dissenting_opinions: list[str] = Field(default_factory=list)
    summary: str = ""


class CommitteeBlock(BaseBlock):
    """Multi-agent evaluation committee with rubric voting and quorum consensus (b90)."""

    def __init__(
        self,
        name: str,
        members: list[CommitteeMember] | None = None,
        quorum_threshold: float = 0.6,
        evaluator_fn: Callable[[CommitteeMember, dict[str, Any]], Ballot] | None = None,
        model: Any = None,
        target_key: str | None = None,
        output_key: str = "committee_verdict",
    ) -> None:
        super().__init__(name=name, block_type="committee")
        self.members = members or [
            CommitteeMember(name="architect", perspective="System Architecture and Non-Functional Requirements"),
            CommitteeMember(name="security", perspective="Vulnerability, Attack Surface, and Compliance Risk"),
            CommitteeMember(name="product", perspective="User Value, Feasibility, and Operational Cost"),
        ]
        self.quorum_threshold = quorum_threshold
        self.evaluator_fn = evaluator_fn
        self.model = model
        self.target_key = target_key
        self.output_key = output_key

    def _default_evaluate_member(self, member: CommitteeMember, data: dict[str, Any]) -> Ballot:
        """Heuristic or model-based single juror evaluation."""
        if self.model is not None and hasattr(self.model, "invoke"):
            # If an LLM or FakeChatModel is provided
            prompt = (
                f"You are the {member.name} ({member.perspective}).\n"
                f"Evaluate the following deliverable:\n{json.dumps(data, default=str)}\n"
                "Return a JSON object with: {'vote': 'go'|'pivot'|'no-go', 'reason': '...', "
                "'scores': {'feasibility': 4.0, ...}}"
            )
            try:
                res = self.model.invoke(prompt)
                content = getattr(res, "content", str(res))
                parsed = json.loads(content)
                vote = str(parsed.get("vote", "go")).lower()
                if vote not in ("go", "pivot", "no-go"):
                    vote = "pivot"
                return Ballot(
                    member_name=member.name,
                    perspective=member.perspective,
                    vote=vote,
                    scores={k: float(v) for k, v in parsed.get("scores", {}).items()},
                    reason=str(parsed.get("reason", "")),
                )
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.debug("Failed parsing LLM committee vote: %s", exc)

        # Deterministic heuristic fallback based on error indicators in data
        payload_dict = data if isinstance(data, dict) else {"content": str(data)}
        has_critical_error = bool(payload_dict.get("critical_defect") or payload_dict.get("security_risk") == "high")
        has_warnings = bool(payload_dict.get("warnings") or payload_dict.get("pending_items"))

        if has_critical_error:
            vote = "no-go"
            reason = f"{member.name} rejected: critical risk detected."
            scores = {c: 1.5 for c in member.rubric_criteria}
        elif has_warnings:
            vote = "pivot"
            reason = f"{member.name} requested adjustments on flagged warnings."
            scores = {c: 3.0 for c in member.rubric_criteria}
        else:
            vote = "go"
            reason = f"{member.name} approved: all rubric criteria satisfied."
            scores = {c: 4.5 for c in member.rubric_criteria}

        return Ballot(
            member_name=member.name,
            perspective=member.perspective,
            vote=vote,
            scores=scores,
            reason=reason,
        )

    def execute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        data = state.get("data", {})
        target = data.get(self.target_key, {}) if self.target_key else data

        ballots: list[Ballot] = []
        total_weight = sum(m.weight for m in self.members) or 1.0
        go_weight = 0.0
        no_go_weight = 0.0
        pivot_weight = 0.0

        all_scores: dict[str, list[float]] = {}

        for member in self.members:
            if self.evaluator_fn is not None:
                ballot = self.evaluator_fn(member, target)
            else:
                ballot = self._default_evaluate_member(member, target)

            ballots.append(ballot)

            if ballot.vote == "go":
                go_weight += member.weight
            elif ballot.vote == "no-go":
                no_go_weight += member.weight
            else:
                pivot_weight += member.weight

            for crit, val in ballot.scores.items():
                all_scores.setdefault(crit, []).append(val)

        go_ratio = go_weight / total_weight
        no_go_ratio = no_go_weight / total_weight

        consensus = False
        if go_ratio >= self.quorum_threshold:
            decision = "go"
            consensus = True
        elif no_go_ratio >= self.quorum_threshold:
            decision = "no-go"
            consensus = True
        else:
            decision = "pivot"
            consensus = False

        avg_scores = {k: sum(v) / len(v) for k, v in all_scores.items() if v}
        dissenting = [b.reason for b in ballots if b.vote != decision]

        summary = (
            f"Committee verdict: {decision.upper()} (Go: {go_ratio:.1%}, "
            f"No-Go: {no_go_ratio:.1%}, Quorum threshold: {self.quorum_threshold:.1%})"
        )

        verdict = CommitteeVerdict(
            decision=decision,
            consensus_reached=consensus,
            quorum_threshold=self.quorum_threshold,
            total_jurors=len(self.members),
            go_weight=go_weight,
            no_go_weight=no_go_weight,
            pivot_weight=pivot_weight,
            ballots=ballots,
            average_scores=avg_scores,
            dissenting_opinions=dissenting,
            summary=summary,
        )

        return BlockResult(
            block_name=self.name,
            status=BlockStatus.SUCCESS,
            next_step=decision,
            updates={self.output_key: verdict.model_dump(), "_last_route": decision},
            message=summary,
        )
