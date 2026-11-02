from __future__ import annotations

import abc
from typing import Any

from pydantic import BaseModel, Field


class AgentFinding(BaseModel):
    title: str
    description: str
    severity: str
    category: str = "security"
    recommendation: str = ""


class AgentAnalysisResult(BaseModel):
    agent_name: str
    summary: str
    findings: list[AgentFinding] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseSecurityAgent(abc.ABC):
    """Abstract base class for security specialist agents."""

    def __init__(self, name: str, role: str) -> None:
        self.name = name
        self.role = role

    @abc.abstractmethod
    def analyze(self, target: Any, offline: bool = True) -> Any:
        """Run analysis on target (code, finding, architecture description)."""
        ...
