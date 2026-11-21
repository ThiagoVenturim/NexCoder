"""Release and automated fix PR gating engine with jury and human approval controls."""

from __future__ import annotations

import hmac
from typing import Any

from pydantic import BaseModel, Field


class FixProposal(BaseModel):
    proposal_id: str
    finding_id: str
    title: str
    branch_name: str
    diff_summary: str
    risk_level: str = "medium"  # low, medium, high
    jury_verdict: str | None = None  # "GO", "NO_GO", "PIVOT"
    human_approval_token: str | None = None
    requires_human_approval: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class GateDecision(BaseModel):
    can_open_pr: bool
    reason: str
    requires_token: bool = False


class FixGate:
    """Enforces gating policies on automated fix PRs based on jury consensus and human approval."""

    def __init__(self, expected_approval_token: str | None = None) -> None:
        self.expected_approval_token = expected_approval_token

    def evaluate_proposal(self, proposal: FixProposal) -> GateDecision:
        """Evaluate if an automated fix PR can be opened."""
        # 1. Jury check
        if not proposal.jury_verdict:
            return GateDecision(
                can_open_pr=False,
                reason="Proposal has not been evaluated by jury committee.",
            )

        if proposal.jury_verdict.upper() != "GO":
            return GateDecision(
                can_open_pr=False,
                reason=f"Jury verdict was '{proposal.jury_verdict}'. Automated PR creation blocked.",
            )

        # 2. Risk check
        is_high_risk = proposal.risk_level.lower() in ("medium", "high") or proposal.requires_human_approval

        if is_high_risk:
            if not proposal.human_approval_token:
                return GateDecision(
                    can_open_pr=False,
                    reason="Human approval token required for medium/high risk automated fixes.",
                    requires_token=True,
                )

            if self.expected_approval_token:
                if not hmac.compare_digest(proposal.human_approval_token, self.expected_approval_token):
                    return GateDecision(
                        can_open_pr=False,
                        reason="Invalid human approval token provided.",
                        requires_token=True,
                    )
            elif len(proposal.human_approval_token.strip()) < 8:
                return GateDecision(
                    can_open_pr=False,
                    reason="Approval token format invalid.",
                    requires_token=True,
                )

        return GateDecision(
            can_open_pr=True,
            reason="All gates passed. Automated fix PR approved.",
            requires_token=False,
        )
