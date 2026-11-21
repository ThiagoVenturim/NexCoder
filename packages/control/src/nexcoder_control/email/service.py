"""Unified Email service with connector routing, approval governance, rate limits, and audit."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nexcoder_control.approval.tokens import ApprovalTokenManager
from nexcoder_control.email.config import EmailSettings
from nexcoder_control.email.connectors.base import BaseEmailConnector
from nexcoder_control.email.connectors.gmail import GmailOAuthConnector
from nexcoder_control.email.connectors.outlook import OutlookGraphConnector
from nexcoder_control.email.connectors.smtp import SMTPConnector
from nexcoder_control.email.models import (
    EmailApprovalRequiredError,
    EmailAttachment,
    EmailMessage,
    EmailNotConfiguredError,
    EmailSendResult,
)
from nexcoder_control.email.rate_limiter import EmailRateLimiter
from nexcoder_control.email.templates import EmailTemplateManager
from nexcoder_control.metering.audit import AppendOnlyAuditLog


class EmailService:
    """Enterprise email dispatcher orchestrating OAuth connectors, human approval, and audit trails."""

    def __init__(
        self,
        settings: EmailSettings | None = None,
        audit_log: AppendOnlyAuditLog | None = None,
        token_manager: ApprovalTokenManager | None = None,
        rate_limiter: EmailRateLimiter | None = None,
        template_manager: EmailTemplateManager | None = None,
        gmail_connector: GmailOAuthConnector | None = None,
        outlook_connector: OutlookGraphConnector | None = None,
        smtp_connector: SMTPConnector | None = None,
    ) -> None:
        self.settings = settings or EmailSettings.from_env()
        self.audit_log = audit_log or AppendOnlyAuditLog()
        self.token_manager = token_manager or ApprovalTokenManager(default_ttl_minutes=15)
        self.rate_limiter = rate_limiter or EmailRateLimiter(limits_rpm=self.settings.rate_limits_rpm)
        self.template_manager = template_manager or EmailTemplateManager()

        self._connectors: dict[str, BaseEmailConnector] = {}

        if gmail_connector is not None:
            self._connectors["gmail"] = gmail_connector
        elif self.settings.gmail.is_configured():
            self._connectors["gmail"] = GmailOAuthConnector(settings=self.settings.gmail)

        if outlook_connector is not None:
            self._connectors["outlook"] = outlook_connector
        elif self.settings.outlook.is_configured():
            self._connectors["outlook"] = OutlookGraphConnector(settings=self.settings.outlook)

        if smtp_connector is not None:
            self._connectors["smtp"] = smtp_connector
        elif self.settings.smtp.is_configured():
            self._connectors["smtp"] = SMTPConnector(settings=self.settings.smtp)

    def is_configured(self) -> bool:
        """Return True if at least one sending provider is operational."""
        return len(self._connectors) > 0 or self.settings.is_configured()

    def is_provider_configured(self, provider: str) -> bool:
        """Check if specific provider is configured and available."""
        norm = self._normalize_provider(provider)
        if norm in self._connectors:
            return self._connectors[norm].is_configured()
        return self.settings.is_provider_configured(norm)

    def get_available_providers(self) -> list[str]:
        """List all active and configured provider names."""
        configured = []
        for name in ("gmail", "outlook", "smtp"):
            if self.is_provider_configured(name):
                configured.append(name)
        return configured

    def _normalize_provider(self, provider: str) -> str:
        clean = provider.strip().lower()
        if clean in ("outlook", "graph", "m365", "office365"):
            return "outlook"
        if clean in ("gmail", "google"):
            return "gmail"
        if clean in ("smtp", "generic_smtp"):
            return "smtp"
        return clean

    def _get_or_create_connector(self, provider: str) -> BaseEmailConnector:
        norm = self._normalize_provider(provider)
        if norm in self._connectors:
            return self._connectors[norm]

        if norm == "gmail":
            conn = GmailOAuthConnector(settings=self.settings.gmail)
            self._connectors[norm] = conn
            return conn
        if norm == "outlook":
            conn = OutlookGraphConnector(settings=self.settings.outlook)
            self._connectors[norm] = conn
            return conn
        if norm == "smtp":
            conn = SMTPConnector(settings=self.settings.smtp)
            self._connectors[norm] = conn
            return conn

        raise EmailNotConfiguredError(f"Unsupported email provider '{provider}'")

    def _build_preview(self, message: EmailMessage, provider: str) -> dict[str, Any]:
        """Construct deterministic preview dictionary for human inspection."""
        attachments_info = [
            {
                "filename": att.filename,
                "content_type": att.get_content_type(),
                "size_bytes": att.size_bytes(),
            }
            for att in message.attachments
        ]
        body_text_preview = message.get_plain_text()[:300]
        return {
            "provider": provider,
            "sender": message.sender or self.settings.gmail.user_email or self.settings.outlook.user_email or "user",
            "recipients": message.normalized_recipients(),
            "cc": message.normalized_cc(),
            "bcc": message.normalized_bcc(),
            "subject": message.subject,
            "body_preview": body_text_preview,
            "has_html": bool(message.body_html),
            "attachments_count": len(message.attachments),
            "attachments": attachments_info,
        }

    def request_approval(
        self,
        message: EmailMessage,
        provider: str | None = None,
        approver: str = "engineer",
    ) -> tuple[str, str, dict[str, Any]]:
        """Pre-flight approval request: issues single-use token and logs audit event.

        Returns (token_id, raw_secret, preview_data).
        """
        chosen_provider = self._normalize_provider(provider or self.settings.get_preferred_provider())
        preview = self._build_preview(message, chosen_provider)
        target_resource = f"email:{';'.join(message.normalized_recipients())}:{message.subject[:40]}"

        record, raw_secret = self.token_manager.issue_token(
            action_name="email:send",
            target_resource=target_resource,
            approver=approver,
            metadata=preview,
        )

        self.audit_log.record_event(
            event_type="email_approval_requested",
            actor=approver,
            action="request_approval",
            resource=target_resource,
            severity="info",
            details={
                "token_id": record.token_id,
                "provider": chosen_provider,
                "recipients": message.normalized_recipients(),
                "subject": message.subject,
            },
        )

        return record.token_id, raw_secret, preview

    def send_email(
        self,
        message: EmailMessage,
        provider: str | None = None,
        approval_token: str | None = None,
        confirmed: bool = False,
        dry_run: bool = False,
        actor: str | None = None,
    ) -> EmailSendResult:
        """Send email with human approval enforcement, rate limits, and audit tracking."""
        # 1. Graceful check: without credentials, deactivate without crashing
        if not self.is_configured():
            now = datetime.now(UTC)
            return EmailSendResult(
                success=False,
                provider=provider or "none",
                sender="",
                recipients=message.normalized_recipients(),
                timestamp=now,
                status="disabled",
                error_message="Email sending is unconfigured. Set Gmail, Outlook, or SMTP credentials in .env.",
            )

        # 2. Recipient validation and anti-bulk enforcement
        recipients = message.normalized_recipients()
        if not recipients:
            raise ValueError("Email message must specify at least one recipient")

        if len(recipients) > self.settings.max_recipients_per_send:
            raise ValueError(
                f"Recipient count ({len(recipients)}) exceeds maximum allowed "
                f"({self.settings.max_recipients_per_send}) to prevent automated bulk distribution"
            )

        # 3. Apply template if requested
        if message.template_name:
            subj, html_b, text_b = self.template_manager.render(message.template_name, message.template_vars)
            if not message.subject or message.subject == "Default Subject":
                message.subject = subj
            if not message.body_html:
                message.body_html = html_b
            if not message.body_text:
                message.body_text = text_b

        # 4. Resolve provider (auto fallback to SMTP if requested provider unconfigured)
        target_provider = self._normalize_provider(provider or self.settings.get_preferred_provider())
        if not self.is_provider_configured(target_provider):
            # Fallback strategy: try available configured providers
            available = self.get_available_providers()
            if available:
                target_provider = available[0]
            else:
                return EmailSendResult(
                    success=False,
                    provider=target_provider,
                    sender="",
                    recipients=recipients,
                    status="disabled",
                    error_message=(
                        f"Requested provider '{target_provider}' is not configured and no fallback available."
                    ),
                )

        connector = self._get_or_create_connector(target_provider)
        sender_email = message.sender or connector.get_sender()
        active_actor = actor or sender_email

        # 5. Enforce human confirmation before every send
        target_resource = f"email:{';'.join(recipients)}:{message.subject[:40]}"
        if self.settings.require_human_approval and not confirmed:
            if not approval_token:
                # Block send and issue token requirement
                token_id, raw_secret, preview = self.request_approval(
                    message=message, provider=target_provider, approver=active_actor
                )
                self.audit_log.record_event(
                    event_type="email_blocked",
                    actor=active_actor,
                    action="block_unapproved_send",
                    resource=target_resource,
                    severity="warning",
                    details={"reason": "human_approval_required", "token_id": token_id},
                )
                raise EmailApprovalRequiredError(
                    message="Email dispatch requires human approval token or explicit confirmation before sending",
                    preview=preview,
                    token_id=token_id,
                )

            # Consume token
            self.token_manager.verify_and_consume(
                raw_token=approval_token,
                action_name="email:send",
                target_resource=target_resource,
                dry_run=dry_run,
            )

        # 6. Enforce platform rate limits
        self.rate_limiter.enforce(target_provider)

        # 7. Dry run handling
        preview_data = self._build_preview(message, target_provider)
        if dry_run:
            evt = self.audit_log.record_event(
                event_type="email_dispatch",
                actor=active_actor,
                action="dry_run",
                resource=target_resource,
                severity="info",
                details={
                    "provider": target_provider,
                    "sender": sender_email,
                    "recipients": recipients,
                    "subject": message.subject,
                    "dry_run": True,
                },
            )
            return EmailSendResult(
                success=True,
                provider=target_provider,
                message_id="dry_run_simulation",
                sender=sender_email,
                recipients=recipients,
                audit_event_id=evt.event_id,
                status="dry_run",
                preview_data=preview_data,
            )

        # 8. Dispatch via selected connector
        try:
            result = connector.send(message)
            result.preview_data = preview_data

            # 9. Audit event on control plane
            evt = self.audit_log.record_event(
                event_type="email_dispatch",
                actor=active_actor,
                action="send",
                resource=target_resource,
                severity="info",
                details={
                    "provider": target_provider,
                    "message_id": result.message_id,
                    "sender": result.sender,
                    "recipients": result.recipients,
                    "subject": message.subject,
                    "attachments_count": len(message.attachments),
                    "status": "sent",
                },
            )
            result.audit_event_id = evt.event_id
            return result
        except Exception as exc:
            self.audit_log.record_event(
                event_type="email_dispatch",
                actor=active_actor,
                action="send_failed",
                resource=target_resource,
                severity="error",
                details={
                    "provider": target_provider,
                    "sender": sender_email,
                    "recipients": recipients,
                    "subject": message.subject,
                    "error": str(exc),
                },
            )
            raise

    def send_test_email(
        self,
        recipient: str,
        provider: str = "gmail",
        attachment_name: str = "test_artifact.txt",
        attachment_content: bytes = b"NexCoder automated email test artifact.",
        confirmed: bool = True,
    ) -> EmailSendResult:
        """Send automated test verification email with an attachment."""
        att = EmailAttachment(
            filename=attachment_name,
            content=attachment_content,
            content_type="text/plain",
        )
        msg = EmailMessage(
            subject=f"[NexCoder Test] Connectivity check for {provider}",
            recipients=[recipient],
            body_html=f"<p>This is an automated connectivity test sent via <strong>{provider}</strong>.</p>",
            body_text=f"This is an automated connectivity test sent via {provider}.",
            attachments=[att],
        )
        return self.send_email(
            message=msg,
            provider=provider,
            confirmed=confirmed,
        )
