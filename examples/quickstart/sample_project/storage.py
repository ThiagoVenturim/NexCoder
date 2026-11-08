"""In-memory task storage repository."""

from __future__ import annotations

from .models import Task


class TaskRepository:
    """Thread-safe in-memory task catalog."""

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def add(self, task: Task) -> None:
        self._tasks[task.id] = task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_all(self) -> list[Task]:
        return list(self._tasks.values())

    def delete(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False
