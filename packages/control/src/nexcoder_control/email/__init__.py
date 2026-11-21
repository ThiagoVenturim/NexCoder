"""Email sending and governance for NexCoder (Gmail, Outlook/Graph, SMTP)."""

from __future__ import annotations

from nexcoder_control.email.config import (
    EmailSettings,
    GmailOAuthSettings,
    OutlookGraphSettings,
    SMTPSettings,
)
from nexcoder_control.email.connectors import (
    BaseEmailConnector,
    GmailOAuthConnector,
    OutlookGraphConnector,
    SMTPConnector,
)
from nexcoder_control.email.models import (
    EmailApprovalRequiredError,
    EmailAttachment,
    EmailDeliveryError,
    EmailError,
    EmailMessage,
    EmailNotConfiguredError,
    EmailRateLimitExceededError,
    EmailRecipient,
    EmailSendResult,
)
from nexcoder_control.email.rate_limiter import EmailRateLimiter
from nexcoder_control.email.service import EmailService
from nexcoder_control.email.templates import EmailTemplate, EmailTemplateManager

__all__ = [
    "BaseEmailConnector",
    "EmailApprovalRequiredError",
    "EmailAttachment",
    "EmailDeliveryError",
    "EmailError",
    "EmailMessage",
    "EmailNotConfiguredError",
    "EmailRateLimitExceededError",
    "EmailRateLimiter",
    "EmailRecipient",
    "EmailSendResult",
    "EmailService",
    "EmailSettings",
    "EmailTemplate",
    "EmailTemplateManager",
    "GmailOAuthConnector",
    "GmailOAuthSettings",
    "OutlookGraphConnector",
    "OutlookGraphSettings",
    "SMTPConnector",
    "SMTPSettings",
]
