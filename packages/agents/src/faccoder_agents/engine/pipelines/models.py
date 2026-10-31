from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from faccoder_agents.engine.blocks.guardrails import ExecutionLimits
from faccoder_agents.engine.graph import PipelineBuilder, PipelineGraph


class PipelineTemplate(BaseModel):
    """Metadata and factory definition for a ready-made pipeline template."""

    name: str
    description: str
    category: str
    required_inputs: list[str] = Field(default_factory=list)
    factory: Callable[..., PipelineBuilder]
    default_limits: ExecutionLimits | None = None

    def build(self, **kwargs: Any) -> PipelineGraph:
        """Instantiate the pipeline builder and compile into an executable graph."""
        builder = self.factory(**kwargs)
        if self.default_limits and not builder.limits:
            builder.set_limits(self.default_limits)
        return builder.compile()
