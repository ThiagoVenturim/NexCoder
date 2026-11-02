"""Sprint capacity modeling, velocity tracking, and workload scheduling."""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from faccoder_planning.models import Plan, Task


class TeamMember(BaseModel):
    """Capacity parameters for an individual team contributor."""

    name: str
    daily_hours: float = 8.0
    working_days: int = 10
    time_off_days: float = 0.0
    focus_factor: float = 1.0

    @property
    def gross_hours(self) -> float:
        """Calculate total gross hours available during the sprint period."""
        effective_days = max(0.0, float(self.working_days) - float(self.time_off_days))
        return effective_days * self.daily_hours * self.focus_factor


class VelocityRecord(BaseModel):
    """Historical performance record from a completed sprint."""

    sprint_name: str
    planned_hours: float
    completed_hours: float
    carried_over_hours: float = 0.0
    planned_tasks_count: int = 0
    completed_tasks_count: int = 0

    @property
    def velocity_ratio(self) -> float:
        """Ratio of hours actually completed against original planned estimate."""
        if self.planned_hours <= 0:
            return 1.0
        return self.completed_hours / self.planned_hours

    @property
    def carryover_ratio(self) -> float:
        """Ratio of hours carried over against original planned estimate."""
        if self.planned_hours <= 0:
            return 0.0
        return self.carried_over_hours / self.planned_hours


class SprintVelocityMetrics(BaseModel):
    """Aggregated historical velocity metrics and predictability trends."""

    total_sprints: int
    average_velocity_hours: float
    rolling_velocity_hours: float
    velocity_std_dev: float
    predictability_percentage: float
    velocity_trend: str  # "increasing", "stable", "declining"
    carryover_rate_percentage: float
    sprint_records: list[VelocityRecord] = Field(default_factory=list)


class SprintForecast(BaseModel):
    """Forecast of remaining backlog workload across future sprints."""

    remaining_backlog_hours: float
    estimated_sprints_needed: float
    confidence_range_sprints: tuple[int, int]
    recommended_capacity_per_sprint: float
    forecast_model: str = "rolling_average"


class VelocityTracker:
    """Tracks historical sprint performance and forecasts delivery velocity."""

    def __init__(self, history: list[VelocityRecord] | None = None):
        self.history: list[VelocityRecord] = list(history) if history else []

    def record_sprint(
        self,
        sprint_name: str,
        planned_hours: float,
        completed_hours: float,
        carried_over_hours: float = 0.0,
        planned_tasks_count: int = 0,
        completed_tasks_count: int = 0,
    ) -> VelocityRecord:
        """Add a completed sprint performance record to the historical tracking log."""
        record = VelocityRecord(
            sprint_name=sprint_name,
            planned_hours=planned_hours,
            completed_hours=completed_hours,
            carried_over_hours=carried_over_hours,
            planned_tasks_count=planned_tasks_count,
            completed_tasks_count=completed_tasks_count,
        )
        self.history.append(record)
        return record

    def calculate_metrics(self, window: int = 5) -> SprintVelocityMetrics:
        """Calculate comprehensive velocity metrics across past sprints."""
        if not self.history:
            return SprintVelocityMetrics(
                total_sprints=0,
                average_velocity_hours=0.0,
                rolling_velocity_hours=0.0,
                velocity_std_dev=0.0,
                predictability_percentage=100.0,
                velocity_trend="stable",
                carryover_rate_percentage=0.0,
                sprint_records=[],
            )

        completed_list = [r.completed_hours for r in self.history]
        total_sprints = len(completed_list)
        avg_velocity = sum(completed_list) / total_sprints

        # Rolling window
        recent = self.history[-window:]
        recent_completed = [r.completed_hours for r in recent]
        rolling_velocity = sum(recent_completed) / len(recent_completed)

        # Standard deviation
        variance = sum((x - avg_velocity) ** 2 for x in completed_list) / total_sprints
        std_dev = math.sqrt(variance)

        # Predictability percentage (average of completed / planned)
        predictability_values = [r.velocity_ratio * 100.0 for r in self.history if r.planned_hours > 0]
        predictability_pct = sum(predictability_values) / len(predictability_values) if predictability_values else 100.0

        # Carryover rate percentage
        carryover_values = [r.carryover_ratio * 100.0 for r in self.history if r.planned_hours > 0]
        carryover_pct = sum(carryover_values) / len(carryover_values) if carryover_values else 0.0

        # Trend analysis (comparing recent rolling velocity to overall average)
        if len(self.history) >= 2:
            first_half = completed_list[: len(completed_list) // 2]
            second_half = completed_list[len(completed_list) // 2 :]
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)
            diff_ratio = (avg_second - avg_first) / max(1.0, avg_first)
            if diff_ratio > 0.10:
                trend = "increasing"
            elif diff_ratio < -0.10:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"

        return SprintVelocityMetrics(
            total_sprints=total_sprints,
            average_velocity_hours=round(avg_velocity, 2),
            rolling_velocity_hours=round(rolling_velocity, 2),
            velocity_std_dev=round(std_dev, 2),
            predictability_percentage=round(predictability_pct, 1),
            velocity_trend=trend,
            carryover_rate_percentage=round(carryover_pct, 1),
            sprint_records=list(self.history),
        )

    def forecast(
        self,
        remaining_backlog_hours: float,
        window: int = 5,
    ) -> SprintForecast:
        """Forecast future sprints needed to complete remaining workload."""
        metrics = self.calculate_metrics(window=window)
        effective_vel = (
            metrics.rolling_velocity_hours if metrics.rolling_velocity_hours > 0 else metrics.average_velocity_hours
        )

        if effective_vel <= 0:
            effective_vel = 80.0

        sprints_needed = remaining_backlog_hours / effective_vel

        # Confidence bounds using std_dev
        std = metrics.velocity_std_dev
        optimistic_vel = max(1.0, effective_vel + std)
        pessimistic_vel = max(1.0, effective_vel - std)

        min_sprints = max(1, math.ceil(remaining_backlog_hours / optimistic_vel))
        max_sprints = max(1, math.ceil(remaining_backlog_hours / pessimistic_vel))

        return SprintForecast(
            remaining_backlog_hours=round(remaining_backlog_hours, 2),
            estimated_sprints_needed=round(sprints_needed, 2),
            confidence_range_sprints=(min_sprints, max_sprints),
            recommended_capacity_per_sprint=round(effective_vel, 2),
            forecast_model="rolling_average",
        )

    def evaluate_carryover(
        self,
        planned_tasks: list[Task],
        completed_task_ids: set[str],
    ) -> tuple[list[Task], list[Task], float]:
        """Separate completed tasks from uncompleted carryover tasks and calculate carried-over hours."""
        completed: list[Task] = []
        carried_over: list[Task] = []
        carried_over_hours = 0.0

        for task in planned_tasks:
            if task.id in completed_task_ids:
                completed.append(task)
            else:
                carried_over.append(task)
                carried_over_hours += task.estimate_hours

        return completed, carried_over, round(carried_over_hours, 2)


class SprintCapacityConfig(BaseModel):
    """Configuration parameters for evaluating sprint capacity."""

    sprint_name: str
    team: list[TeamMember]
    working_days: int = 10
    reserve_percentage: float = 0.15
    velocity_history: list[VelocityRecord] = Field(default_factory=list)

    @property
    def total_gross_hours(self) -> float:
        """Sum of gross hours across all team members."""
        return sum(member.gross_hours for member in self.team)

    @property
    def velocity_factor(self) -> float:
        """Compute rolling average velocity factor from past sprint records."""
        if not self.velocity_history:
            return 1.0
        recent = self.velocity_history[-5:]
        total_planned = sum(r.planned_hours for r in recent)
        total_completed = sum(r.completed_hours for r in recent)
        if total_planned <= 0:
            return 1.0
        return total_completed / total_planned

    def get_velocity_tracker(self) -> VelocityTracker:
        """Instantiate a VelocityTracker loaded with historical velocity records."""
        return VelocityTracker(self.velocity_history)


class CapacityReport(BaseModel):
    """Detailed calculation report comparing workload to sprint capacity."""

    sprint_name: str
    gross_hours: float
    reserve_percentage: float
    reserve_hours: float
    net_available_hours: float
    velocity_factor: float
    effective_capacity_hours: float
    planned_hours: float
    is_over_capacity: bool
    overflow_hours: float


class SprintPlanResult(BaseModel):
    """Result of scheduling tasks into sprint capacity, separating scheduled and overflow items."""

    sprint_name: str
    capacity_report: CapacityReport
    scheduled_tasks: list[Task]
    overflow_tasks: list[Task]


class CapacityCalculator:
    """Calculates team capacity and schedules tasks respecting limits and dependencies."""

    def evaluate_capacity(
        self,
        config: SprintCapacityConfig,
        planned_hours: float = 0.0,
    ) -> CapacityReport:
        """Evaluate capacity metrics for a given configuration and planned workload."""
        gross = config.total_gross_hours
        reserve_hrs = gross * config.reserve_percentage
        net_hrs = max(0.0, gross - reserve_hrs)
        v_factor = config.velocity_factor
        effective_capacity = net_hrs * v_factor

        is_over = planned_hours > effective_capacity
        overflow = max(0.0, planned_hours - effective_capacity)

        return CapacityReport(
            sprint_name=config.sprint_name,
            gross_hours=round(gross, 2),
            reserve_percentage=config.reserve_percentage,
            reserve_hours=round(reserve_hrs, 2),
            net_available_hours=round(net_hrs, 2),
            velocity_factor=round(v_factor, 3),
            effective_capacity_hours=round(effective_capacity, 2),
            planned_hours=round(planned_hours, 2),
            is_over_capacity=is_over,
            overflow_hours=round(overflow, 2),
        )

    def plan_sprint(
        self,
        tasks_or_plan: list[Task] | Plan,
        config: SprintCapacityConfig,
    ) -> SprintPlanResult:
        """Schedule tasks into the sprint up to effective capacity, pushing overflow to next sprint."""
        if isinstance(tasks_or_plan, Plan):
            tasks = tasks_or_plan.topological_sort_tasks()
        else:
            # Sort with basic in-degree dependency ordering
            all_tasks_map = {t.id: t for t in tasks_or_plan}
            in_degree = {t.id: 0 for t in tasks_or_plan}
            dependents: dict[str, list[str]] = {t.id: [] for t in tasks_or_plan}

            for t in tasks_or_plan:
                for dep in t.dependencies:
                    if dep in all_tasks_map:
                        dependents[dep].append(t.id)
                        in_degree[t.id] += 1

            queue = [t.id for t in tasks_or_plan if in_degree[t.id] == 0]
            sorted_tasks: list[Task] = []
            while queue:
                curr_id = queue.pop(0)
                sorted_tasks.append(all_tasks_map[curr_id])
                for child in dependents.get(curr_id, []):
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        queue.append(child)

            if len(sorted_tasks) < len(tasks_or_plan):
                for t in tasks_or_plan:
                    if t not in sorted_tasks:
                        sorted_tasks.append(t)
            tasks = sorted_tasks

        # Calculate base capacity
        gross = config.total_gross_hours
        reserve_hrs = gross * config.reserve_percentage
        net_hrs = max(0.0, gross - reserve_hrs)
        v_factor = config.velocity_factor
        effective_capacity = net_hrs * v_factor

        scheduled: list[Task] = []
        overflow: list[Task] = []
        accumulated_hours = 0.0

        for task in tasks:
            # Check if task can fit within remaining effective capacity
            if accumulated_hours + task.estimate_hours <= effective_capacity:
                scheduled.append(task)
                accumulated_hours += task.estimate_hours
            elif not scheduled:
                scheduled.append(task)
                accumulated_hours += task.estimate_hours
            else:
                overflow.append(task)

        report = self.evaluate_capacity(config, planned_hours=accumulated_hours)

        return SprintPlanResult(
            sprint_name=config.sprint_name,
            capacity_report=report,
            scheduled_tasks=scheduled,
            overflow_tasks=overflow,
        )
