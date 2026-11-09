"""nexcoder-planning: agentic sprints and tasks in git.

Decomposes PRDs into structured backlogs, computes sprint capacity
and velocity, and idempotently syncs tasks with Git platform issue trackers.
"""

from nexcoder_planning.adapters import (
    AzureDevOpsAdapter,
    GitHubAdapter,
    GitLabAdapter,
    IssueSyncResult,
    PlatformAdapter,
    ProjectV2Info,
    ProjectV2Item,
    ProjectV2ItemResult,
    RemoteIssue,
    RemoteMilestone,
    SyncSummary,
)
from nexcoder_planning.capacity import (
    CapacityCalculator,
    CapacityReport,
    SprintCapacityConfig,
    SprintForecast,
    SprintPlanResult,
    SprintVelocityMetrics,
    TeamMember,
    VelocityRecord,
    VelocityTracker,
)
from nexcoder_planning.git_helpers import (
    GitResult,
    PRResult,
    build_conventional_commit,
    build_pull_request_body,
    create_branch,
    create_pull_request,
    execute_commit,
    strip_co_author_trailers,
    validate_no_emoji,
)
from nexcoder_planning.models import (
    AcceptanceCriterion,
    Epic,
    Plan,
    Story,
    Task,
)
from nexcoder_planning.prd import PRDConverter
from nexcoder_planning.sync import (
    BoardColumn,
    BoardSynchronizer,
    BoardSyncSummary,
    IssuePRBinding,
    ReplanResult,
    SlippageAlert,
)

__all__ = [
    "AcceptanceCriterion",
    "AzureDevOpsAdapter",
    "BoardColumn",
    "BoardSyncSummary",
    "BoardSynchronizer",
    "CapacityCalculator",
    "CapacityReport",
    "Epic",
    "GitHubAdapter",
    "GitLabAdapter",
    "GitResult",
    "IssuePRBinding",
    "IssueSyncResult",
    "PRResult",
    "Plan",
    "PlatformAdapter",
    "PRDConverter",
    "ProjectV2Info",
    "ProjectV2Item",
    "ProjectV2ItemResult",
    "RemoteIssue",
    "RemoteMilestone",
    "ReplanResult",
    "SlippageAlert",
    "SprintCapacityConfig",
    "SprintForecast",
    "SprintPlanResult",
    "SprintVelocityMetrics",
    "Story",
    "SyncSummary",
    "Task",
    "TeamMember",
    "VelocityRecord",
    "VelocityTracker",
    "build_conventional_commit",
    "build_pull_request_body",
    "create_branch",
    "create_pull_request",
    "execute_commit",
    "strip_co_author_trailers",
    "validate_no_emoji",
]

__version__ = "0.1.0"
