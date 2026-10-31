"""Kanban board synchronization, issue/PR state reconciliation, and sprint re-planning."""

from __future__ import annotations

import logging
from enum import StrEnum

from pydantic import BaseModel, Field

from faccoder_planning.adapters.base import PlatformAdapter, RemoteIssue
from faccoder_planning.capacity import SprintCapacityConfig
from faccoder_planning.models import Plan, Task

logger = logging.getLogger(__name__)


class BoardColumn(StrEnum):
    """Standard workflow columns on an agentic Kanban board."""

    BACKLOG = "Backlog"
    TODO = "Todo"
    IN_PROGRESS = "In Progress"
    IN_REVIEW = "In Review"
    DONE = "Done"


class IssuePRBinding(BaseModel):
    """Reconciled state linking a local task, remote issue, and optional pull request."""

    task_id: str
    faccoder_id: str
    issue_number: int | None = None
    pr_number: int | None = None
    current_column: str = BoardColumn.BACKLOG.value
    target_column: str = BoardColumn.TODO.value
    reason: str = ""


class SlippageAlert(BaseModel):
    """Alert raised when remaining task workload exceeds available sprint capacity."""

    sprint_name: str
    planned_hours: float
    remaining_hours: float
    available_hours: float
    slippage_hours: float
    message: str
    recommended_deferrals: list[Task] = Field(default_factory=list)


class ReplanResult(BaseModel):
    """Backlog re-planning outcome triggered by capacity slippage."""

    sprint_name: str
    retained_tasks: list[Task] = Field(default_factory=list)
    deferred_tasks: list[Task] = Field(default_factory=list)
    alert: SlippageAlert | None = None


class BoardSyncSummary(BaseModel):
    """Overall summary of board reconciliation and sprint workload adjustment."""

    total_tasks: int = 0
    moved_count: int = 0
    bindings: list[IssuePRBinding] = Field(default_factory=list)
    replan_result: ReplanResult | None = None
    dry_run: bool = True


class BoardSynchronizer:
    """Reconciles board state from issues/PRs and calculates backlog adjustments on slippage."""

    def __init__(
        self,
        adapter: PlatformAdapter,
        capacity_config: SprintCapacityConfig | None = None,
    ):
        self.adapter = adapter
        self.capacity_config = capacity_config

    def resolve_target_column(
        self,
        issue: RemoteIssue | None,
        pr_state: str | None = None,
        labels: list[str] | None = None,
    ) -> tuple[BoardColumn, str]:
        """Determine target board column based on remote issue status, PR state, and labels."""
        if issue is None:
            return BoardColumn.BACKLOG, "No remote issue mapped"

        # 1. Closed issue or merged PR -> Done
        if issue.status.lower() in ("closed", "done", "completed"):
            return BoardColumn.DONE, "Remote issue is closed"

        if pr_state and pr_state.lower() in ("merged", "closed"):
            return BoardColumn.DONE, "Pull request is merged"

        # 2. Open PR -> In Review
        if pr_state and pr_state.lower() in ("open", "draft", "in_review"):
            return BoardColumn.IN_REVIEW, f"Pull request is active ({pr_state})"

        # 3. Label-based or in-progress status
        effective_labels = labels or issue.labels
        lower_labels = [lbl.lower() for lbl in effective_labels]

        if any("review" in lbl for lbl in lower_labels):
            return BoardColumn.IN_REVIEW, "Tagged for code review"
        if any("progresso" in lbl or "progress" in lbl or "doing" in lbl for lbl in lower_labels):
            return BoardColumn.IN_PROGRESS, "Tagged as active work in progress"

        # 4. Open issue without active PR -> Todo
        return BoardColumn.TODO, "Issue is open and ready to be worked on"

    def detect_slippage(
        self,
        tasks: list[Task],
        completed_task_ids: set[str],
        available_capacity_hours: float,
        sprint_name: str = "Active Sprint",
    ) -> SlippageAlert | None:
        """Evaluate if uncompleted task hours exceed available capacity, raising an alert if so."""
        uncompleted_tasks = [t for t in tasks if t.id not in completed_task_ids]
        remaining_hours = sum(t.estimate_hours for t in uncompleted_tasks)
        planned_hours = sum(t.estimate_hours for t in tasks)

        if remaining_hours <= available_capacity_hours:
            return None

        slippage = remaining_hours - available_capacity_hours
        # Identify low-priority or leaf tasks to defer, walking backwards through task list
        accumulated_to_cut = 0.0
        deferrals: list[Task] = []
        for task in reversed(uncompleted_tasks):
            if accumulated_to_cut < slippage:
                deferrals.append(task)
                accumulated_to_cut += task.estimate_hours

        msg = (
            f"Sprint '{sprint_name}' capacity slipped: {remaining_hours:.1f}h remaining work "
            f"exceeds available {available_capacity_hours:.1f}h by {slippage:.1f}h. "
            f"Recommend deferring {len(deferrals)} task(s)."
        )

        return SlippageAlert(
            sprint_name=sprint_name,
            planned_hours=round(planned_hours, 1),
            remaining_hours=round(remaining_hours, 1),
            available_hours=round(available_capacity_hours, 1),
            slippage_hours=round(slippage, 1),
            message=msg,
            recommended_deferrals=deferrals,
        )

    def replan_backlog(
        self,
        tasks: list[Task],
        completed_task_ids: set[str],
        available_capacity_hours: float,
        sprint_name: str = "Active Sprint",
    ) -> ReplanResult:
        """Re-plan the sprint workload by retaining completed and fitting tasks, deferring excess."""
        alert = self.detect_slippage(tasks, completed_task_ids, available_capacity_hours, sprint_name)

        retained: list[Task] = []
        deferred: list[Task] = []
        accumulated_uncompleted_hours = 0.0

        for task in tasks:
            if task.id in completed_task_ids:
                retained.append(task)
            elif accumulated_uncompleted_hours + task.estimate_hours <= available_capacity_hours:
                retained.append(task)
                accumulated_uncompleted_hours += task.estimate_hours
            else:
                deferred.append(task)

        return ReplanResult(
            sprint_name=sprint_name,
            retained_tasks=retained,
            deferred_tasks=deferred,
            alert=alert,
        )

    def sync_board_and_sprint(
        self,
        plan: Plan,
        pr_states_by_issue: dict[int, str] | None = None,
        remaining_capacity_hours: float | None = None,
        dry_run: bool = True,
    ) -> BoardSyncSummary:
        """Sync board items and evaluate potential slippage across all tasks in a Plan."""
        pr_states = pr_states_by_issue or {}
        bindings: list[IssuePRBinding] = []
        completed_task_ids: set[str] = set()
        moved_count = 0

        # Build map of remote issues by faccoder_id
        remote_issues = self.adapter.list_issues()
        issues_by_marker: dict[str, RemoteIssue] = {}
        for issue in remote_issues:
            if issue.faccoder_id:
                issues_by_marker[issue.faccoder_id] = issue

        for task in plan.all_tasks():
            remote = issues_by_marker.get(task.faccoder_id)
            issue_num = remote.number if remote else None
            pr_state = pr_states.get(issue_num) if issue_num else None

            target_col, reason = self.resolve_target_column(remote, pr_state)
            current_col = BoardColumn.BACKLOG.value
            if remote:
                current_col = BoardColumn.DONE.value if remote.status == "closed" else BoardColumn.TODO.value

            is_moved = current_col != target_col.value
            if is_moved:
                moved_count += 1

            if target_col == BoardColumn.DONE:
                completed_task_ids.add(task.id)

            bindings.append(
                IssuePRBinding(
                    task_id=task.id,
                    faccoder_id=task.faccoder_id,
                    issue_number=issue_num,
                    pr_number=None,
                    current_column=current_col,
                    target_column=target_col.value,
                    reason=reason,
                )
            )

        # Capacity re-planning if remaining capacity is provided or capacity_config exists
        replan_res: ReplanResult | None = None
        cap = remaining_capacity_hours
        if cap is None and self.capacity_config:
            cap = self.capacity_config.total_gross_hours * (1.0 - self.capacity_config.reserve_percentage)

        if cap is not None:
            sprint_name = self.capacity_config.sprint_name if self.capacity_config else "Sprint"
            replan_res = self.replan_backlog(
                tasks=plan.all_tasks(),
                completed_task_ids=completed_task_ids,
                available_capacity_hours=cap,
                sprint_name=sprint_name,
            )

        return BoardSyncSummary(
            total_tasks=len(plan.all_tasks()),
            moved_count=moved_count,
            bindings=bindings,
            replan_result=replan_res,
            dry_run=dry_run,
        )
