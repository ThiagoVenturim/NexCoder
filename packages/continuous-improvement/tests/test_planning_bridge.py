"""Unit tests for planning bridge task generator."""

from nexcoder_continuous_improvement.issues.planning_bridge import (
    FindingCategory,
    ImprovementFinding,
    PlanningBridge,
)


def test_planning_bridge_formats_tasks() -> None:
    bridge = PlanningBridge()

    finding = ImprovementFinding(
        category=FindingCategory.SECURITY,
        title="Upgrade fastapi to patch GHSA-crit-9999",
        description="FastAPI 0.100.0 contains critical vulnerability, update to 0.110.0.",
        layer="security",
        recommended_agent="sec-fixer",
        estimate_points=2,
        priority="high",
        acceptance_given="FastAPI dependency is currently vulnerable",
        acceptance_when="Version is updated in pyproject.toml",
        acceptance_then="Security gate and unit tests pass offline",
    )

    payload = bridge.create_task_payload(finding)

    assert "[SECURITY] Upgrade fastapi" in payload["title"]
    assert "Given FastAPI dependency is currently vulnerable" in payload["acceptance_criteria"]
    assert "layer:security" in payload["labels"]
    assert payload["estimate"] == 2
