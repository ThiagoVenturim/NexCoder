from __future__ import annotations

from typing import Any


def plan_sprints(
    prd_text: str,
    sprint_name: str = "Sprint 1",
    reserve_percentage: float = 0.20,
    team: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Parse a PRD into epics, stories, and tasks, then schedule into sprints with capacity calculation."""
    try:
        from faccoder_planning.capacity import (
            CapacityCalculator,
            SprintCapacityConfig,
            TeamMember,
        )
        from faccoder_planning.prd import PRDConverter
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Planning package not available: {exc}",
        }

    converter = PRDConverter()
    plan = converter.parse_markdown(prd_text)

    team_members: list[TeamMember] = []
    if team:
        for member_dict in team:
            team_members.append(TeamMember(**member_dict))
    else:
        team_members = [
            TeamMember(name="Lead Engineer", daily_hours=8.0, working_days=10),
            TeamMember(name="Fullstack Developer", daily_hours=8.0, working_days=10),
        ]

    config = SprintCapacityConfig(
        sprint_name=sprint_name,
        team=team_members,
        reserve_percentage=reserve_percentage,
    )

    all_tasks = plan.all_tasks()
    calculator = CapacityCalculator()
    sprint_result = calculator.plan_sprint(all_tasks, config)

    return {
        "status": "success",
        "title": plan.title,
        "epics_count": len(plan.epics),
        "stories_count": len(plan.all_stories()),
        "tasks_count": len(all_tasks),
        "scheduled_tasks": [t.model_dump() for t in sprint_result.scheduled_tasks],
        "overflow_tasks": [t.model_dump() for t in sprint_result.overflow_tasks],
        "capacity_report": {
            "sprint_name": sprint_result.capacity_report.sprint_name,
            "gross_hours": sprint_result.capacity_report.gross_hours,
            "reserve_hours": sprint_result.capacity_report.reserve_hours,
            "net_available_hours": sprint_result.capacity_report.net_available_hours,
            "effective_capacity_hours": sprint_result.capacity_report.effective_capacity_hours,
            "planned_hours": sprint_result.capacity_report.planned_hours,
            "is_over_capacity": sprint_result.capacity_report.is_over_capacity,
            "overflow_hours": sprint_result.capacity_report.overflow_hours,
        },
    }


def sync_board(
    platform: str = "github",
    repo: str = "local/repo",
    dry_run: bool = True,
    prd_text: str | None = None,
) -> dict[str, Any]:
    """Synchronize planned tasks with a Git platform issue tracker / Kanban board."""
    try:
        from faccoder_planning.adapters.azure_devops import AzureDevOpsAdapter
        from faccoder_planning.adapters.github import GitHubAdapter
        from faccoder_planning.adapters.gitlab import GitLabAdapter
        from faccoder_planning.models import Plan
        from faccoder_planning.prd import PRDConverter
        from faccoder_planning.sync import BoardSynchronizer
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Planning package not available: {exc}",
        }

    platform_lower = platform.lower()
    if "gitlab" in platform_lower:
        adapter = GitLabAdapter(repo=repo, dry_run=dry_run)
    elif "azure" in platform_lower or "ado" in platform_lower:
        adapter = AzureDevOpsAdapter(repo=repo, dry_run=dry_run)
    else:
        adapter = GitHubAdapter(repo=repo, dry_run=dry_run)

    if prd_text:
        plan = PRDConverter().parse_markdown(prd_text)
    else:
        plan = Plan(title="Backlog Sync Plan", epics=[])

    synchronizer = BoardSynchronizer(adapter=adapter)
    summary = synchronizer.sync_board_and_sprint(
        plan=plan,
        dry_run=dry_run,
    )

    return {
        "status": "success",
        "platform": platform,
        "repo": repo,
        "dry_run": dry_run,
        "total_tasks": summary.total_tasks,
        "moved_count": summary.moved_count,
        "has_slippage": summary.replan_result is not None and summary.replan_result.alert is not None,
    }
