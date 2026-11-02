from faccoder_planning.capacity import (
    SprintCapacityConfig,
    TeamMember,
    VelocityRecord,
    VelocityTracker,
)
from faccoder_planning.models import Task


def test_velocity_record_properties():
    record = VelocityRecord(
        sprint_name="Sprint 1",
        planned_hours=80.0,
        completed_hours=72.0,
        carried_over_hours=8.0,
        planned_tasks_count=10,
        completed_tasks_count=9,
    )
    assert record.velocity_ratio == 0.9
    assert record.carryover_ratio == 0.1

    # Zero planned hours safe division
    zero_record = VelocityRecord(sprint_name="Zero", planned_hours=0.0, completed_hours=0.0)
    assert zero_record.velocity_ratio == 1.0
    assert zero_record.carryover_ratio == 0.0


def test_velocity_tracker_empty_history():
    tracker = VelocityTracker()
    metrics = tracker.calculate_metrics()
    assert metrics.total_sprints == 0
    assert metrics.average_velocity_hours == 0.0
    assert metrics.rolling_velocity_hours == 0.0
    assert metrics.predictability_percentage == 100.0
    assert metrics.velocity_trend == "stable"
    assert metrics.carryover_rate_percentage == 0.0

    forecast = tracker.forecast(remaining_backlog_hours=160.0)
    assert forecast.remaining_backlog_hours == 160.0
    # Fallback velocity 80h per sprint
    assert forecast.estimated_sprints_needed == 2.0


def test_velocity_tracker_metrics_calculation_and_trends():
    tracker = VelocityTracker()

    # Add 4 sprints with increasing delivery velocity
    tracker.record_sprint("Sprint 1", planned_hours=80.0, completed_hours=60.0, carried_over_hours=20.0)
    tracker.record_sprint("Sprint 2", planned_hours=80.0, completed_hours=65.0, carried_over_hours=15.0)
    tracker.record_sprint("Sprint 3", planned_hours=80.0, completed_hours=75.0, carried_over_hours=5.0)
    tracker.record_sprint("Sprint 4", planned_hours=80.0, completed_hours=80.0, carried_over_hours=0.0)

    metrics = tracker.calculate_metrics(window=3)
    assert metrics.total_sprints == 4
    # (60 + 65 + 75 + 80) / 4 = 280 / 4 = 70.0
    assert metrics.average_velocity_hours == 70.0
    # Rolling last 3: (65 + 75 + 80) / 3 = 220 / 3 = 73.33
    assert metrics.rolling_velocity_hours == 73.33
    assert metrics.velocity_trend == "increasing"
    assert metrics.velocity_std_dev > 0.0
    # Average completion ratio: (0.75 + 0.8125 + 0.9375 + 1.0) / 4 = 3.5 / 4 = 87.5%
    assert metrics.predictability_percentage == 87.5
    # Average carryover ratio: (0.25 + 0.1875 + 0.0625 + 0.0) / 4 = 0.5 / 4 = 12.5%
    assert metrics.carryover_rate_percentage == 12.5


def test_velocity_tracker_declining_trend():
    tracker = VelocityTracker()
    tracker.record_sprint("Sprint 1", planned_hours=80.0, completed_hours=80.0)
    tracker.record_sprint("Sprint 2", planned_hours=80.0, completed_hours=78.0)
    tracker.record_sprint("Sprint 3", planned_hours=80.0, completed_hours=60.0)
    tracker.record_sprint("Sprint 4", planned_hours=80.0, completed_hours=50.0)

    metrics = tracker.calculate_metrics()
    assert metrics.velocity_trend == "declining"


def test_velocity_tracker_forecast():
    tracker = VelocityTracker()
    tracker.record_sprint("Sprint 1", planned_hours=80.0, completed_hours=70.0)
    tracker.record_sprint("Sprint 2", planned_hours=80.0, completed_hours=75.0)
    tracker.record_sprint("Sprint 3", planned_hours=80.0, completed_hours=75.0)

    forecast = tracker.forecast(remaining_backlog_hours=220.0)
    assert forecast.remaining_backlog_hours == 220.0
    # rolling velocity is 73.33h -> 220 / 73.33 ~ 3.0 sprints
    assert 2.9 <= forecast.estimated_sprints_needed <= 3.1
    min_s, max_s = forecast.confidence_range_sprints
    assert min_s <= max_s
    assert min_s >= 1


def test_velocity_tracker_evaluate_carryover():
    tracker = VelocityTracker()

    t1 = Task(id="T1", title="Task 1", estimate_hours=4.0)
    t2 = Task(id="T2", title="Task 2", estimate_hours=6.0)
    t3 = Task(id="T3", title="Task 3", estimate_hours=8.0)

    completed, carried_over, overflow_hours = tracker.evaluate_carryover(
        planned_tasks=[t1, t2, t3],
        completed_task_ids={"T1", "T3"},
    )

    assert len(completed) == 2
    assert completed[0].id == "T1"
    assert completed[1].id == "T3"
    assert len(carried_over) == 1
    assert carried_over[0].id == "T2"
    assert overflow_hours == 6.0


def test_capacity_config_velocity_tracker_integration():
    records = [
        VelocityRecord(sprint_name="S1", planned_hours=40.0, completed_hours=36.0),
        VelocityRecord(sprint_name="S2", planned_hours=40.0, completed_hours=38.0),
    ]
    member = TeamMember(name="Dev 1", daily_hours=8.0, working_days=5)
    config = SprintCapacityConfig(
        sprint_name="Sprint 3",
        team=[member],
        velocity_history=records,
    )

    tracker = config.get_velocity_tracker()
    metrics = tracker.calculate_metrics()
    assert metrics.total_sprints == 2
    assert metrics.average_velocity_hours == 37.0
