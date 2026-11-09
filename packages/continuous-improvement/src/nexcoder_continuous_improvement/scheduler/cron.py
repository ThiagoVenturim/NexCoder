"""Configurable cron scheduler for continuous analysis, research, and security routines."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field


class CronJob(BaseModel):
    name: str
    schedule: str  # e.g., "@daily", "@hourly", "*/30 * * * *"
    task_type: str
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = 0
    last_status: str = "pending"
    parameters: dict[str, Any] = Field(default_factory=dict)


def compute_next_run(schedule: str, from_time: datetime | None = None) -> datetime:
    """Calculate the next execution time based on interval or standard cron shortcut."""
    base = from_time or datetime.now(UTC)
    s = schedule.strip().lower()

    if s == "@hourly":
        return base + timedelta(hours=1)
    if s == "@daily":
        return base + timedelta(days=1)
    if s == "@weekly":
        return base + timedelta(weeks=1)

    # Simple minute interval syntax e.g. "*/N * * * *"
    if s.startswith("*/"):
        parts = s.split()
        try:
            minute_interval = int(parts[0].replace("*/", ""))
            return base + timedelta(minutes=max(1, minute_interval))
        except ValueError:
            pass

    # Default fallback interval: 1 day
    return base + timedelta(days=1)


class CronScheduler:
    """Manages scheduled continuous improvement tasks and execution tracking."""

    def __init__(self) -> None:
        self.jobs: dict[str, CronJob] = {}
        self.handlers: dict[str, Callable[[CronJob], Any]] = {}

    def register_job(self, job: CronJob) -> None:
        """Register a new scheduled job and compute its initial next_run."""
        if not job.next_run:
            job.next_run = compute_next_run(job.schedule)
        self.jobs[job.name] = job

    def register_handler(self, task_type: str, handler: Callable[[CronJob], Any]) -> None:
        """Register an execution handler for a specific task type."""
        self.handlers[task_type] = handler

    def get_due_jobs(self, current_time: datetime | None = None) -> list[CronJob]:
        """Return all enabled jobs whose next_run is at or before current_time."""
        now = current_time or datetime.now(UTC)
        due: list[CronJob] = []
        for job in self.jobs.values():
            if job.enabled and job.next_run and job.next_run <= now:
                due.append(job)
        return due

    def run_due_jobs(self, current_time: datetime | None = None) -> list[dict[str, Any]]:
        """Execute all due jobs using their registered handlers and update execution state."""
        now = current_time or datetime.now(UTC)
        due_jobs = self.get_due_jobs(now)
        results: list[dict[str, Any]] = []

        for job in due_jobs:
            handler = self.handlers.get(job.task_type)
            result_entry: dict[str, Any] = {"job_name": job.name, "task_type": job.task_type}
            if handler:
                try:
                    res = handler(job)
                    job.last_status = "success"
                    result_entry["result"] = res
                    result_entry["status"] = "success"
                except Exception as exc:  # noqa: BLE001
                    job.last_status = f"error: {exc}"
                    result_entry["error"] = str(exc)
                    result_entry["status"] = "error"
            else:
                job.last_status = "no_handler"
                result_entry["status"] = "no_handler"

            job.last_run = now
            job.run_count += 1
            job.next_run = compute_next_run(job.schedule, from_time=now)
            results.append(result_entry)

        return results
