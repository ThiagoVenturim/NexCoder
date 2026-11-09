from nexcoder_planning.capacity import (
    CapacityCalculator,
    SprintCapacityConfig,
    TeamMember,
    VelocityRecord,
)
from nexcoder_planning.models import Task


def test_team_member_gross_hours():
    member = TeamMember(
        name="Developer A",
        daily_hours=8.0,
        working_days=10,
        time_off_days=2.0,
        focus_factor=0.9,
    )
    # (10 - 2) * 8 * 0.9 = 8 * 7.2 = 57.6
    assert round(member.gross_hours, 2) == 57.6


def test_velocity_factor_calculation():
    records = [
        VelocityRecord(sprint_name="Sprint 1", planned_hours=80.0, completed_hours=72.0),  # 0.9
        VelocityRecord(sprint_name="Sprint 2", planned_hours=80.0, completed_hours=88.0),  # 1.1
    ]
    config = SprintCapacityConfig(
        sprint_name="Sprint 3",
        team=[TeamMember(name="Dev", daily_hours=8.0, working_days=10)],  # 80h gross
        velocity_history=records,
        reserve_percentage=0.10,
    )
    # total planned = 160, total completed = 160 -> factor = 1.0
    assert config.velocity_factor == 1.0

    # With unequal totals
    records_unequal = [
        VelocityRecord(sprint_name="Sprint 1", planned_hours=100.0, completed_hours=80.0),
    ]
    config_unequal = SprintCapacityConfig(
        sprint_name="Sprint 2",
        team=[TeamMember(name="Dev", daily_hours=8.0, working_days=10)],
        velocity_history=records_unequal,
    )
    assert config_unequal.velocity_factor == 0.8


def test_capacity_evaluation_and_buffer():
    team = [
        TeamMember(name="Alice", daily_hours=8.0, working_days=10, time_off_days=0.0),  # 80h
        TeamMember(name="Bob", daily_hours=8.0, working_days=10, time_off_days=0.0),  # 80h
    ]
    # Total gross = 160h. Reserve = 20% (32h). Net = 128h.
    config = SprintCapacityConfig(
        sprint_name="Sprint 1",
        team=team,
        reserve_percentage=0.20,
    )
    calculator = CapacityCalculator()
    report = calculator.evaluate_capacity(config, planned_hours=140.0)

    assert report.gross_hours == 160.0
    assert report.reserve_hours == 32.0
    assert report.net_available_hours == 128.0
    assert report.effective_capacity_hours == 128.0
    assert report.is_over_capacity is True
    assert report.overflow_hours == 12.0


def test_sprint_planning_task_scheduling_and_overflow():
    team = [TeamMember(name="Alice", daily_hours=8.0, working_days=5)]  # 40h gross
    # Reserve 25% -> 10h reserve -> 30h effective capacity
    config = SprintCapacityConfig(
        sprint_name="Sprint 1",
        team=team,
        reserve_percentage=0.25,
    )

    t1 = Task(id="T1", title="Task 1", estimate_hours=12.0)
    t2 = Task(id="T2", title="Task 2", estimate_hours=15.0, dependencies=["T1"])
    t3 = Task(id="T3", title="Task 3", estimate_hours=10.0, dependencies=["T2"])

    calculator = CapacityCalculator()
    result = calculator.plan_sprint([t3, t2, t1], config)

    # T1 (12h) + T2 (15h) = 27h <= 30h.
    # T3 (10h) would push to 37h > 30h -> overflow!
    assert len(result.scheduled_tasks) == 2
    assert [t.id for t in result.scheduled_tasks] == ["T1", "T2"]
    assert len(result.overflow_tasks) == 1
    assert result.overflow_tasks[0].id == "T3"
