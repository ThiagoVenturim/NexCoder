from __future__ import annotations

import time

from faccoder_agents.engine.blocks import (
    ConditionBlock,
    HumanApprovalBlock,
    PromptBlock,
    ValidatorBlock,
)
from faccoder_agents.engine.models import ApprovalStatus, BlockStatus
from faccoder_core.llm.fake import FakeChatModel
from pydantic import BaseModel


class ProjectInput(BaseModel):
    title: str
    budget: int


def test_validator_block_required_keys() -> None:
    validator = ValidatorBlock("val", required_keys=["title", "budget"])

    # Success case
    ok_state = {"data": {"title": "Auth Service", "budget": 5000}}
    res_ok = validator.execute(ok_state)
    assert res_ok.status == BlockStatus.SUCCESS

    # Missing key case
    bad_state = {"data": {"title": "Auth Service"}}
    res_bad = validator.execute(bad_state)
    assert res_bad.status == BlockStatus.FAILURE
    assert "budget" in (res_bad.error or "")


def test_validator_block_schema_validation() -> None:
    validator = ValidatorBlock("val_schema", schema=ProjectInput)

    ok_state = {"data": {"title": "Billing", "budget": 1000}}
    assert validator.execute(ok_state).status == BlockStatus.SUCCESS

    bad_state = {"data": {"title": "Billing", "budget": "not-an-int"}}
    res_bad = validator.execute(bad_state)
    assert res_bad.status == BlockStatus.FAILURE
    assert "validation error" in (res_bad.error or "").lower()


def test_validator_block_custom_predicate() -> None:
    def check_positive_budget(data: dict) -> tuple[bool, str | None]:
        if data.get("budget", 0) <= 0:
            return False, "Budget must be greater than zero."
        return True, None

    validator = ValidatorBlock("val_pred", custom_validator=check_positive_budget)
    assert validator.execute({"data": {"budget": 10}}).status == BlockStatus.SUCCESS
    res_fail = validator.execute({"data": {"budget": -5}})
    assert res_fail.status == BlockStatus.FAILURE
    assert "greater than zero" in (res_fail.error or "")


def test_condition_block_field_routing() -> None:
    condition = ConditionBlock(
        name="decision_gate",
        field="decision",
        branches={"go": "build_task", "pivot": "refine_idea", "no-go": "archive"},
        default_branch="archive",
    )

    res_go = condition.execute({"data": {"decision": "go"}})
    assert res_go.status == BlockStatus.SUCCESS
    assert res_go.next_step == "build_task"

    res_pivot = condition.execute({"data": {"decision": "pivot"}})
    assert res_pivot.next_step == "refine_idea"

    res_default = condition.execute({"data": {"decision": "unknown"}})
    assert res_default.next_step == "archive"


def test_condition_block_predicate_routing() -> None:
    condition = ConditionBlock(
        name="score_gate",
        predicate=lambda d: "fast_track" if d.get("score", 0) > 80 else "standard_track",
    )
    assert condition.execute({"data": {"score": 95}}).next_step == "fast_track"
    assert condition.execute({"data": {"score": 50}}).next_step == "standard_track"


def test_prompt_block_execution_with_fake_model() -> None:
    fake_llm = FakeChatModel(responses=["Architecture reviewed: approved."])
    block = PromptBlock(
        name="review_step",
        system_prompt="You are an architect.",
        user_prompt_template="Review service: {service_name}",
        output_key="review_notes",
        model=fake_llm,
    )

    state = {"data": {"service_name": "EventGateway"}}
    res = block.execute(state)
    assert res.status == BlockStatus.SUCCESS
    assert res.updates["review_notes"] == "Architecture reviewed: approved."


def test_prompt_block_structured_output() -> None:
    class Verdict(BaseModel):
        passed: bool
        score: int

    json_reply = '{"passed": true, "score": 92}'
    fake_llm = FakeChatModel(responses=[json_reply])

    block = PromptBlock(
        name="structured_eval",
        user_prompt_template="Evaluate {topic}",
        output_key="eval_result",
        schema=Verdict,
        model=fake_llm,
    )

    state = {"data": {"topic": "Security posture"}}
    res = block.execute(state)
    assert res.status == BlockStatus.SUCCESS
    verdict = res.updates["eval_result"]
    assert isinstance(verdict, Verdict)
    assert verdict.passed is True
    assert verdict.score == 92


def test_human_approval_block_dry_run() -> None:
    approval = HumanApprovalBlock(
        name="gate",
        action_name="deploy_service",
        description="Approve deployment to cluster",
    )
    state = {
        "metadata": {"dry_run": True},
        "data": {"service": "AuthService", "version": "v1.2.0"},
    }

    res = approval.execute(state)
    assert res.status == BlockStatus.DRY_RUN
    assert res.approval_request is not None
    assert res.approval_request.status == ApprovalStatus.DRY_RUN
    assert "_dry_run_preview" in res.updates


def test_human_approval_block_pending_and_approval_flow() -> None:
    approval = HumanApprovalBlock(
        name="gate",
        action_name="release_payment",
        description="Approve wire transfer",
    )

    # 1. First run: no token provided -> waiting approval
    state = {"data": {"amount": 50000}}
    res_pending = approval.execute(state)
    assert res_pending.status == BlockStatus.WAITING_APPROVAL
    assert res_pending.approval_request is not None
    assert res_pending.approval_request.status == ApprovalStatus.PENDING

    token = res_pending.approval_request.token
    req_dict = res_pending.approval_request.model_dump()

    # 2. Second run: invalid token
    state_invalid = {
        "data": {"amount": 50000},
        "inputs": {"approval_token": "wrong-token-123"},
        "approval": req_dict,
    }
    res_invalid = approval.execute(state_invalid)
    assert res_invalid.status == BlockStatus.FAILURE

    # 3. Third run: valid token -> approved!
    state_valid = {
        "data": {"amount": 50000},
        "inputs": {"approval_token": token},
        "approval": req_dict,
    }
    res_ok = approval.execute(state_valid)
    assert res_ok.status == BlockStatus.SUCCESS
    assert res_ok.approval_request is not None
    assert res_ok.approval_request.status == ApprovalStatus.APPROVED


def test_human_approval_block_expired_token() -> None:
    approval = HumanApprovalBlock(
        name="gate",
        action_name="drop_table",
        ttl_seconds=1.0,
    )
    state = {"data": {"table": "temp_logs"}}
    res_pending = approval.execute(state)
    token = res_pending.approval_request.token
    req_dict = res_pending.approval_request.model_dump()

    # Artificially expire the token
    req_dict["expires_at"] = time.time() - 10.0

    state_expired = {
        "data": {"table": "temp_logs"},
        "inputs": {"approval_token": token},
        "approval": req_dict,
    }
    res_expired = approval.execute(state_expired)
    assert res_expired.status == BlockStatus.REJECTED
    assert "expired" in (res_expired.error or "").lower()
