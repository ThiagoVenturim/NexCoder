"""nexcoder-testing: Multi-agent extreme application testing for owned/authorized targets."""

from __future__ import annotations

from nexcoder_control.approval import (
    TargetAuthorizationGate,
    TargetAuthorizationRecord,
    TargetNotAuthorizedError,
)

from nexcoder_testing.models import (
    AgentExecutionReport,
    AgentWorkSlice,
    APIEndpointSpec,
    DOMScreenSpec,
    ExtremeTestConfig,
    ExtremeTestReport,
    GeneratedTestArtifact,
    ScopeSummary,
    SystemFlowSpec,
    TestCaseExecution,
    TestScope,
)
from nexcoder_testing.orchestrator import ExtremeTestOrchestrator, TestWorkerAgent
from nexcoder_testing.pipeline import (
    ExtremeTestingBlock,
    create_extreme_testing_pipeline,
    register_extreme_testing_pipeline,
)
from nexcoder_testing.runners import (
    APIRequestRunner,
    ApplicationSecurityRunner,
    DOMScrapingRunner,
    SystemAndProcessRunner,
    UnitAndContractRunner,
)
from nexcoder_testing.synthetic import SyntheticTargetApp, create_synthetic_target_app

# Register the extreme-testing pipeline template in nexcoder-agents when imported
register_extreme_testing_pipeline()

__version__ = "0.1.0"

__all__ = [
    "APIEndpointSpec",
    "APIRequestRunner",
    "AgentExecutionReport",
    "AgentWorkSlice",
    "ApplicationSecurityRunner",
    "DOMScrapingRunner",
    "DOMScreenSpec",
    "ExtremeTestConfig",
    "ExtremeTestOrchestrator",
    "ExtremeTestReport",
    "ExtremeTestingBlock",
    "GeneratedTestArtifact",
    "ScopeSummary",
    "SyntheticTargetApp",
    "SystemAndProcessRunner",
    "SystemFlowSpec",
    "TargetAuthorizationGate",
    "TargetAuthorizationRecord",
    "TargetNotAuthorizedError",
    "TestCaseExecution",
    "TestScope",
    "TestWorkerAgent",
    "UnitAndContractRunner",
    "create_extreme_testing_pipeline",
    "create_synthetic_target_app",
    "register_extreme_testing_pipeline",
]
