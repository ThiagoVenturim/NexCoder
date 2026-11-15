"""Email connector implementations for Google Gmail, Microsoft Graph, and SMTP."""

from __future__ import annotations

from nexcoder_control.email.connectors.base import BaseEmailConnector
from nexcoder_control.email.connectors.gmail import GmailOAuthConnector
from nexcoder_control.email.connectors.outlook import OutlookGraphConnector
from nexcoder_control.email.connectors.smtp import SMTPConnector

__all__ = [
    "BaseEmailConnector",
    "GmailOAuthConnector",
    "OutlookGraphConnector",
    "SMTPConnector",
]
