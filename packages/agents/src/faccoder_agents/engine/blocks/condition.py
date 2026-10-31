from __future__ import annotations

from collections.abc import Callable
from typing import Any

from faccoder_agents.engine.blocks.base import BaseBlock
from faccoder_agents.engine.models import BlockResult, BlockStatus


class ConditionBlock(BaseBlock):
    """Evaluates branching conditions to dynamically route pipeline execution."""

    def __init__(
        self,
        name: str,
        field: str | None = None,
        branches: dict[Any, str] | None = None,
        predicate: Callable[[dict[str, Any]], str] | None = None,
        default_branch: str = "end",
    ) -> None:
        super().__init__(name=name, block_type="condition")
        self.field = field
        self.branches = branches or {}
        self.predicate = predicate
        self.default_branch = default_branch

    def evaluate_route(self, state: dict[str, Any]) -> str:
        """Determine next target block based on state and condition configuration."""
        data = state.get("data", {})

        if self.predicate is not None:
            return self.predicate(data)

        if self.field is not None:
            val = data.get(self.field)
            if val in self.branches:
                return self.branches[val]

        return self.default_branch

    def execute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        route = self.evaluate_route(state)
        return BlockResult(
            block_name=self.name,
            status=BlockStatus.SUCCESS,
            next_step=route,
            updates={"_last_route": route},
            message=f"Condition routed to: {route}",
        )
