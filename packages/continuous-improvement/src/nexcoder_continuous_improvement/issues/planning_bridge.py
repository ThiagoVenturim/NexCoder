"""Planning bridge: converts continuous improvement findings into actionable backlog tasks."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class FindingCategory(StrEnum):
    RESEARCH = "research"
    OBSERVABILITY = "observability"
    SECURITY = "security"
    DEPENDENCY = "dependency"


class ImprovementFinding(BaseModel):
    category: FindingCategory
    title: str
    description: str
    layer: str = "core"  # e.g. core, security, ideation, planning
    recommended_agent: str = "sec-fixer"
    estimate_points: int = 3
    priority: str = "high"
    acceptance_given: str = "A finding has been detected by continuous monitoring"
    acceptance_when: str = "The responsible agent applies the fix or implementation"
    acceptance_then: str = "All tests pass offline and the issue is resolved"
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanningBridge:
    """Bridges improvement findings to formatted tasks compatible with nexcoder-planning."""

    def create_task_payload(self, finding: ImprovementFinding) -> dict[str, Any]:
        """Format an improvement finding as a standardized task definition."""
        return {
            "title": f"[{finding.category.upper()}] {finding.title}",
            "description": finding.description,
            "layer": finding.layer,
            "recommended_agent": finding.recommended_agent,
            "estimate": finding.estimate_points,
            "priority": finding.priority,
            "acceptance_criteria": (
                f"Given {finding.acceptance_given}\n"
                f"When {finding.acceptance_when}\n"
                f"Then {finding.acceptance_then}"
            ),
            "labels": [f"type:{finding.category.value}", f"layer:{finding.layer}", f"priority:{finding.priority}"],
        }

    def batch_convert(self, findings: list[ImprovementFinding]) -> list[dict[str, Any]]:
        """Convert a batch of findings into planning task payloads."""
        return [self.create_task_payload(f) for f in findings]
