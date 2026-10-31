from __future__ import annotations

import pytest
from faccoder_agents.engine import (
    ApprovalStatus,
    ConditionBlock,
    HumanApprovalBlock,
    PipelineBuilder,
    PromptBlock,
    ValidatorBlock,
)
from faccoder_core.llm.fake import FakeChatModel


def test_linear_pipeline_dry_run() -> None:
    fake_llm = FakeChatModel(responses=["Generated PRD specification."])

    builder = PipelineBuilder("feature-flow")
    builder.add_block(ValidatorBlock(name="val", required_keys=["feature_request"]))
    builder.add_block(
        PromptBlock(
            name="generate_spec",
            user_prompt_template="Create spec for: {feature_request}",
            output_key="spec",
            model=fake_llm,
        )
    )
    builder.add_block(
        HumanApprovalBlock(
            name="approval_gate",
            action_name="publish_spec",
            description="Review specification before publication",
        )
    )

    builder.set_entry_point("val")
    builder.add_edge("val", "generate_spec")
    builder.add_edge("generate_spec", "approval_gate")

    pipeline = builder.compile()

    result = pipeline.run(inputs={"feature_request": "Audit log export"}, dry_run=True)

    assert result.status == "completed"
    assert result.data["spec"] == "Generated PRD specification."
    assert result.approval is not None
    assert result.approval.status == ApprovalStatus.DRY_RUN
    assert len(result.history) == 3


def test_pipeline_approval_gate_halt_and_resume() -> None:
    builder = PipelineBuilder("release-pipeline")
    builder.add_block(
        HumanApprovalBlock(
            name="deploy_gate",
            action_name="production_deploy",
            description="Approve production deployment",
        )
    )
    builder.set_entry_point("deploy_gate")
    pipeline = builder.compile()

    # Step 1: Run without approval token -> halts with waiting_approval
    res1 = pipeline.run(inputs={"build_id": "b-9912"})
    assert res1.status == "waiting_approval"
    assert res1.approval is not None
    assert res1.approval.status == ApprovalStatus.PENDING

    token = res1.approval.token
    saved_approval = res1.approval.model_dump()

    # Step 2: Resume providing the approval token
    res2 = pipeline.run(
        inputs={
            "build_id": "b-9912",
            "approval_token": token,
            "approval": saved_approval,
        }
    )
    assert res2.status == "completed"
    assert res2.approval is not None
    assert res2.approval.status == ApprovalStatus.APPROVED


def test_pipeline_branching_with_condition_block() -> None:
    builder = PipelineBuilder("routing-pipeline")
    builder.add_block(
        ConditionBlock(
            name="triage",
            field="severity",
            branches={"critical": "pager_duty", "minor": "slack_notify"},
            default_branch="slack_notify",
        )
    )
    builder.add_block(ValidatorBlock(name="pager_duty", required_keys=["incident_id"]))
    builder.add_block(ValidatorBlock(name="slack_notify", required_keys=["channel"]))

    builder.set_entry_point("triage")
    builder.add_edge("pager_duty", "end")
    builder.add_edge("slack_notify", "end")

    pipeline = builder.compile()

    # Test critical branch
    res_crit = pipeline.run(inputs={"severity": "critical", "incident_id": "INC-101"})
    assert res_crit.status == "completed"
    executed_blocks = [h["block"] for h in res_crit.history]
    assert executed_blocks == ["triage", "pager_duty"]

    # Test minor branch
    res_minor = pipeline.run(inputs={"severity": "minor", "channel": "#dev-alerts"})
    assert res_minor.status == "completed"
    executed_blocks_minor = [h["block"] for h in res_minor.history]
    assert executed_blocks_minor == ["triage", "slack_notify"]


def test_pipeline_add_sequence() -> None:
    builder = PipelineBuilder("sequence-pipeline")
    builder.add_sequence([
        ValidatorBlock(name="step1", required_keys=["k1"]),
        ValidatorBlock(name="step2", required_keys=["k2"]),
    ])
    pipeline = builder.compile()
    res = pipeline.run(inputs={"k1": "v1", "k2": "v2"})
    assert res.status == "completed"
    assert len(res.history) == 2


def test_pipeline_short_circuits_on_failure() -> None:
    builder = PipelineBuilder("failing-pipeline")
    builder.add_block(ValidatorBlock(name="val", required_keys=["mandatory"]))
    builder.add_block(ValidatorBlock(name="downstream", required_keys=["optional"]))
    builder.set_entry_point("val")
    builder.add_edge("val", "downstream")
    pipeline = builder.compile()

    res = pipeline.run(inputs={"optional": "present"})
    assert res.status == "failed"
    assert len(res.errors) >= 1
    # Downstream was passed through without executing its validation
    executed_blocks = [h["block"] for h in res.history]
    assert executed_blocks == ["val"]


def test_pipeline_builder_validation_errors() -> None:
    builder = PipelineBuilder("invalid-pipeline")
    builder.add_block(ValidatorBlock(name="b1"))
    with pytest.raises(ValueError, match="already registered"):
        builder.add_block(ValidatorBlock(name="b1"))

    with pytest.raises(KeyError, match="Entry block"):
        builder.set_entry_point("unknown")

    with pytest.raises(KeyError, match="Source block"):
        builder.add_edge("missing_source", "b1")

    with pytest.raises(KeyError, match="Target block"):
        builder.add_edge("b1", "missing_target")

    empty_builder = PipelineBuilder("empty")
    with pytest.raises(ValueError, match="zero blocks"):
        empty_builder.compile()

