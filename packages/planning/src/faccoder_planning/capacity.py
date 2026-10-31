"""Sprint capacity modeling, velocity tracking, and workload scheduling."""

from __future__ import annotations

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

    @property
    def velocity_ratio(self) -> float:
        """Ratio of hours actually completed against original planned estimate."""
        if self.planned_hours <= 0:
            return 1.0
        return self.completed_hours / self.planned_hours


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
            # Build mini plan to sort topologically if dependencies exist
            temp_plan = Plan(title="Temp", epics=[])
            temp_plan.epics = []
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
            # If the task would push over capacity, move to overflow
            if accumulated_hours + task.estimate_hours <= effective_capacity or not scheduled:
                # Always accept at least the first task if capacity is tight, or fit while space permits
                if accumulated_hours + task.estimate_hours <= effective_capacity:
                    scheduled.append(task)
                    accumulated_hours += task.estimate_hours
                elif not scheduled:
                    scheduled.append(task)
                    accumulated_hours += task.estimate_hours
                else:
                    overflow.append(task)
            else:
                overflow.append(task)

        report = self.evaluate_capacity(config, planned_hours=accumulated_hours)

        return SprintPlanResult(
            sprint_name=config.sprint_name,
            capacity_report=report,
            scheduled_tasks=scheduled,
            overflow_tasks=overflow,
        )
