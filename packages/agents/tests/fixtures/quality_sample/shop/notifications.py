"""Customer notifications for the sample shop."""

from __future__ import annotations

from abc import ABC, abstractmethod


class NotifierStrategy(ABC):
    """Planted over-engineering: an abstraction with one implementation."""

    @abstractmethod
    def send(self, recipient: str, message: str) -> bool:
        raise NotImplementedError


class EmailNotifier(NotifierStrategy):
    def __init__(self) -> None:
        self.outbox: list[tuple[str, str]] = []

    def send(self, recipient: str, message: str) -> bool:
        self.outbox.append((recipient, message))
        return True
