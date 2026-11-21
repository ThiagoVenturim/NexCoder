"""Unit tests for sample task management library."""

from __future__ import annotations

import sys
from pathlib import Path

# Add sample_project parent to sys.path so tests can import sample_project
sys.path.insert(0, str(Path(__file__).parent.parent))

from ..models import Task
from ..service import TaskService
from ..storage import TaskRepository


def test_task_creation_and_completion() -> None:
    repo = TaskRepository()
    svc = TaskService(repo)
    task = svc.create_task("t1", "Implement due dates", due_date="2026-12-01")

    assert task.id == "t1"
    assert task.status == "pending"
    assert not task.is_completed

    assert svc.mark_completed("t1") is True
    assert task.is_completed is True


def test_repository_delete() -> None:
    repo = TaskRepository()
    task = Task("t2", "Cleanup")
    repo.add(task)
    assert repo.get("t2") is not None
    assert repo.delete("t2") is True
    assert repo.get("t2") is None
