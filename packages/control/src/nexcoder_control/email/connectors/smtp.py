"""Fallback generic SMTP connector supporting STARTTLS, SSL, and attachments."""

from __future__ import annotations

import smtplib
import uuid
from collections.abc import Callable
from email.message import EmailMessage as PyEmailMessage
from typing import Any

from nexcoder_control.email.config import SMTPSettings
from nexcoder_control.email.connectors.base import BaseEmailConnector
from nexcoder_control.email.models import (
    EmailDeliveryError,
    EmailMessage,
    EmailNotConfiguredError,
    EmailSendResult,
)


class SMTPConnector(BaseEmailConnector):
    """Dispatches outgoing email via standard SMTP / STARTTLS."""

    provider_name = "smtp"

    def __init__(
        self,
        settings: SMTPSettings | None = None,
        smtp_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings or SMTPSettings()
        self._smtp_factory = smtp_factory

    def is_configured(self) -> bool:
        return self.settings.is_configured()

    def get_sender(self) -> str:
        return self.settings.from_email or self.settings.username or "user@localhost"

    def build_mime_message(self, message: EmailMessage) -> PyEmailMessage:
        """Construct standard RFC 2822 MIME message."""
        msg = PyEmailMessage()
        msg["Subject"] = message.subject
        sender = message.sender or self.get_sender()
        msg["From"] = sender
        msg["To"] = ", ".join(message.normalized_recipients())

        if message.normalized_cc():
            msg["Cc"] = ", ".join(message.normalized_cc())
        if message.normalized_bcc():
            msg["Bcc"] = ", ".join(message.normalized_bcc())

        for k, v in message.headers.items():
            msg[k] = v

        plain_text = message.get_plain_text()
        if message.body_html:
            msg.set_content(plain_text)
            msg.add_alternative(message.body_html, subtype="html")
        else:
            msg.set_content(plain_text)

        for att in message.attachments:
            raw = att.get_bytes()
            ctype = att.get_content_type()
            maintype, subtype = ctype.split("/", 1) if "/" in ctype else ("application", "octet-stream")
            msg.add_attachment(
                raw,
                maintype=maintype,
                subtype=subtype,
                filename=att.filename,
            )

        return msg

    def _create_smtp_client(self) -> Any:
        if self._smtp_factory is not None:
            return self._smtp_factory()

        host = self.settings.host or "localhost"
        port = self.settings.port or (465 if self.settings.use_ssl else 587)

        if self.settings.use_ssl:
            return smtplib.SMTP_SSL(host=host, port=port, timeout=30.0)
        return smtplib.SMTP(host=host, port=port, timeout=30.0)

    def send(self, message: EmailMessage) -> EmailSendResult:
        if not self.is_configured():
            raise EmailNotConfiguredError("SMTP connector is not configured with host")

        recipients = message.normalized_recipients()
        if not recipients:
            raise ValueError("Message must have at least one recipient")

        mime_msg = self.build_mime_message(message)

        try:
            client = self._create_smtp_client()
            with client:
                if self.settings.use_tls and not self.settings.use_ssl:
                    client.starttls()
                if self.settings.username and self.settings.password:
                    client.login(self.settings.username, self.settings.password)

                all_destinations = recipients + message.normalized_cc() + message.normalized_bcc()
                client.send_message(mime_msg, to_addrs=all_destinations)

            msg_id = f"smtp_{uuid.uuid4().hex[:12]}"
            return EmailSendResult(
                success=True,
                provider="smtp",
                message_id=msg_id,
                sender=message.sender or self.get_sender(),
                recipients=recipients,
                status="sent",
            )
        except Exception as exc:
            raise EmailDeliveryError(f"SMTP delivery failed: {exc}") from exc
