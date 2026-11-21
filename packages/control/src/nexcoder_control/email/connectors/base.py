"""Abstract base connector for nexcoder email providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from nexcoder_control.email.models import EmailMessage, EmailSendResult


class BaseEmailConnector(ABC):
    """Abstract interface that all email dispatchers implement."""

    provider_name: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if connector has necessary credentials and configuration."""

    @abstractmethod
    def get_sender(self) -> str:
        """Return authenticated user email address."""

    @abstractmethod
    def send(self, message: EmailMessage) -> EmailSendResult:
        """Dispatch message using provider API or protocol."""
