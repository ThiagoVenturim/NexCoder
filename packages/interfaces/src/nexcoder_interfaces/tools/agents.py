from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PausedPipelineExecution:
    execution_id: str
    pipeline_name: str
    pipeline: Any
    initial_inputs: dict[str, Any]
    approval_request: Any  # ApprovalRequest
    created_at: float = field(default_factory=time.time)


class ExecutionRegistry:
    """Thread-safe registry holding paused pipeline executions awaiting approval."""

    def __init__(self) -> None:
        self._executions: dict[str, PausedPipelineExecution] = {}
        self._action_to_execution_id: dict[str, str] = {}
        self._lock = threading.Lock()

    def register(self, execution_id: str, execution: PausedPipelineExecution) -> None:
        with self._lock:
            self._executions[execution_id] = execution
            self._action_to_execution_id[execution.approval_request.action_name] = execution_id

    def get(self, execution_id: str) -> PausedPipelineExecution | None:
        with self._lock:
            return self._executions.get(execution_id)

    def find_by_action(self, action_name: str) -> PausedPipelineExecution | None:
        with self._lock:
            eid = self._action_to_execution_id.get(action_name)
            return self._executions.get(eid) if eid else None

    def remove(self, execution_id: str) -> None:
        with self._lock:
            item = self._executions.pop(execution_id, None)
            if item:
                self._action_to_execution_id.pop(item.approval_request.action_name, None)

    def clear(self) -> None:
        with self._lock:
            self._executions.clear()
            self._action_to_execution_id.clear()


GLOBAL_EXECUTION_REGISTRY = ExecutionRegistry()


def run_agent(
    agent_name: str,
    task: str,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a task with a specialist agent from the catalog."""
    try:
        from nexcoder_agents.catalog import AgentCatalog
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
    execution_id: str | None = None,
) -> dict[str, Any]:
    """Execute a multi-block agentic pipeline graph."""
    try:
        from nexcoder_agents.engine import (
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

    from nexcoder_core import NexcoderConfig

    cfg = NexcoderConfig(preset="offline") if dry_run else None

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

    exec_id = execution_id or f"exec_{uuid.uuid4().hex[:12]}"

    approval_dict = None
    if res.approval:
        approval_dict = {
            "execution_id": exec_id,
            "action_name": res.approval.action_name,
            "block_name": res.approval.block_name,
            "status": res.approval.status.value,
            "token": res.approval.token,
            "token_hash": res.approval.token_hash,
            "expires_at": res.approval.expires_at,
        }
        if res.status == "waiting_approval":
            paused_item = PausedPipelineExecution(
                execution_id=exec_id,
                pipeline_name=pipeline_name,
                pipeline=pipeline,
                initial_inputs=payload,
                approval_request=res.approval,
            )
            GLOBAL_EXECUTION_REGISTRY.register(exec_id, paused_item)

    return {
        "status": "success",
        "execution_id": exec_id,
        "pipeline_name": pipeline_name,
        "run_status": res.status,
        "outputs": res.data,
        "approval_required": res.status == "waiting_approval",
        "approval": approval_dict,
    }


def approve_step(
    action_name: str,
    token: str,
    execution_id: str | None = None,
    approver: str = "human",
    current_time: float | None = None,
) -> dict[str, Any]:
    """Approve a paused human approval gate using a secure token."""
    try:
        from nexcoder_agents.engine.models import ApprovalStatus
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Agents package not available: {exc}",
        }

    now = current_time if current_time is not None else time.time()

    if not token or not str(token).strip():
        return {
            "status": "rejected",
            "action_name": action_name,
            "execution_id": execution_id,
            "approved": False,
            "reason": "Token cannot be empty",
        }

    clean_token = str(token).strip()

    # 1. Lookup the paused execution by execution_id or action_name
    paused: PausedPipelineExecution | None = None
    if execution_id:
        paused = GLOBAL_EXECUTION_REGISTRY.get(execution_id)
        if paused and paused.approval_request.action_name != action_name:
            return {
                "status": "rejected",
                "action_name": action_name,
                "execution_id": execution_id,
                "approved": False,
                "reason": (
                    f"Action mismatch: execution '{execution_id}' is for action "
                    f"'{paused.approval_request.action_name}', not '{action_name}'."
                ),
            }
    else:
        paused = GLOBAL_EXECUTION_REGISTRY.find_by_action(action_name)

    # Sem solicitacao pendente: rejeita
    if not paused:
        return {
            "status": "rejected",
            "action_name": action_name,
            "execution_id": execution_id,
            "approved": False,
            "reason": f"No pending approval request found for action '{action_name}'.",
        }

    req = paused.approval_request

    # 2. Check if already consumed / single-use check
    if req.consumed or req.status == ApprovalStatus.APPROVED:
        return {
            "status": "rejected",
            "action_name": action_name,
            "execution_id": paused.execution_id,
            "approved": False,
            "reason": f"Approval token for '{action_name}' has already been consumed.",
        }

    # 3. Check expiration
    if req.is_expired(current_time=now):
        req.status = ApprovalStatus.EXPIRED
        return {
            "status": "rejected",
            "action_name": action_name,
            "execution_id": paused.execution_id,
            "approved": False,
            "reason": f"Approval token for '{action_name}' has expired.",
        }

    # 4. Validate with matches_token (constant-time, timing-safe)
    # Strictly reject random tokens or tokens from other requests
    if not req.matches_token(clean_token):
        return {
            "status": "rejected",
            "action_name": action_name,
            "execution_id": paused.execution_id,
            "approved": False,
            "reason": "Invalid approval token: secret token mismatch.",
        }

    # 5. Resume paused pipeline execution
    block_name = req.block_name or "release_approval"
    resume_inputs = dict(paused.initial_inputs)
    resume_inputs[f"approval_token_{block_name}"] = clean_token
    resume_inputs[f"approval_{block_name}"] = req.to_state_dict()

    resumed_result = None
    if paused.pipeline:
        try:
            resumed_result = paused.pipeline.run(inputs=resume_inputs)
        except Exception as exc:
            logger.error("Error resuming pipeline '%s': %s", paused.pipeline_name, exc)

    # 6. Mark consumed and remove from registry
    req.status = ApprovalStatus.APPROVED
    req.consumed = True
    GLOBAL_EXECUTION_REGISTRY.remove(paused.execution_id)

    return {
        "status": "approved",
        "action_name": action_name,
        "execution_id": paused.execution_id,
        "approved": True,
        "approver": approver,
        "timestamp": now,
        "pipeline_status": resumed_result.status if resumed_result else "completed",
        "outputs": resumed_result.data if resumed_result else {},
    }
