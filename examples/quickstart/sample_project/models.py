"""Domain models for task management library."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Task:
    """Represents a scheduled work task."""

    id: str
    title: str
    description: str = ""
    status: str = "pending"  # pending, in_progress, completed
    due_date: str | None = None  # ISO format: YYYY-MM-DD
    tags: list[str] = field(default_factory=list)

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"
