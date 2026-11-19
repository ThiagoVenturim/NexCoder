"""Pluggable agent backends: run a whole task through an external agent CLI.

Model backends (``nexcoder_core.get_chat_model``) send one prompt to an API and get
tokens back. An ``AgentBackend`` sits next to them and hands a complete task to an
agent runtime (for example a coding agent CLI running in a container with the
user's own login) and receives a structured result.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentResultStatus = Literal["ok", "error", "timeout", "blocked"]


class AgentBackendError(RuntimeError):
    """Raised for backend misconfiguration (never for a failed task, see AgentResult.status)."""


class AgentTask(BaseModel):
    """One unit of work handed to an agent backend."""

    prompt: str = Field(min_length=1)
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    system_prompt: str | None = None
    timeout_s: float | None = Field(default=None, gt=0)
    actor: str = "anonymous"
    agent_id: str = "generic_agent"
    pipeline_id: str = "adhoc_pipeline"
    app_id: str = "default_app"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentUsage(BaseModel):
    """Token usage reported by the agent runtime, when it reports any."""

    input_tokens: int = 0
    output_tokens: int = 0


class AgentResult(BaseModel):
    """Structured outcome of a task. Failures are values, not exceptions."""

    task_id: str
    backend: str
    status: AgentResultStatus
    output: str = ""
    model: str = "unknown"
    usage: AgentUsage = Field(default_factory=AgentUsage)
    reported_cost_usd: float | None = None
    duration_s: float = 0.0
    error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class AgentBackend(ABC):
    """Interface every agent backend implements."""

    name: str = "abstract"

    @abstractmethod
    def run(self, task: AgentTask) -> AgentResult:
        """Execute ``task`` and return its structured result. Must not raise for task failures."""

    def dispatch(self, prompt: str, **task_fields: Any) -> AgentResult:
        """Convenience wrapper: build an ``AgentTask`` from a prompt and run it."""
        return self.run(AgentTask(prompt=prompt, **task_fields))


class OfflineAgentBackend(AgentBackend):
    """Deterministic backend with no network and no subprocess. The default."""

    name = "offline"

    def run(self, task: AgentTask) -> AgentResult:
        words = task.prompt.split()
        return AgentResult(
            task_id=task.task_id,
            backend=self.name,
            status="ok",
            output=f"[offline] received task with {len(words)} words",
            model="offline",
            usage=AgentUsage(input_tokens=len(words), output_tokens=0),
            reported_cost_usd=0.0,
        )
