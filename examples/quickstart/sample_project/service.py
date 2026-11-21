"""Task management business logic."""

from __future__ import annotations

from .models import Task
from .storage import TaskRepository


class TaskService:
    """Core domain service for tasks."""

    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    def create_task(self, task_id: str, title: str, due_date: str | None = None) -> Task:
        task = Task(id=task_id, title=title, due_date=due_date)
        self.repository.add(task)
        return task

    def mark_completed(self, task_id: str) -> bool:
        task = self.repository.get(task_id)
        if not task:
            return False
        task.status = "completed"
        return True

    def is_overdue(self, task: Task, reference_date: str) -> bool:
        """Check whether task is past its due date.

        Known bug: comparison inverted (< instead of >).
        """
        if not task.due_date:
            return False
        # Known bug for pipeline demonstration: inverted condition
        return reference_date < task.due_date

    def export_tasks_csv(self, tasks: list[Task]) -> str:
        """Export tasks as comma-separated values (untested function)."""
        lines = ["id,title,status,due_date"]
        for t in tasks:
            lines.append(f"{t.id},{t.title},{t.status},{t.due_date or ''}")
        return "\n".join(lines)
