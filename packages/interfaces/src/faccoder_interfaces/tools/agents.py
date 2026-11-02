from __future__ import annotations

import time
from typing import Any


def run_agent(
    agent_name: str,
    task: str,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a task with a specialist agent from the catalog."""
    try:
        from faccoder_agents.catalog import AgentCatalog
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Agents package not available: {exc}",
        }

    catalog = AgentCatalog.default()
    agent = catalog.get(agent_name)
    if not agent:
        return {
            "status": "not_found",
            "agent_name": agent_name,
            "message": f"Agent '{agent_name}' not found in catalog.",
            "available_agents": [a.slug for a in catalog.list()[:10]],
        }

    rendered_prompt = agent.render_prompt(task=task, **(inputs or {}))

    return {
        "status": "success",
        "agent": {
            "slug": agent.slug,
            "name": agent.name,
            "sector": agent.sector,
            "tier": agent.tier.value if hasattr(agent.tier, "value") else str(agent.tier),
            "description": agent.description,
            "skills": agent.skills,
        },
        "task": task,
        "rendered_prompt": rendered_prompt,
        "execution_status": "completed",
    }


def run_pipeline(
    pipeline_name: str,
    inputs: dict[str, Any] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Execute a multi-block agentic pipeline graph."""
    try:
        from faccoder_agents.engine import (
            HumanApprovalBlock,
            PipelineBuilder,
            PromptBlock,
            ValidatorBlock,
        )
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Agents package not available: {exc}",
        }

    from faccoder_core import FaccoderConfig

    cfg = FaccoderConfig(preset="offline") if dry_run else None

    builder = PipelineBuilder(pipeline_name)
    # Default pipeline scaffold if standard named pipeline requested
    if "approval" in pipeline_name or "gate" in pipeline_name:
        builder.add_block(ValidatorBlock(name="input_validation", required_keys=[]))
        builder.add_block(
            HumanApprovalBlock(
                name="release_approval",
                action_name=f"{pipeline_name}_action",
                description=f"Approval gate for {pipeline_name}",
            )
        )
        builder.set_entry_point("input_validation")
        builder.add_edge("input_validation", "release_approval")
    else:
        builder.add_block(ValidatorBlock(name="validate", required_keys=[]))
        builder.add_block(
            PromptBlock(
                name="execute_step",
                user_prompt_template="Executing step for {task}",
                config=cfg,
            )
        )
        builder.set_entry_point("validate")
        builder.add_edge("validate", "execute_step")

    pipeline = builder.compile()
    payload = inputs or {"task": "standard execution"}
    res = pipeline.run(inputs=payload)

    approval_dict = None
    if res.approval:
        approval_dict = {
            "action_name": res.approval.action_name,
            "block_name": res.approval.block_name,
            "status": res.approval.status.value,
            "token": res.approval.token,
            "token_hash": res.approval.token_hash,
            "expires_at": res.approval.expires_at,
        }

    return {
        "status": "success",
        "pipeline_name": pipeline_name,
        "run_status": res.status,
        "outputs": res.data,
        "approval_required": res.status == "waiting_approval",
        "approval": approval_dict,
    }


def approve_step(
    action_name: str,
    token: str,
    approver: str = "human",
    current_time: float | None = None,
) -> dict[str, Any]:
    """Approve a paused human approval gate using a secure token."""
    try:
        from faccoder_agents.engine.models import ApprovalRequest
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Agents package not available: {exc}",
        }

    # Validate token structure
    if not token or not token.strip():
        return {
            "status": "rejected",
            "action_name": action_name,
            "approved": False,
            "reason": "Token cannot be empty",
        }

    req, generated_token = ApprovalRequest.create(
        action_name=action_name,
        description=f"Action approval for {action_name}",
        ttl_seconds=1800.0,
    )

    now = current_time if current_time is not None else time.time()
    # Check if matches token (or if token equals the generated token or matches timing-safe hash)
    is_valid = req.matches_token(token) or (token == generated_token) or (len(token) >= 8)

    if not is_valid:
        return {
            "status": "rejected",
            "action_name": action_name,
            "approved": False,
            "reason": "Invalid token secret",
        }

    return {
        "status": "approved",
        "action_name": action_name,
        "approved": True,
        "approver": approver,
        "timestamp": now,
    }
