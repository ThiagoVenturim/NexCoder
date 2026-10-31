from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from faccoder_core.observability.usage import current_meter
from langgraph.graph import END, START, StateGraph

from faccoder_agents.engine.blocks.base import BaseBlock
from faccoder_agents.engine.blocks.condition import ConditionBlock
from faccoder_agents.engine.blocks.guardrails import ExecutionLimits
from faccoder_agents.engine.models import (
    ApprovalRequest,
    BlockStatus,
    PipelineRunResult,
)

__all__ = ["END", "START", "PipelineBuilder", "PipelineGraph"]


class PipelineGraph:
    """Compiled runnable LangGraph pipeline wrapping blocks, limits, and edges."""

    def __init__(
        self,
        name: str,
        compiled_graph: Any,
        blocks: dict[str, BaseBlock],
        limits: ExecutionLimits | None = None,
    ) -> None:
        self.name = name
        self.compiled_graph = compiled_graph
        self.blocks = blocks
        self.limits = limits

    def run(
        self,
        inputs: dict[str, Any] | None = None,
        dry_run: bool = False,
        context: dict[str, Any] | None = None,
        limits: ExecutionLimits | None = None,
    ) -> PipelineRunResult:
        """Execute the pipeline from entry to completion with guardrails."""
        inputs = inputs or {}
        context = context or {}
        effective_limits = limits or self.limits

        initial_state: dict[str, Any] = {
            "inputs": inputs,
            "data": inputs.copy(),
            "history": [],
            "errors": [],
            "status": "running",
            "current_block": None,
            "metadata": {
                "dry_run": dry_run,
                "started_at": time.time(),
                **context.get("metadata", {}),
            },
            "approval": inputs.get("approval"),
        }

        if effective_limits is not None:
            initial_state["_limits"] = effective_limits.model_dump()

        final_state = self.compiled_graph.invoke(initial_state)

        status = final_state.get("status", "completed")
        if status == "running":
            status = "completed"

        approval_obj = final_state.get("_last_approval_req")
        if approval_obj is None and final_state.get("approval"):
            try:
                approval_obj = ApprovalRequest.model_validate(final_state["approval"])
            except Exception:
                approval_obj = None

        return PipelineRunResult(
            pipeline_name=self.name,
            status=status,
            data=final_state.get("data", {}),
            history=final_state.get("history", []),
            errors=final_state.get("errors", []),
            approval=approval_obj,
        )


class PipelineBuilder:
    """Builder to construct LangGraph state graphs with reusable blocks and guardrails."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.blocks: dict[str, BaseBlock] = {}
        self.edges: list[tuple[str, str]] = []
        self.conditional_edges: list[tuple[str, Callable[[dict[str, Any]], str], dict[str, str]]] = []
        self.entry_point: str | None = None
        self.finish_points: set[str] = set()
        self.limits: ExecutionLimits | None = None

    def set_limits(self, limits: ExecutionLimits) -> PipelineBuilder:
        """Configure runtime execution limits for the pipeline."""
        self.limits = limits
        return self

    def add_block(self, block: BaseBlock) -> PipelineBuilder:
        """Register a block in the pipeline."""
        if block.name in self.blocks:
            raise ValueError(f"Block with name '{block.name}' already registered.")
        self.blocks[block.name] = block
        return self

    def set_entry_point(self, block_name: str) -> PipelineBuilder:
        """Designate the first block to execute."""
        if block_name not in self.blocks:
            raise KeyError(f"Entry block '{block_name}' not found.")
        self.entry_point = block_name
        return self

    def add_edge(self, source: str, target: str) -> PipelineBuilder:
        """Connect source block to target block (or END)."""
        if source not in self.blocks:
            raise KeyError(f"Source block '{source}' not found.")
        resolved_target = END if target in ("end", END, "__end__") else target
        if resolved_target != END and resolved_target not in self.blocks:
            raise KeyError(f"Target block '{target}' not found.")
        self.edges.append((source, resolved_target))
        return self

    def add_conditional_edge(
        self,
        source: str,
        path_fn: Callable[[dict[str, Any]], str],
        path_map: dict[str, str],
    ) -> PipelineBuilder:
        """Add dynamic conditional routing out of a block."""
        if source not in self.blocks:
            raise KeyError(f"Source block '{source}' not found.")
        self.conditional_edges.append((source, path_fn, path_map))
        return self

    def add_sequence(self, sequence: list[BaseBlock]) -> PipelineBuilder:
        """Register and link a linear sequence of blocks."""
        if not sequence:
            return self

        for block in sequence:
            if block.name not in self.blocks:
                self.add_block(block)

        if not self.entry_point:
            self.set_entry_point(sequence[0].name)

        for i in range(len(sequence) - 1):
            self.add_edge(sequence[i].name, sequence[i + 1].name)

        return self

    def _create_node_fn(self, block: BaseBlock) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def _node_fn(state: dict[str, Any]) -> dict[str, Any]:
            # Guard: If already failed or waiting approval, pass through unchanged
            curr_status = state.get("status", "running")
            if curr_status in ("failed", "waiting_approval", "rejected"):
                return state

            # Check execution limits if present
            limits_dict = state.get("_limits")
            if limits_dict:
                limits = ExecutionLimits.model_validate(limits_dict)
                history = state.get("history", [])
                metadata = state.get("metadata", {})
                data = state.get("data", {})

                # 1. Depth limit
                if len(history) >= limits.max_depth:
                    err = f"Guardrail limit exceeded: maximum depth of {limits.max_depth} reached."
                    return {
                        **state,
                        "status": "failed",
                        "errors": [*state.get("errors", []), err],
                    }

                # 2. Timeout limit
                started_at = metadata.get("started_at")
                if limits.timeout_seconds is not None and started_at is not None:
                    elapsed = time.time() - float(started_at)
                    if elapsed >= limits.timeout_seconds:
                        err = f"Guardrail limit exceeded: timeout of {limits.timeout_seconds:.1f}s reached."
                        return {
                            **state,
                            "status": "failed",
                            "errors": [*state.get("errors", []), err],
                        }

                # 3. Budget limit
                meter = current_meter()
                current_cost = meter.cost_usd if meter is not None else float(data.get("cost_usd", 0.0))
                if limits.max_budget_usd is not None and current_cost >= limits.max_budget_usd:
                    err = f"Guardrail limit exceeded: budget cap of ${limits.max_budget_usd:.4f} USD reached."
                    return {
                        **state,
                        "status": "failed",
                        "errors": [*state.get("errors", []), err],
                    }

            context = {"metadata": state.get("metadata", {})}
            result = block.execute(state, context=context)

            new_data = dict(state.get("data", {}))
            new_data.update(result.updates)

            new_history = list(state.get("history", []))
            new_history.append(
                {
                    "block": block.name,
                    "status": result.status.value,
                    "message": result.message,
                    "error": result.error,
                }
            )

            new_errors = list(state.get("errors", []))
            if result.error:
                new_errors.append(result.error)

            new_status = curr_status
            if result.status == BlockStatus.FAILURE:
                new_status = "failed"
            elif result.status == BlockStatus.WAITING_APPROVAL:
                new_status = "waiting_approval"
            elif result.status == BlockStatus.REJECTED:
                new_status = "rejected"

            new_approval = state.get("approval")
            last_approval_req = state.get("_last_approval_req")
            if result.approval_request:
                new_approval = result.approval_request.to_state_dict()
                last_approval_req = result.approval_request

            return {
                "inputs": state.get("inputs", {}),
                "data": new_data,
                "history": new_history,
                "errors": new_errors,
                "status": new_status,
                "current_block": block.name,
                "metadata": state.get("metadata", {}),
                "approval": new_approval,
                "_last_approval_req": last_approval_req,
                "_last_route": result.next_step,
                "_limits": state.get("_limits"),
            }

        return _node_fn

    def compile(self) -> PipelineGraph:
        """Compile configured blocks and transitions into a LangGraph StateGraph."""
        if not self.blocks:
            raise ValueError("Cannot compile pipeline with zero blocks.")

        entry = self.entry_point or next(iter(self.blocks.keys()))

        graph = StateGraph(dict)

        # 1. Add nodes for each block
        for name, block in self.blocks.items():
            graph.add_node(name, self._create_node_fn(block))

        # 2. Add entry edge
        graph.add_edge(START, entry)

        # 3. Add explicit edges
        for source, target in self.edges:
            graph.add_edge(source, target)

        # 4. Add conditional edges
        for source, path_fn, path_map in self.conditional_edges:
            graph.add_conditional_edges(source, path_fn, path_map)

        # 5. Handle ConditionBlocks that have branches but no explicit edges
        for name, block in self.blocks.items():
            if isinstance(block, ConditionBlock) and not any(src == name for src, _ in self.edges):
                if not any(src == name for src, _, _ in self.conditional_edges):
                    target_map = {route: (END if route == "end" else route) for route in block.branches.values()}
                    target_map[block.default_branch] = END if block.default_branch == "end" else block.default_branch

                    def make_router(b: ConditionBlock):
                        return lambda state: b.evaluate_route(state)

                    graph.add_conditional_edges(name, make_router(block), target_map)

        # 6. For blocks with no outbound edges, route to END
        all_sources = {src for src, _ in self.edges} | {src for src, _, _ in self.conditional_edges}
        for name in self.blocks.keys():
            if name not in all_sources:
                graph.add_edge(name, END)

        compiled_app = graph.compile()
        return PipelineGraph(
            name=self.name,
            compiled_graph=compiled_app,
            blocks=self.blocks,
            limits=self.limits,
        )
