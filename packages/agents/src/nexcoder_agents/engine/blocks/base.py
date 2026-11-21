from __future__ import annotations

import abc
from typing import Any

from nexcoder_agents.engine.models import BlockResult


class BaseBlock(abc.ABC):
    """Abstract contract for all pipeline blocks."""

    def __init__(self, name: str, block_type: str = "generic") -> None:
        self.name = name
        self.block_type = block_type

    @abc.abstractmethod
    def execute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        """Execute block logic synchronously."""
        raise NotImplementedError

    async def aexecute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        """Execute block logic asynchronously."""
        return self.execute(state, context)
