"""Automated continuous improvement module for nexcoder: detect, issue, develop, verify, merge, and audit."""

from nexcoder_continuous_improvement.auto_improve.agent_bridge import NexLinkDevAgentBridge
from nexcoder_continuous_improvement.auto_improve.issues import (
    AutoIssueManager,
    GitHubCliIssueAdapter,
    InMemoryIssueAdapter,
    IssuePlatformAdapter,
)
from nexcoder_continuous_improvement.auto_improve.loop import AutoImproveLoop
from nexcoder_continuous_improvement.auto_improve.merger import AutoMergeEngine
from nexcoder_continuous_improvement.auto_improve.models import (
    AgentExecutionResult,
    AutoImproveCycleReport,
    AutoIssue,
    DailyLimitExceededError,
    MergeDecision,
    SafetyViolationError,
    VerificationFailedError,
    VerificationResult,
)
from nexcoder_continuous_improvement.auto_improve.quota import DailyQuotaTracker
from nexcoder_continuous_improvement.auto_improve.reporter import AutoImproveReporter
from nexcoder_continuous_improvement.auto_improve.scanner import RepoScanner

__all__ = [
    "AgentExecutionResult",
    "AutoImproveCycleReport",
    "AutoImproveLoop",
    "AutoImproveReporter",
    "AutoIssue",
    "AutoIssueManager",
    "AutoMergeEngine",
    "DailyLimitExceededError",
    "DailyQuotaTracker",
    "GitHubCliIssueAdapter",
    "InMemoryIssueAdapter",
    "IssuePlatformAdapter",
    "MergeDecision",
    "NexLinkDevAgentBridge",
    "RepoScanner",
    "SafetyViolationError",
    "VerificationFailedError",
    "VerificationResult",
]
