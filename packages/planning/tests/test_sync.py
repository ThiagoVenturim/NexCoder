from faccoder_planning.adapters.base import PlatformAdapter, RemoteIssue
from faccoder_planning.capacity import SprintCapacityConfig, TeamMember
from faccoder_planning.models import Epic, Plan, Story, Task
from faccoder_planning.sync import BoardColumn, BoardSynchronizer


class DummyPlatformAdapter(PlatformAdapter):
    def __init__(self, issues: list[RemoteIssue]):
        super().__init__(dry_run=True)
        self._issues = issues

    def list_issues(self) -> list[RemoteIssue]:
        return self._issues

    def create_issue(self, task, dry_run=None):
        pass

    def update_issue(self, remote, task, dry_run=None):
        pass


def test_board_synchronizer_column_resolution():
    adapter = DummyPlatformAdapter([])
    sync = BoardSynchronizer(adapter)

    # 1. Closed issue -> Done
    closed_issue = RemoteIssue(id="1", number=1, title="Task", status="closed")
    col, reason = sync.resolve_target_column(closed_issue)
    assert col == BoardColumn.DONE

    # 2. Open issue with merged PR -> Done
    open_issue = RemoteIssue(id="2", number=2, title="Task", status="open")
    col, reason = sync.resolve_target_column(open_issue, pr_state="merged")
    assert col == BoardColumn.DONE

    # 3. Open issue with active PR -> In Review
    col, reason = sync.resolve_target_column(open_issue, pr_state="open")
    assert col == BoardColumn.IN_REVIEW

    # 4. Open issue with progress label -> In Progress
    in_progress_issue = RemoteIssue(
        id="3",
        number=3,
        title="Task",
        status="open",
        labels=["status:em-progresso"],
    )
    col, reason = sync.resolve_target_column(in_progress_issue)
    assert col == BoardColumn.IN_PROGRESS

    # 5. Open issue with no PR or progress label -> Todo
    col, reason = sync.resolve_target_column(open_issue)
    assert col == BoardColumn.TODO


def test_detect_slippage_and_replan():
    adapter = DummyPlatformAdapter([])
    sync = BoardSynchronizer(adapter)

    t1 = Task(id="T1", title="Task 1", estimate_hours=10.0)
    t2 = Task(id="T2", title="Task 2", estimate_hours=15.0)
    t3 = Task(id="T3", title="Task 3", estimate_hours=10.0)
    tasks = [t1, t2, t3]  # Total 35h

    # T1 is completed (10h). Remaining = 25h (T2=15h + T3=10h).
    completed_ids = {"T1"}

    # Available capacity is 20h. Remaining 25h > 20h -> Slippage of 5h!
    alert = sync.detect_slippage(
        tasks=tasks,
        completed_task_ids=completed_ids,
        available_capacity_hours=20.0,
        sprint_name="Sprint 1",
    )
    assert alert is not None
    assert alert.slippage_hours == 5.0
    assert len(alert.recommended_deferrals) >= 1
    # T3 (last item) should be recommended for deferral
    assert alert.recommended_deferrals[0].id == "T3"

    # Replan backlog
    replan = sync.replan_backlog(
        tasks=tasks,
        completed_task_ids=completed_ids,
        available_capacity_hours=20.0,
        sprint_name="Sprint 1",
    )
    assert replan.alert is not None
    # T1 (completed) and T2 (15h <= 20h) are retained
    assert [t.id for t in replan.retained_tasks] == ["T1", "T2"]
    # T3 (10h pushes total to 25h > 20h) is deferred
    assert [t.id for t in replan.deferred_tasks] == ["T3"]


def test_sync_board_and_sprint_full():
    t1 = Task(id="T1", faccoder_id="f-1", title="Task 1", estimate_hours=8.0)
    t2 = Task(id="T2", faccoder_id="f-2", title="Task 2", estimate_hours=8.0)

    issue1 = RemoteIssue(
        id="101",
        number=1,
        title="Task 1",
        status="closed",
        faccoder_id="f-1",
    )
    issue2 = RemoteIssue(
        id="102",
        number=2,
        title="Task 2",
        status="open",
        faccoder_id="f-2",
    )

    adapter = DummyPlatformAdapter([issue1, issue2])
    team = [TeamMember(name="Alice", daily_hours=8.0, working_days=5)]  # 40h gross
    config = SprintCapacityConfig(
        sprint_name="Sprint 1",
        team=team,
        reserve_percentage=0.20,  # 32h net
    )
    sync = BoardSynchronizer(adapter, capacity_config=config)

    plan = Plan(
        title="Plan",
        epics=[
            Epic(
                id="EP-1",
                title="Epic 1",
                stories=[Story(id="US-1", title="Story 1", tasks=[t1, t2])],
            )
        ],
    )

    summary = sync.sync_board_and_sprint(
        plan=plan,
        pr_states_by_issue={2: "open"},  # Issue 2 has open PR -> In Review
        dry_run=True,
    )

    assert summary.total_tasks == 2
    assert len(summary.bindings) == 2
    b1 = next(b for b in summary.bindings if b.task_id == "T1")
    b2 = next(b for b in summary.bindings if b.task_id == "T2")

    assert b1.target_column == BoardColumn.DONE.value
    assert b2.target_column == BoardColumn.IN_REVIEW.value
    # Work fits within 32h capacity, so no slippage alert
    assert summary.replan_result is not None
    assert summary.replan_result.alert is None
