"""Unit tests for automated fix gating policies."""

from faccoder_continuous_improvement.pipeline.fix_gate import FixGate, FixProposal


def test_fix_gate_blocks_no_go_jury() -> None:
    gate = FixGate()
    proposal = FixProposal(
        proposal_id="prop-1",
        finding_id="find-1",
        title="Automated refactor",
        branch_name="fix/refactor",
        diff_summary="Modifies core routing",
        jury_verdict="NO_GO",
    )

    decision = gate.evaluate_proposal(proposal)
    assert decision.can_open_pr is False
    assert "Jury verdict was 'NO_GO'" in decision.reason


def test_fix_gate_requires_human_token() -> None:
    gate = FixGate(expected_approval_token="human_secret_approval_123")

    proposal_no_token = FixProposal(
        proposal_id="prop-2",
        finding_id="find-2",
        title="Upgrade security dependency",
        branch_name="fix/security",
        diff_summary="Update requests",
        risk_level="high",
        jury_verdict="GO",
    )
    decision = gate.evaluate_proposal(proposal_no_token)
    assert decision.can_open_pr is False
    assert decision.requires_token is True

    # With invalid token
    proposal_bad_token = proposal_no_token.model_copy(update={"human_approval_token": "wrong_token_here"})
    decision_bad = gate.evaluate_proposal(proposal_bad_token)
    assert decision_bad.can_open_pr is False
    assert "Invalid human approval token" in decision_bad.reason

    # With valid token
    proposal_good = proposal_no_token.model_copy(update={"human_approval_token": "human_secret_approval_123"})
    decision_good = gate.evaluate_proposal(proposal_good)
    assert decision_good.can_open_pr is True
    assert "All gates passed" in decision_good.reason
