from __future__ import annotations

import time

import pytest
from nexcoder_agents.engine import (
    Ballot,
    BlockStatus,
    CommitteeBlock,
    CommitteeMember,
    ExecutionLimits,
    GuardrailBlock,
    PipelineBuilder,
    ValidatorBlock,
)
from nexcoder_core.llm.fake import FakeChatModel


def test_committee_block_consensus_go() -> None:
    committee = CommitteeBlock(
        name="launch_jury",
        quorum_threshold=0.6,
    )
    clean_state = {"data": {"feature": "OAuth2 Login", "test_coverage": 95}}
    result = committee.execute(clean_state)

    assert result.status == BlockStatus.SUCCESS
    assert result.next_step == "go"
    verdict = result.updates["committee_verdict"]
    assert verdict["decision"] == "go"
    assert verdict["consensus_reached"] is True
    assert len(verdict["ballots"]) == 3


def test_committee_block_critical_risk_no_go() -> None:
    committee = CommitteeBlock(
        name="launch_jury",
        quorum_threshold=0.6,
    )
    flawed_state = {"data": {"feature": "Payments", "security_risk": "high"}}
    result = committee.execute(flawed_state)

    assert result.status == BlockStatus.SUCCESS
    assert result.next_step == "no-go"
    verdict = result.updates["committee_verdict"]
    assert verdict["decision"] == "no-go"
    assert verdict["consensus_reached"] is True


def test_committee_block_custom_evaluator_split_vote_pivot() -> None:
    members = [
        CommitteeMember(name="architect", perspective="architecture", weight=1.0),
        CommitteeMember(name="security", perspective="security", weight=1.0),
        CommitteeMember(name="finance", perspective="finance", weight=1.0),
    ]

    # architect says go, security says no-go, finance says pivot
    votes = {"architect": "go", "security": "no-go", "finance": "pivot"}

    def custom_eval(member: CommitteeMember, data: dict) -> Ballot:
        return Ballot(
            member_name=member.name,
            perspective=member.perspective,
            vote=votes[member.name],
            scores={"overall": 3.0},
            reason=f"{member.name} vote is {votes[member.name]}",
        )

    committee = CommitteeBlock(
        name="board_jury",
        members=members,
        quorum_threshold=0.6,
        evaluator_fn=custom_eval,
    )
    res = committee.execute({"data": {}})
    verdict = res.updates["committee_verdict"]

    # Since go is 33% and no-go is 33%, neither reaches 60% quorum -> pivot
    assert verdict["decision"] == "pivot"
    assert verdict["consensus_reached"] is False
    assert len(verdict["dissenting_opinions"]) >= 2


def test_committee_block_with_fake_model() -> None:
    fake_json = '{"vote": "go", "reason": "Model verified spec", "scores": {"feasibility": 5.0}}'
    model = FakeChatModel(responses=[fake_json, fake_json, fake_json])

    committee = CommitteeBlock(
        name="llm_jury",
        model=model,
    )
    res = committee.execute({"data": {"spec": "Clean code"}})
    verdict = res.updates["committee_verdict"]
    assert verdict["decision"] == "go"
    assert verdict["ballots"][0]["reason"] == "Model verified spec"


def test_guardrail_block_depth_violation() -> None:
    limits = ExecutionLimits(max_depth=3)
    guard = GuardrailBlock("guard", limits=limits)

    # 4 items in history -> exceeds depth 3
    fake_history = [{"block": f"b{i}"} for i in range(4)]
    state = {"history": fake_history, "data": {}, "metadata": {}}

    res = guard.execute(state)
    assert res.status == BlockStatus.FAILURE
    assert "maximum execution depth" in (res.error or "").lower()


def test_guardrail_block_tool_whitelist_violation() -> None:
    limits = ExecutionLimits(allowed_tools=["read_file", "code_search"])
    guard = GuardrailBlock("guard", limits=limits)

    state = {
        "history": [],
        "data": {"requested_tools": ["read_file", "execute_arbitrary_shell"]},
        "metadata": {},
    }
    res = guard.execute(state)
    assert res.status == BlockStatus.FAILURE
    assert "unauthorized tools requested" in (res.error or "").lower()


def test_guardrail_block_budget_violation() -> None:
    limits = ExecutionLimits(max_budget_usd=0.05)
    guard = GuardrailBlock("guard", limits=limits)

    state = {
        "history": [],
        "data": {"cost_usd": 0.12},
        "metadata": {},
    }
    res = guard.execute(state)
    assert res.status == BlockStatus.FAILURE
    assert "budget cap" in (res.error or "").lower()


def test_pipeline_engine_limits_depth_enforcement() -> None:
    # Build a pipeline with limits
    limits = ExecutionLimits(max_depth=2)
    builder = PipelineBuilder("limited-pipeline")
    builder.set_limits(limits)

    b1 = ValidatorBlock("step1", required_keys=["k"])
    b2 = ValidatorBlock("step2", required_keys=["k"])
    b3 = ValidatorBlock("step3", required_keys=["k"])

    builder.add_sequence([b1, b2, b3])
    pipeline = builder.compile()

    result = pipeline.run(inputs={"k": "v"})
    assert result.status == "failed"
    assert any("maximum depth" in err for err in result.errors)


def test_guardrail_block_timeout_violation() -> None:
    limits = ExecutionLimits(timeout_seconds=5.0)
    guard = GuardrailBlock("guard", limits=limits)

    # Simulating execution started 10 seconds ago
    state = {
        "history": [],
        "data": {},
        "metadata": {"started_at": time.time() - 10.0},
    }
    res = guard.execute(state)
    assert res.status == BlockStatus.FAILURE
    assert "timeout" in (res.error or "").lower()


def test_guardrail_block_raise_on_violation() -> None:
    limits = ExecutionLimits(max_depth=2)
    guard = GuardrailBlock("guard", limits=limits, raise_on_violation=True)

    fake_history = [{"block": "b0"}, {"block": "b1"}, {"block": "b2"}]
    state = {"history": fake_history, "data": {}, "metadata": {}}

    with pytest.raises(RuntimeError, match="maximum execution depth"):
        guard.execute(state)


def test_committee_block_target_key() -> None:
    committee = CommitteeBlock(name="sub_jury", target_key="deliverable")
    state = {
        "data": {
            "unrelated_flag": "critical_defect",
            "deliverable": {"feature": "Safe Module", "test_coverage": 100},
        }
    }
    res = committee.execute(state)
    assert res.status == BlockStatus.SUCCESS
    verdict = res.updates["committee_verdict"]
    assert verdict["decision"] == "go"


def test_committee_block_llm_json_decode_error_fallback() -> None:
    # Model returns invalid non-JSON string
    bad_model = FakeChatModel(responses=["This is not JSON"])
    committee = CommitteeBlock(name="fallback_jury", model=bad_model)

    res = committee.execute({"data": {"feature": "Docs"}})
    assert res.status == BlockStatus.SUCCESS
    verdict = res.updates["committee_verdict"]
    assert verdict["decision"] == "go"
