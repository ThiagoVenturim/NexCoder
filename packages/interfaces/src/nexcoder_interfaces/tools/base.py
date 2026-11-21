from __future__ import annotations

from typing import Any


def unavailable_tool_handler(module_name: str, tool_name: str) -> dict[str, Any]:
    """Uniform response for tools whose underlying module is not yet available in develop."""
    return {
        "status": "unavailable",
        "module": module_name,
        "tool": tool_name,
        "message": (
            f"Module '{module_name}' is not yet available in this release. "
            f"The tool '{tool_name}' will be activated when '{module_name}' is merged into develop."
        ),
    }
