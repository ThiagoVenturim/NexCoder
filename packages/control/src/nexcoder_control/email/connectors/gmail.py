"""Google Gmail API connector using OAuth2 user account authentication."""

from __future__ import annotations

import base64
from email.message import EmailMessage as PyEmailMessage
from typing import Any

import httpx

from nexcoder_control.email.config import GmailOAuthSettings
from nexcoder_control.email.connectors.base import BaseEmailConnector
from nexcoder_control.email.models import (
    EmailDeliveryError,
    EmailMessage,
    EmailNotConfiguredError,
    EmailSendResult,
)


class GmailOAuthConnector(BaseEmailConnector):
    """Dispatches outgoing email via the official Google Gmail REST API v1."""

    provider_name = "gmail"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    SEND_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

    def __init__(
        self,
        settings: GmailOAuthSettings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or GmailOAuthSettings()
        self._http_client = http_client
        self._cached_access_token: str | None = self.settings.access_token

    def is_configured(self) -> bool:
        return self.settings.is_configured()

    def get_sender(self) -> str:
        return self.settings.user_email or "me"

    def _get_client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        return httpx.Client(timeout=30.0)

    def _refresh_access_token(self, client: httpx.Client) -> str:
        """Exchange OAuth2 refresh token for short-lived access token."""
        if not (self.settings.client_id and self.settings.client_secret and self.settings.refresh_token):
            raise EmailNotConfiguredError("Missing Gmail OAuth client_id, client_secret, or refresh_token")

        payload = {
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
            "refresh_token": self.settings.refresh_token,
            "grant_type": "refresh_token",
        }

        resp = client.post(self.TOKEN_ENDPOINT, data=payload)
        if resp.status_code != 200:
            raise EmailDeliveryError(
                f"Failed to refresh Gmail OAuth token (HTTP {resp.status_code}): {resp.text}"
            )

        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise EmailDeliveryError("Gmail token refresh response missing access_token")

        self._cached_access_token = str(token)
        return self._cached_access_token

    def _get_valid_token(self, client: httpx.Client) -> str:
        if self._cached_access_token:
            return self._cached_access_token
        return self._refresh_access_token(client)

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

    def send(self, message: EmailMessage) -> EmailSendResult:
        if not self.is_configured():
            raise EmailNotConfiguredError("Gmail connector is not configured with required credentials")

        recipients = message.normalized_recipients()
        if not recipients:
            raise ValueError("Message must have at least one recipient")

        mime_msg = self.build_mime_message(message)
        raw_bytes = mime_msg.as_bytes()
        raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("ascii")

        client = self._get_client()
        owns_client = self._http_client is None

        try:
            token = self._get_valid_token(client)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            body = {"raw": raw_b64}

            resp = client.post(self.SEND_ENDPOINT, headers=headers, json=body)

            # If 401 and we have refresh credentials, attempt refresh once
            if resp.status_code == 401 and self.settings.refresh_token:
                token = self._refresh_access_token(client)
                headers["Authorization"] = f"Bearer {token}"
                resp = client.post(self.SEND_ENDPOINT, headers=headers, json=body)

            if resp.status_code not in (200, 201, 202):
                raise EmailDeliveryError(
                    f"Gmail API rejected message (HTTP {resp.status_code}): {resp.text}"
                )

            data: dict[str, Any] = resp.json() if resp.content else {}
            msg_id = data.get("id") or f"gmail_{data.get('threadId', 'ok')}"

            return EmailSendResult(
                success=True,
                provider="gmail",
                message_id=str(msg_id),
                sender=message.sender or self.get_sender(),
                recipients=recipients,
                status="sent",
            )
        finally:
            if owns_client:
                client.close()
