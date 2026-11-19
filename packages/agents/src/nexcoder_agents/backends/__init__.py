"""Pluggable agent backends (issue #115).

``OfflineAgentBackend`` is the default and never touches the network or a
subprocess. ``ContainerCLIBackend`` hands the task to an agent CLI running in a
container with the user's own login; ``CommandAgentBackend`` runs any local argv
that speaks the same wire protocol (used by tests with a fake CLI).
"""

from __future__ import annotations

import os
import shlex
from typing import Any

from nexcoder_agents.backends.base import (
    AgentBackend,
    AgentBackendError,
    AgentResult,
    AgentResultStatus,
    AgentTask,
    AgentUsage,
    OfflineAgentBackend,
)
from nexcoder_agents.backends.command import (
    CommandAgentBackend,
    ContainerBackendConfig,
    ContainerCLIBackend,
)
from nexcoder_agents.backends.protocol import (
    REQUEST_PROTOCOL,
    RESULT_PROTOCOL,
    ProtocolError,
    encode_request,
    parse_result,
)

BACKEND_ENV = "NEXCODER_AGENT_BACKEND"
COMMAND_ENV = "NEXCODER_AGENT_COMMAND"
BACKEND_NAMES = ("offline", "container", "command")


def build_agent_backend(
    name: str | None = None,
    *,
    container_config: ContainerBackendConfig | None = None,
    command: list[str] | str | None = None,
    **kwargs: Any,
) -> AgentBackend:
    """Build a backend by name. Falls back to ``$NEXCODER_AGENT_BACKEND`` and then to ``offline``.

    ``kwargs`` (timeout_s, audit_log, cost_tracker, firewall, runner) are passed to
    the subprocess based backends.
    """
    chosen = (name or os.environ.get(BACKEND_ENV) or "offline").strip().lower()
    if chosen == "offline":
        return OfflineAgentBackend()
    if chosen == "container":
        return ContainerCLIBackend(container_config, **kwargs)
    if chosen == "command":
        argv = command if command is not None else os.environ.get(COMMAND_ENV, "")
        if isinstance(argv, str):
            argv = shlex.split(argv)
        if not argv:
            raise AgentBackendError(f"the command backend needs an argv (pass command= or set {COMMAND_ENV})")
        return CommandAgentBackend(argv, **kwargs)
    raise AgentBackendError(f"unknown agent backend {chosen!r}; choose one of {', '.join(BACKEND_NAMES)}")


__all__ = [
    "BACKEND_ENV",
    "BACKEND_NAMES",
    "COMMAND_ENV",
    "REQUEST_PROTOCOL",
    "RESULT_PROTOCOL",
    "AgentBackend",
    "AgentBackendError",
    "AgentResult",
    "AgentResultStatus",
    "AgentTask",
    "AgentUsage",
    "CommandAgentBackend",
    "ContainerBackendConfig",
    "ContainerCLIBackend",
    "OfflineAgentBackend",
    "ProtocolError",
    "build_agent_backend",
    "encode_request",
    "parse_result",
]
