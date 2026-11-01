# Agentic Planning: PRDs to Git Tasks

Turning a Product Requirement Document (PRD) into synchronized, trackable code tasks requires more than a simple text summary. It requires understanding dependencies, calculating team capacity, maintaining idempotency, and updating issue trackers as work progresses.

The `faccoder-planning` package provides agentic sprint planning and task synchronization across GitHub, GitLab, and Azure DevOps.

---

## The Planning Flow

```
+--------------------+
|    Approved PRD    |
+---------+----------+
          |
          v
+--------------------+
| 1. Decomposition   | -> Epics -> User Stories -> Tasks (Given/When/Then)
+---------+----------+
          |
          v
+--------------------+
| 2. Dependency Graph| -> Topological sorting, cycle detection, critical path
+---------+----------+
          |
          v
+--------------------+
| 3. Capacity Model  | -> Developer hours, reserve buffers, historical velocity
+---------+----------+
          |
          v
+--------------------+
| 4. Idempotent Sync | -> GitHub Projects v2 / Issues / Milestones with tracking tags
+---------+----------+
          |
          v
+--------------------+
| 5. Sync Loop       | -> Detect slippage, re-plan active sprint, adjust board
+--------------------+
```

---

## 1. Hierarchical Backlog Decomposition

`PRDConverter` parses Markdown PRDs using deterministic heuristics and LLM extraction to produce a hierarchical backlog:

```python
from faccoder_planning import PRDConverter

converter = PRDConverter()
backlog = converter.convert_prd(prd_markdown_text)

for epic in backlog.epics:
    print(f"Epic: {epic.title}")
    for story in epic.stories:
        print(f"  Story: {story.title} ({story.story_points} pts)")
        for task in story.tasks:
            print(f"    Task: {task.title} [{task.layer}] - {task.estimate_hours}h")
```

### Task Specification Schema
Every generated task includes:
- **Title**: Standardized imperative action (`feat(auth): implement token verification`).
- **Layer**: Architectural tier (`core`, `backend`, `frontend`, `data`, `qa`, `security`, `devops`).
- **Acceptance Criteria**: Formatted strictly in Given/When/Then syntax.
- **Dependencies**: Explicit list of prerequisite task IDs.
- **Recommended Agent**: The specialized persona best suited to execute the task (e.g. `lead-architect`, `backend-specialist`, `qa-engineer`).

---

## 2. Sprint Capacity Calculator

Raw backlog estimates cannot be scheduled without accounting for real-world team availability:

```python
from faccoder_planning import CapacityCalculator, SprintCapacityConfig, TeamMember

config = SprintCapacityConfig(
    sprint_duration_days=10,
    daily_working_hours=8.0,
    buffer_reserve_percent=0.20,  # 20% reserve for meetings and unplanned overhead
    historical_velocity_factor=0.90,  # 90% completion rate based on past sprints
)

team = [
    TeamMember(name="Alex", role="backend", daily_hours=8.0, vacation_days=1.0),
    TeamMember(name="Taylor", role="frontend", daily_hours=8.0),
]

calculator = CapacityCalculator(config=config, team=team)
capacity_report = calculator.calculate_available_hours()
print(f"Net scheduled capacity: {capacity_report.available_hours} hours")
```

The calculator matches estimated task hours against layer-specific availability, preventing overallocated backend sprints while frontend engineers wait idle.

---

## 3. Idempotent Platform Adapters

When creating issues in external trackers (such as GitHub, GitLab, or Azure DevOps), repeating the planning step must never create duplicate tickets.

`faccoder-planning` embeds an invisible HTML comment marker into the body of every generated item:

```markdown
<!-- faccoder-id: fc-task-7a9b1c2d-4e5f -->
```

Before creating any ticket or project item, the adapter queries the tracker:
1. Searches existing issues for the matching `faccoder-id`.
2. If found, **updates** the title, description, and milestones in place.
3. If not found, **creates** a new issue and attaches the marker.

### GitHub Projects v2 Integration
The `GitHubAdapter` communicates with GitHub via GraphQL:
- Handles full cursor-based pagination, overcoming the 50/100 item page limits.
- Supports Project v2 custom fields (Status, Story Points, Sprint, Layer).
- Supports `--dry-run` modes across all operations to preview board modifications safely.

---

## 4. The Kanban Synchronization Loop

During active development, tasks finish, slip, or encounter unexpected blockers.

The `BoardSynchronizer` runs continuously or periodically on cron:
1. Queries the active GitHub/GitLab milestone for issue and PR states.
2. Identifies PRs linked to tasks (`Closes #123`) and transitions card status from *In Progress* to *In Review* or *Done*.
3. Compares elapsed sprint time against remaining story points.
4. If remaining hours exceed available capacity, issues an automated **Slippage Alert** recommending the bottom-priority tasks to defer to the next sprint.
