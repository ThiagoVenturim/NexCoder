# faccoder-planning

Agentic planning engine for faccoder: converts Product Requirement Documents (PRDs) into structured backlogs (epics, user stories, tasks), computes sprint capacity factoring in velocity and buffer reserves, and syncs tasks with platform trackers (GitHub, GitLab, Azure DevOps) idempotently using unique tracking markers.

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
- **Idempotent Platform Adapters**:
  - GitHub, GitLab, and Azure DevOps integration.
  - Embedded hidden tracking marker `<!-- faccoder-id: <uuid> -->` in task issue bodies.
  - Duplicate detection preventing repeated ticket creation on re-runs.
  - Full pagination support without item count limits.
  - Safe by default: `--dry-run` is enabled by default to prevent unintended remote modifications.

## Installation

```bash
pip install -e packages/planning
```

## Quick Start

```python
from faccoder_planning import (
    PRDConverter,
    CapacityCalculator,
    SprintCapacityConfig,
    TeamMember,
    GitHubAdapter,
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

# 3. Sync to GitHub with dry-run protection
adapter = GitHubAdapter(repo="org/repo", token="gh_token", dry_run=True)
summary = adapter.sync_plan(plan)
print(f"Sync complete (dry-run): {summary.created} to create, {summary.skipped} unchanged.")
```

## Origin

This package generalizes earlier planning prototypes into a decoupled, model-driven engine with full pagination and idempotent issue synchronization.
