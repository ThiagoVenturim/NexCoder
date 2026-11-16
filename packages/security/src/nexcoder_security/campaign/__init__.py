"""Security and quality testing campaign control plane package."""

from __future__ import annotations

from typing import Any

from nexcoder_security.campaign.agents import (
    ApiTestAgent,
    BaseTestAgent,
    DomTestAgent,
    ProcessTestAgent,
    SecurityTestAgent,
    SystemTestAgent,
    UnitTestAgent,
    build_test_agent,
)
from nexcoder_security.campaign.engine import SecurityTestCampaignEngine
from nexcoder_security.campaign.models import (
    AgentExecutionResult,
    CampaignBudget,
    CampaignConfig,
    CampaignReport,
    CampaignStatus,
    TestFinding,
    TestType,
)
from nexcoder_security.campaign.registry import CampaignRegistry, get_global_registry


def run_security_test_campaign(
    target: str,
    *,
    test_types: list[str] | list[TestType] | None = None,
    agent_count: int = 3,
    allowed_scope: list[str] | None = None,
    max_cost_usd: float = 5.0,
    max_duration_seconds: float = 120.0,
    owned_target: bool = False,
    authorized_by: str = "",
    authorization_document: Any | None = None,
    require_signed_document: bool = False,
    engine: SecurityTestCampaignEngine | None = None,
    dry_run: bool = True,
) -> CampaignReport:
    """Convenience helper to initialize and run a security test campaign."""
    parsed_types: list[TestType] = []
    if test_types:
        for t in test_types:
            parsed_types.append(t if isinstance(t, TestType) else TestType.from_str(t))
    else:
        parsed_types = [TestType.UNIT, TestType.API, TestType.SECURITY]

    budget = CampaignBudget(
        max_cost_usd=max_cost_usd,
        max_duration_seconds=max_duration_seconds,
    )
    config = CampaignConfig(
        target=target,
        test_types=parsed_types,
        agent_count=agent_count,
        allowed_scope=allowed_scope or ["*"],
        budget=budget,
        owned_target=owned_target,
        authorized_by=authorized_by,
        authorization_document=authorization_document,
        require_signed_document=require_signed_document,
        dry_run=dry_run,
    )

    runner = engine or SecurityTestCampaignEngine()
    return runner.run_campaign(config)


__all__ = [
    "AgentExecutionResult",
    "ApiTestAgent",
    "BaseTestAgent",
    "CampaignBudget",
    "CampaignConfig",
    "CampaignRegistry",
    "CampaignReport",
    "CampaignStatus",
    "DomTestAgent",
    "ProcessTestAgent",
    "SecurityTestAgent",
    "SecurityTestCampaignEngine",
    "SystemTestAgent",
    "TestFinding",
    "TestType",
    "UnitTestAgent",
    "build_test_agent",
    "get_global_registry",
    "run_security_test_campaign",
]
