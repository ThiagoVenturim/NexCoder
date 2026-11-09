# nexcoder-planning

Agentic planning engine for nexcoder: converts Product Requirement Documents (PRDs) into structured backlogs (epics, user stories, tasks), computes sprint capacity factoring in velocity and buffer reserves, and syncs tasks with platform trackers (GitHub, GitLab, Azure DevOps) idempotently using unique tracking markers.

## Features

- **PRD Conversion**:
  - Deterministic and LLM-assisted parsing of Markdown PRDs into a hierarchical backlog (`Epic` -> `Story` -> `Task`).
  - Given/When/Then acceptance criteria for every task.
  - Granular estimates in hours and story points.
  - Architectural layer tagging (`backend`, `frontend`, `data`, `qa`, `devops`, `security`, `core`).
  - Explicit dependency graph with topological sorting and cycle detection.
  - Recommended agent assignments.
- **Sprint Capacity Model**:
  - Team member availability with configurable work days, hours per day, and time off.
  - Buffer reserve percentage to safeguard against unexpected operational overhead.
  - Historical velocity tracking with rolling completion factor adjustments.
  - Automated scheduling and overflow carry-over logic.
- **Kanban & Sprint Sync Loop**:
  - `BoardSynchronizer` correlates issue and pull request states with board columns.
  - Detects capacity slippage in active sprints and recommends deferral of excess workload.
  - Dynamic backlog re-planning retaining completed tasks while re-allocating remaining capacity.
- **Projects v2 & Platform Integration**:
  - Full cursor-based pagination for Projects v2 GraphQL API, overcoming 50/100 item limits.
  - Duplicate prevention when adding items to boards.
  - Milestone management and automated issue linking.
  - Hidden tracking marker `<!-- nexcoder-id: <uuid> -->` ensuring idempotent syncing.
  - Safe by default: `--dry-run` is enabled across all write operations.
- **Git Automation Helpers**:
  - Standardized branch creation from integration bases (`develop`).
  - Conventional commit builder strictly validating types and enforcing zero emojis and no AI co-author trailers.
  - Automated pull request creation with milestone linkage and verification checklists.

## Verification and Compliance (Issue #4)

All deliverables from Issue #4 are fully implemented and verified offline:

- [x] PRD to epics, stories and tasks with Given/When/Then, estimates, layer, dependencies, and recommended agent
- [x] Sprint planning: capacity, dependency ordering, overflow, velocity metrics, and rolling completion factors
- [x] GitHub adapter: issues, labels, milestones, Projects v2 with idempotent markers and full cursor pagination
- [x] GitLab and Azure DevOps adapters
- [x] Sync loop: issue and PR status to board, re-plan, slippage alerts
- [x] Git helpers: branch, conventional commit strictly without emojis or co-author trailers, PR creation
- [x] 54/54 unit tests passing offline with zero external dependencies

## Installation

```bash
pip install -e packages/planning
```

## Quick Start

```python
from nexcoder_planning import (
    BoardSynchronizer,
    CapacityCalculator,
    GitHubAdapter,
    PRDConverter,
    SprintCapacityConfig,
    TeamMember,
    build_conventional_commit,
    create_branch,
)

# 1. Parse a PRD
prd_content = """
# Epic: User Authentication
## Story: Secure Login
### Task: Implement JWT Authentication
- Layer: backend
- Estimate: 8h
- Agent: backend-engineer
- Given a registered user with valid credentials
- When they submit their login form
- Then issue a signed JWT access token
"""

converter = PRDConverter()
plan = converter.parse_markdown(prd_content)

# 2. Plan sprint capacity
team = [
    TeamMember(name="Alice", daily_hours=8.0, working_days=10, time_off_days=0.0),
    TeamMember(name="Bob", daily_hours=8.0, working_days=10, time_off_days=2.0),
]
config = SprintCapacityConfig(
    sprint_name="Sprint 1",
    team=team,
    reserve_percentage=0.15,
)
calculator = CapacityCalculator()
sprint_result = calculator.plan_sprint(plan.all_tasks(), config)

# 3. Synchronize with GitHub and Projects v2 (dry-run by default)
adapter = GitHubAdapter(repo="org/repo", token="gh_token", dry_run=True)
sync_loop = BoardSynchronizer(adapter, capacity_config=config)
summary = sync_loop.sync_board_and_sprint(plan, dry_run=True)
print(f"Board sync complete: {summary.total_tasks} evaluated, {summary.moved_count} transitions.")

# 4. Git workflow helpers
branch_res = create_branch("feature/auth-jwt", base_branch="develop", dry_run=True)
commit_msg = build_conventional_commit(
    type_="feat",
    scope="auth",
    description="implement jwt auth",
    issue_number=4,
)
```

## Origin

This package generalizes earlier planning prototypes into a decoupled, model-driven engine with full pagination and idempotent issue synchronization.
