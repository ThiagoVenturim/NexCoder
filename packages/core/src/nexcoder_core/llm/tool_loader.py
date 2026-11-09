"""Selective loading for tools, MCP servers, and skills.

Avoids overwhelming the model context with dozens of unused tool schemas.
Tracks what tools each agent actually invoked across executions, loads only
those plus a minimal fixed core set, and lists the remainder by name in an
on-demand manifest so the agent can activate them if needed.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from pydantic import BaseModel, Field


class ToolUsageRecord(BaseModel):
    tool_name: str
    call_count: int = 1
    last_called_at: float = Field(default_factory=time.time)


class ToolUsageTracker:
    """Thread-safe usage tracker recording tool and MCP server invocations per agent."""

    def __init__(self) -> None:
        self._usage: dict[str, dict[str, ToolUsageRecord]] = {}
        self._lock = threading.Lock()

    def record_usage(self, agent_id: str, tool_name: str) -> None:
        norm_name = tool_name.strip()
        with self._lock:
            agent_map = self._usage.setdefault(agent_id, {})
            if norm_name in agent_map:
                record = agent_map[norm_name]
                record.call_count += 1
                record.last_called_at = time.time()
            else:
                agent_map[norm_name] = ToolUsageRecord(tool_name=norm_name)

    def get_used_tools(self, agent_id: str) -> set[str]:
        with self._lock:
            agent_map = self._usage.get(agent_id, {})
            return set(agent_map.keys())

    def reset(self, agent_id: str | None = None) -> None:
        with self._lock:
            if agent_id:
                self._usage.pop(agent_id, None)
            else:
                self._usage.clear()


class SelectiveLoadResult:
    """Container for active tools and the lightweight on-demand manifest."""

    def __init__(
        self,
        active_tools: list[Any],
        active_names: list[str],
        on_demand_names: list[str],
        manifest: str,
    ) -> None:
        self.active_tools = active_tools
        self.active_names = active_names
        self.on_demand_names = on_demand_names
        self.manifest = manifest


class SelectiveToolLoader:
    """Selectively loads only used tools plus a core set, keeping the rest on-demand."""

    def __init__(
        self,
        always_include: set[str] | None = None,
        tracker: ToolUsageTracker | None = None,
    ) -> None:
        self.always_include = set(always_include or {"read_file", "ask_user", "request_tool"})
        self.tracker = tracker or ToolUsageTracker()

    @staticmethod
    def _tool_name(tool: Any) -> str:
        for attr in ("name", "__name__"):
            val = getattr(tool, attr, None)
            if isinstance(val, str) and val:
                return val
        if isinstance(tool, dict) and "name" in tool:
            return str(tool["name"])
        return str(tool)

    @staticmethod
    def _tool_desc(tool: Any) -> str:
        for attr in ("description", "__doc__"):
            val = getattr(tool, attr, None)
            if isinstance(val, str) and val:
                return val.strip().split("\n")[0][:100]
        if isinstance(tool, dict) and "description" in tool:
            return str(tool["description"])[:100]
        return ""

    def load_tools(self, agent_id: str, available_tools: list[Any]) -> SelectiveLoadResult:
        """Filter tools into active ones and an on-demand catalog manifest."""
        used_names = self.tracker.get_used_tools(agent_id)
        active_names_set = self.always_include | used_names

        active_tools = []
        active_names = []
        on_demand_tools = []
        on_demand_names = []

        for tool in available_tools:
            name = self._tool_name(tool)
            if name in active_names_set:
                active_tools.append(tool)
                active_names.append(name)
            else:
                on_demand_tools.append(tool)
                on_demand_names.append(name)

        # Generate on-demand manifest
        if on_demand_names:
            lines = [
                "[ON-DEMAND TOOLS]",
                "The following tools are available on demand. Call request_tool(name) if needed:",
            ]
            for tool in on_demand_tools:
                name = self._tool_name(tool)
                desc = self._tool_desc(tool)
                lines.append(f"- {name}: {desc}" if desc else f"- {name}")
            manifest = "\n".join(lines)
        else:
            manifest = ""

        return SelectiveLoadResult(
            active_tools=active_tools,
            active_names=active_names,
            on_demand_names=on_demand_names,
            manifest=manifest,
        )

    def request_tool(self, agent_id: str, tool_name: str, available_tools: list[Any]) -> Any | None:
        """Activate an on-demand tool by name, recording usage so it persists."""
        norm = tool_name.strip()
        for tool in available_tools:
            if self._tool_name(tool) == norm:
                self.tracker.record_usage(agent_id, norm)
                return tool
        return None
