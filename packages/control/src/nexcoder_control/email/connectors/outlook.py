"""Microsoft Graph API connector for Outlook and Microsoft 365."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from nexcoder_control.email.config import OutlookGraphSettings
from nexcoder_control.email.connectors.base import BaseEmailConnector
from nexcoder_control.email.models import (
    EmailDeliveryError,
    EmailMessage,
    EmailNotConfiguredError,
    EmailSendResult,
)


class OutlookGraphConnector(BaseEmailConnector):
    """Dispatches outgoing email via Microsoft Graph API (/v1.0/me/sendMail)."""

    provider_name = "outlook"
    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        settings: OutlookGraphSettings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or OutlookGraphSettings()
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

    def _token_endpoint(self) -> str:
        tenant = self.settings.tenant_id or "common"
        return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    def _refresh_access_token(self, client: httpx.Client) -> str:
        """Exchange OAuth2 refresh token for Graph access token."""
        if not (self.settings.client_id and self.settings.client_secret and self.settings.refresh_token):
            raise EmailNotConfiguredError("Missing Outlook OAuth client_id, client_secret, or refresh_token")

        payload = {
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
            "refresh_token": self.settings.refresh_token,
            "grant_type": "refresh_token",
            "scope": "https://graph.microsoft.com/.default offline_access",
        }

        resp = client.post(self._token_endpoint(), data=payload)
        if resp.status_code != 200:
            raise EmailDeliveryError(
                f"Failed to refresh Outlook OAuth token (HTTP {resp.status_code}): {resp.text}"
            )

        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise EmailDeliveryError("Outlook token refresh response missing access_token")

        self._cached_access_token = str(token)
        return self._cached_access_token

    def _get_valid_token(self, client: httpx.Client) -> str:
        if self._cached_access_token:
            return self._cached_access_token
        return self._refresh_access_token(client)

    def build_graph_payload(self, message: EmailMessage) -> dict[str, Any]:
        """Construct Microsoft Graph sendMail JSON payload."""
        to_recipients = [{"emailAddress": {"address": r}} for r in message.normalized_recipients()]
        cc_recipients = [{"emailAddress": {"address": r}} for r in message.normalized_cc()]
        bcc_recipients = [{"emailAddress": {"address": r}} for r in message.normalized_bcc()]

        content_type = "HTML" if message.body_html else "Text"
        content_body = message.body_html if message.body_html else message.get_plain_text()

        attachments_payload: list[dict[str, Any]] = []
        for att in message.attachments:
            attachments_payload.append(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": att.filename,
                    "contentType": att.get_content_type(),
                    "contentBytes": att.to_base64(),
                }
            )

        graph_msg: dict[str, Any] = {
            "subject": message.subject,
            "body": {
                "contentType": content_type,
                "content": content_body,
            },
            "toRecipients": to_recipients,
            "saveToSentItems": "true",
        }

        if cc_recipients:
            graph_msg["ccRecipients"] = cc_recipients
        if bcc_recipients:
            graph_msg["bccRecipients"] = bcc_recipients
        if attachments_payload:
            graph_msg["attachments"] = attachments_payload

        return {"message": graph_msg, "saveToSentItems": True}

    def send(self, message: EmailMessage) -> EmailSendResult:
        if not self.is_configured():
            raise EmailNotConfiguredError("Outlook Graph connector is not configured with required credentials")

        recipients = message.normalized_recipients()
        if not recipients:
            raise ValueError("Message must have at least one recipient")

        payload = self.build_graph_payload(message)
        client = self._get_client()
        owns_client = self._http_client is None

        send_url = f"{self.GRAPH_BASE_URL}/me/sendMail"

        try:
            token = self._get_valid_token(client)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            resp = client.post(send_url, headers=headers, json=payload)

            # If 401 and refresh token available, refresh once and retry
            if resp.status_code == 401 and self.settings.refresh_token:
                token = self._refresh_access_token(client)
                headers["Authorization"] = f"Bearer {token}"
                resp = client.post(send_url, headers=headers, json=payload)

            # Microsoft Graph sendMail returns 202 Accepted on success
            if resp.status_code not in (200, 201, 202):
                raise EmailDeliveryError(
                    f"Microsoft Graph rejected sendMail (HTTP {resp.status_code}): {resp.text}"
                )

            # Graph sendMail does not return a message ID in body; generate correlation ID
            corr_id = resp.headers.get("client-request-id") or f"graph_{uuid.uuid4().hex[:12]}"

            return EmailSendResult(
                success=True,
                provider="outlook",
                message_id=str(corr_id),
                sender=message.sender or self.get_sender(),
                recipients=recipients,
                status="sent",
            )
        finally:
            if owns_client:
                client.close()
