"""Data models and exceptions for nexcoder email sending and governance."""

from __future__ import annotations

import base64
import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EmailError(Exception):
    """Base exception for email operations."""


class EmailApprovalRequiredError(EmailError):
    """Raised when an email dispatch is blocked pending human confirmation."""

    def __init__(
        self,
        message: str = "Email dispatch requires human approval before sending",
        preview: dict[str, Any] | None = None,
        token_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.preview = preview or {}
        self.token_id = token_id


class EmailNotConfiguredError(EmailError):
    """Raised when an email provider is requested but credentials are unconfigured."""


class EmailRateLimitExceededError(EmailError):
    """Raised when sending rate exceeds provider throttling limits."""

    def __init__(self, provider: str, limit_rpm: int, retry_after_seconds: float = 60.0) -> None:
        super().__init__(
            f"Rate limit exceeded for provider '{provider}' (limit: {limit_rpm} req/min). "
            f"Retry after {retry_after_seconds:.1f}s."
        )
        self.provider = provider
        self.limit_rpm = limit_rpm
        self.retry_after_seconds = retry_after_seconds


class EmailDeliveryError(EmailError):
    """Raised when provider delivery fails after all retries."""


class EmailRecipient(BaseModel):
    """Structured recipient with optional display name."""

    email: str
    name: str | None = None

    def formatted(self) -> str:
        clean_email = self.email.strip()
        if self.name and self.name.strip():
            clean_name = self.name.strip().replace('"', "")
            return f'"{clean_name}" <{clean_email}>'
        return clean_email


class EmailAttachment(BaseModel):
    """File attachment (PDF, report, screenshot, or document)."""

    filename: str
    content: bytes | None = None
    file_path: str | None = None
    content_type: str | None = None
    inline: bool = False
    content_id: str | None = None

    def get_bytes(self) -> bytes:
        """Resolve attachment binary content from bytes or file path."""
        if self.content is not None:
            return self.content
        if self.file_path:
            p = Path(self.file_path).resolve()
            if not p.is_file():
                raise FileNotFoundError(f"Attachment file not found: {self.file_path}")
            return p.read_bytes()
        return b""

    def get_content_type(self) -> str:
        """Guess or return MIME content type."""
        if self.content_type and self.content_type.strip():
            return self.content_type.strip()
        guessed, _ = mimetypes.guess_type(self.filename)
        return guessed or "application/octet-stream"

    def to_base64(self) -> str:
        """Return base64-encoded string of attachment bytes."""
        return base64.b64encode(self.get_bytes()).decode("ascii")

    def size_bytes(self) -> int:
        """Return size in bytes."""
        return len(self.get_bytes())


class EmailMessage(BaseModel):
    """Outgoing email payload with HTML, plain text, and attachments."""

    subject: str
    recipients: list[str | EmailRecipient]
    cc: list[str | EmailRecipient] = Field(default_factory=list)
    bcc: list[str | EmailRecipient] = Field(default_factory=list)
    sender: str | None = None
    body_html: str | None = None
    body_text: str | None = None
    attachments: list[EmailAttachment] = Field(default_factory=list)
    template_name: str | None = None
    template_vars: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)

    def normalized_recipients(self) -> list[str]:
        return [r.email if isinstance(r, EmailRecipient) else str(r).strip() for r in self.recipients]

    def normalized_cc(self) -> list[str]:
        return [r.email if isinstance(r, EmailRecipient) else str(r).strip() for r in self.cc]

    def normalized_bcc(self) -> list[str]:
        return [r.email if isinstance(r, EmailRecipient) else str(r).strip() for r in self.bcc]

    def get_plain_text(self) -> str:
        """Provide clean text representation, deriving from HTML if missing."""
        if self.body_text and self.body_text.strip():
            return self.body_text.strip()
        if self.body_html:
            clean = re.sub(r"<[^>]+>", " ", self.body_html)
            clean = re.sub(r"\s+", " ", clean).strip()
            return clean
        return ""


class EmailSendResult(BaseModel):
    """Result of an email dispatch attempt."""

    success: bool
    provider: str
    message_id: str | None = None
    sender: str = ""
    recipients: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    audit_event_id: str | None = None
    status: str = "sent"
    error_message: str | None = None
    preview_data: dict[str, Any] | None = None
