from nexcoder_planning.adapters.base import PlatformAdapter, RemoteIssue
from nexcoder_planning.capacity import SprintCapacityConfig, TeamMember
from nexcoder_planning.models import Epic, Plan, Story, Task
from nexcoder_planning.sync import BoardColumn, BoardSynchronizer


class DummyPlatformAdapter(PlatformAdapter):
    def __init__(self, issues: list[RemoteIssue], board_items=None):
        super().__init__(dry_run=True)
        self._issues = issues
        self._board_items = board_items or []
        self.updated_statuses = []

    def list_issues(self) -> list[RemoteIssue]:
        return self._issues

    def list_project_items(self, project_id: str):
        return self._board_items

    def update_project_item_status(
        self, project_id, item_id, field_id, single_select_option_id, content_id=None, dry_run=None
    ):
        self.updated_statuses.append((item_id, single_select_option_id, content_id, dry_run))

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

    # 3. Open issue with closed PR (without merge) -> MUST NOT be Done! Returns Todo
    col, reason = sync.resolve_target_column(open_issue, pr_state="closed")
    assert col == BoardColumn.TODO
    assert "without merge" in reason

    # 4. Open issue with active PR -> In Review
    col, reason = sync.resolve_target_column(open_issue, pr_state="open")
    assert col == BoardColumn.IN_REVIEW

    # 5. Open issue with progress label -> In Progress
    in_progress_issue = RemoteIssue(
        id="3",
        number=3,
        title="Task",
        status="open",
        labels=["status:em-progresso"],
    )
    col, reason = sync.resolve_target_column(in_progress_issue)
    assert col == BoardColumn.IN_PROGRESS

    # 6. Open issue with no PR or progress label -> Todo
    col, reason = sync.resolve_target_column(open_issue)
    assert col == BoardColumn.TODO


def test_detect_slippage_and_replan_with_dependencies():
    adapter = DummyPlatformAdapter([])
    sync = BoardSynchronizer(adapter)

    t1 = Task(id="T1", title="Task 1", estimate_hours=10.0)
    t2 = Task(id="T2", title="Task 2", estimate_hours=15.0, dependencies=["T1"])
    t3 = Task(id="T3", title="Task 3", estimate_hours=10.0, dependencies=["T2"])
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
    # T3 does not fit (15h + 10h = 25h > 20h) and is recommended for deferral
    assert any(t.id == "T3" for t in alert.recommended_deferrals)

    # Replan backlog
    replan = sync.replan_backlog(
        tasks=tasks,
        completed_task_ids=completed_ids,
        available_capacity_hours=20.0,
        sprint_name="Sprint 1",
    )
    assert replan.alert is not None
    assert [t.id for t in replan.retained_tasks] == ["T1", "T2"]
    assert [t.id for t in replan.deferred_tasks] == ["T3"]


def test_replan_backlog_cascading_dependencies():
    adapter = DummyPlatformAdapter([])
    sync = BoardSynchronizer(adapter)

    t1 = Task(id="T1", title="Task 1", estimate_hours=15.0)
    t2 = Task(id="T2", title="Task 2", estimate_hours=10.0, dependencies=["T1"])
    tasks = [t1, t2]

    # Capacity is 12h: T1 (15h) does not fit, so it is deferred.
    # T2 (10h) fits 10h <= 12h, BUT depends on T1! Therefore T2 must also be deferred!
    replan = sync.replan_backlog(
        tasks=tasks,
        completed_task_ids=set(),
        available_capacity_hours=12.0,
        sprint_name="Sprint 1",
    )
    assert replan.alert is not None
    assert [t.id for t in replan.retained_tasks] == []
    assert [t.id for t in replan.deferred_tasks] == ["T1", "T2"]


def test_sync_board_and_sprint_full():
    t1 = Task(id="T1", nexcoder_id="f-1", title="Task 1", estimate_hours=8.0)
    t2 = Task(id="T2", nexcoder_id="f-2", title="Task 2", estimate_hours=8.0)

    issue1 = RemoteIssue(
        id="101",
        number=1,
        title="Task 1",
        status="closed",
        nexcoder_id="f-1",
    )
    issue2 = RemoteIssue(
        id="102",
        number=2,
        title="Task 2",
        status="open",
        nexcoder_id="f-2",
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


def test_sync_board_matching_by_node_id_and_number():
    from nexcoder_planning.adapters.base import ProjectV2Item

    t1 = Task(id="T1", nexcoder_id="f-1", title="Task 1")
    t2 = Task(id="T2", nexcoder_id="f-2", title="Task 2")

    # Issue 1 has REST id "1001", node_id "I_kwDO1", number 1
    # Issue 2 has REST id "1002", node_id None, number 2
    issue1 = RemoteIssue(
        id="1001",
        node_id="I_kwDO1",
        number=1,
        title="Task 1",
        status="open",
        nexcoder_id="f-1",
    )
    issue2 = RemoteIssue(
        id="1002",
        node_id=None,
        number=2,
        title="Task 2",
        status="closed",
        nexcoder_id="f-2",
    )

    # Board item 1 matches issue1 by content_id == node_id
    b_item1 = ProjectV2Item(
        id="ITEM_1",
        content_id="I_kwDO1",
        content_number=1,
        status="Backlog",
    )
    # Board item 2 matches issue2 by content_number == number
    b_item2 = ProjectV2Item(
        id="ITEM_2",
        content_id="DIFFERENT_CONTENT_ID",
        content_number=2,
        status="Todo",
    )

    adapter = DummyPlatformAdapter([issue1, issue2], board_items=[b_item1, b_item2])
    sync = BoardSynchronizer(adapter)

    plan = Plan(
        title="Plan",
        epics=[Epic(id="EP-1", title="Epic 1", stories=[Story(id="US-1", title="Story 1", tasks=[t1, t2])])],
    )

    sync.sync_board_and_sprint(
        plan=plan,
        project_id="PVT_1",
        status_field_id="FIELD_STATUS",
        single_select_option_ids={"Todo": "OPT_TODO", "Done": "OPT_DONE"},
        dry_run=False,
    )

    assert len(adapter.updated_statuses) == 2
    # Item 1 moved to Todo (since open issue), content_id="I_kwDO1"
    assert adapter.updated_statuses[0] == ("ITEM_1", "OPT_TODO", "I_kwDO1", False)
    # Item 2 moved to Done (since closed issue), content_id="DIFFERENT_CONTENT_ID"
    assert adapter.updated_statuses[1] == ("ITEM_2", "OPT_DONE", "DIFFERENT_CONTENT_ID", False)
