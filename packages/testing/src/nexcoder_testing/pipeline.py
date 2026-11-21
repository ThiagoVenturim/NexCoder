"""LangGraph pipeline block and ready-made pipeline template reusing nexcoder-agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nexcoder_agents.engine import (
    BaseBlock,
    BlockResult,
    BlockStatus,
    CommitteeBlock,
    CommitteeMember,
    ExecutionLimits,
    HumanApprovalBlock,
    PipelineBuilder,
    PromptBlock,
    ValidatorBlock,
)
from nexcoder_agents.engine.pipelines import (
    PipelineTemplate,
    list_pipeline_templates,
    register_pipeline_template,
)
from nexcoder_control.approval import TargetAuthorizationGate, TargetNotAuthorizedError

from nexcoder_testing.models import ExtremeTestConfig, TestScope
from nexcoder_testing.orchestrator import ExtremeTestOrchestrator


class ExtremeTestingBlock(BaseBlock):
    """LangGraph pipeline block that runs the multi-agent ExtremeTestOrchestrator."""

    def __init__(
        self,
        name: str = "extreme_testing_execution",
        orchestrator: ExtremeTestOrchestrator | None = None,
        target_gate: TargetAuthorizationGate | None = None,
    ) -> None:
        super().__init__(name=name)
        self.orchestrator = orchestrator or ExtremeTestOrchestrator(target_gate=target_gate)

    def execute(
        self,
        state: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> BlockResult:
        data = state.get("data", {})
        inputs = state.get("inputs", {})

        target_raw = data.get("target_path") or inputs.get("target_path")
        if not target_raw:
            return BlockResult(
                block_name=self.name,
                status=BlockStatus.FAILURE,
                error="Missing required input 'target_path' for ExtremeTestingBlock.",
            )

        num_agents = int(data.get("num_agents") or inputs.get("num_agents") or 3)
        owned_target = bool(data.get("owned_target") or inputs.get("owned_target") or False)
        authorized_by = str(data.get("authorized_by") or inputs.get("authorized_by") or "owner")
        approval_token = data.get("approval_token") or inputs.get("approval_token")
        raw_scopes = data.get("scopes") or inputs.get("scopes")
        scopes = [TestScope(s) for s in raw_scopes] if raw_scopes else TestScope.all_scopes()
        requester = data.get("requester") or inputs.get("requester")

        cfg = ExtremeTestConfig(
            target_path=Path(str(target_raw)),
            base_url=data.get("base_url") or inputs.get("base_url"),
            num_agents=num_agents,
            scopes=scopes,
            offline=bool(data.get("offline", inputs.get("offline", True))),
            owned_target=owned_target,
            authorized_by=authorized_by,
            approval_token=approval_token,
            endpoints=data.get("endpoints") or inputs.get("endpoints") or [],
            screens=data.get("screens") or inputs.get("screens") or [],
            system_flows=data.get("system_flows") or inputs.get("system_flows") or [],
        )

        try:
            report = self.orchestrator.run(cfg, requester=requester)
        except TargetNotAuthorizedError as exc:
            return BlockResult(
                block_name=self.name,
                status=BlockStatus.FAILURE,
                error=str(exc),
                message="Target authorization gate refused execution.",
            )

        return BlockResult(
            block_name=self.name,
            status=BlockStatus.SUCCESS,
            updates={
                "extreme_test_report": report.model_dump(mode="json"),
                "extreme_test_markdown": report.to_markdown(),
                "total_tests": report.total_tests,
                "total_findings": len(report.findings),
                "gate_passed": report.security_gate_verdict.passed if report.security_gate_verdict else True,
            },
            message=report.executive_summary,
        )


def create_extreme_testing_pipeline(
    name: str = "extreme-testing",
    approval_action: str = "signoff_extreme_test_report",
    limits: ExecutionLimits | None = None,
    model: Any = None,
    orchestrator: ExtremeTestOrchestrator | None = None,
) -> PipelineBuilder:
    """Build a LangGraph multi-agent extreme application testing pipeline."""
    builder = PipelineBuilder(name)

    val = ValidatorBlock(
        name="target_validator",
        required_keys=["target_path"],
    )

    test_block = ExtremeTestingBlock(
        name="extreme_testing_execution",
        orchestrator=orchestrator,
    )

    triage = PromptBlock(
        name="findings_remediation_synthesis",
        user_prompt_template=(
            "You are a principal QA and application security architect.\n"
            "Target: {target_path}\n"
            "Total Tests: {total_tests}\n"
            "Total Findings: {total_findings}\n"
            "Report:\n{extreme_test_markdown}\n"
            "Synthesize prioritized remediation guidance for the application owner."
        ),
        output_key="remediation_synthesis",
        tier="medium",
        model=model,
    )

    committee = CommitteeBlock(
        name="qa_security_committee",
        members=[
            CommitteeMember(name="qa_lead", perspective="Unit, API, DOM, and E2E Coverage", weight=1.5),
            CommitteeMember(name="appsec_lead", perspective="Defensive Application Security Posture", weight=1.5),
        ],
        target_key="remediation_synthesis",
        quorum_threshold=0.6,
        model=model,
    )

    gate = HumanApprovalBlock(
        name="extreme_testing_gate",
        action_name=approval_action,
        description="Sign off extreme testing report and remediation backlog",
        payload_keys=["target_path", "total_tests", "total_findings", "remediation_synthesis"],
    )

    builder.add_sequence([val, test_block, triage, committee, gate])
    if limits:
        builder.set_limits(limits)
    return builder


def register_extreme_testing_pipeline() -> PipelineTemplate:
    """Register the 'extreme-testing' template in nexcoder-agents pipeline registry."""
    template = PipelineTemplate(
        name="extreme-testing",
        description=(
            "Multi-agent extreme application testing (unit, system/process, DOM scraping, "
            "API contracts, and defensive security) for owned targets."
        ),
        category="qa",
        required_inputs=["target_path"],
        factory=create_extreme_testing_pipeline,
    )
    # The registry fills its built-in templates lazily only while it is empty; load them first so
    # registering this template on import does not hide the built-in ones.
    list_pipeline_templates()
    register_pipeline_template(template)
    return template
