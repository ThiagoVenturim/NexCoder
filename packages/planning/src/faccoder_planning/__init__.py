"""faccoder-planning: agentic sprints and tasks in git.

Decomposes PRDs into structured backlogs, computes sprint capacity
and velocity, and idempotently syncs tasks with Git platform issue trackers.
"""

from faccoder_planning.adapters import (
    AzureDevOpsAdapter,
    GitHubAdapter,
    GitLabAdapter,
    IssueSyncResult,
    PlatformAdapter,
    RemoteIssue,
    SyncSummary,
)
from faccoder_planning.capacity import (
    CapacityCalculator,
    CapacityReport,
    SprintCapacityConfig,
    SprintPlanResult,
    TeamMember,
    VelocityRecord,
)
from faccoder_planning.models import (
    AcceptanceCriterion,
    Epic,
    Plan,
    Story,
    Task,
)
from faccoder_planning.prd import PRDConverter

__all__ = [
    "AcceptanceCriterion",
    "AzureDevOpsAdapter",
    "CapacityCalculator",
    "CapacityReport",
    "Epic",
    "GitHubAdapter",
    "GitLabAdapter",
    "IssueSyncResult",
    "Plan",
    "PlatformAdapter",
    "PRDConverter",
    "RemoteIssue",
    "SprintCapacityConfig",
    "SprintPlanResult",
    "Story",
    "SyncSummary",
    "Task",
    "TeamMember",
    "VelocityRecord",
]

__version__ = "0.1.0"
