"""Agentic IaC delivery pipeline reusing nexcoder-agents blocks and governance gates."""

from __future__ import annotations

from typing import Any

from nexcoder_agents.engine.blocks.approval import HumanApprovalBlock
from nexcoder_agents.engine.blocks.guardrails import ExecutionLimits
from nexcoder_agents.engine.blocks.validator import ValidatorBlock
from nexcoder_agents.engine.graph import PipelineBuilder

from nexcoder_iac.credentials import scan_for_secrets
from nexcoder_iac.engine import IaCEngine
from nexcoder_iac.generators.parser import HighLevelSpecParser
from nexcoder_iac.models import IaCTarget, IaCTool


def create_iac_pipeline(
    name: str = "iac-delivery",
    approval_action: str = "apply_infrastructure",
    limits: ExecutionLimits | None = None,
    engine: IaCEngine | None = None,
) -> PipelineBuilder:
    """Build an end-to-end agentic infrastructure delivery pipeline with approval gate."""
    builder = PipelineBuilder(name)

    # 1. Validate inputs
    validator = ValidatorBlock(
        name="iac_input_validator",
        required_keys=["description"],
    )

    # 2. Human approval gate for production or destructive apply
    approval = HumanApprovalBlock(
        name="iac_approval_gate",
        action_name=approval_action,
        payload_keys=["description", "target", "estimated_cost_usd"],
    )

    builder.add_sequence([validator, approval])
    if limits:
        builder.set_limits(limits)

    return builder


def run_iac_workflow(
    description: str,
    target: IaCTarget = IaCTarget.LOCAL_COMPOSE,
    tool: IaCTool | None = None,
    engine: IaCEngine | None = None,
    actor: str = "nexcoder-agent",
    confirm_apply: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Execute the end-to-end IaC workflow: parse -> generate -> secret scan -> plan -> apply."""
    eng = engine or IaCEngine()

    # Step 1: Parse high-level description
    spec = HighLevelSpecParser.parse(description, target_override=target)

    # Step 2: Generate IaC artifacts
    artifacts = eng.generate(spec, target=target, tool=tool, actor=actor)

    # Step 3: Verify zero secrets in all generated files
    secret_findings: dict[str, list[str]] = {}
    for f in artifacts.files:
        findings = scan_for_secrets(f.content)
        if findings:
            secret_findings[f.filename] = findings

    if secret_findings:
        raise ValueError(f"Secret scanning detected violations in IaC artifacts: {secret_findings}")

    # Step 4: Plan preview
    preview = eng.plan(artifacts, actor=actor, dry_run=dry_run)

    # Step 5: Conditional Apply (only if confirmed)
    apply_result = None
    if confirm_apply:
        apply_result = eng.apply(preview, confirm=True, actor=actor, dry_run=dry_run)

    return {
        "spec": spec.model_dump(),
        "target": target.value,
        "tool": artifacts.tool.value,
        "files": [f.filename for f in artifacts.files],
        "estimated_monthly_cost_usd": artifacts.estimated_monthly_cost_usd,
        "plan_id": preview.plan_id,
        "plan_summary": preview.execution_summary,
        "applied": apply_result.success if apply_result else False,
        "apply_status": apply_result.status if apply_result else "pending_confirmation",
    }
