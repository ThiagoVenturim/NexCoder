"""Agent and tool interface for dispatching emails through nexcoder-control."""

from __future__ import annotations

from typing import Any


def send_email(
    recipients: list[str],
    subject: str,
    body_text: str | None = None,
    body_html: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
    template_name: str | None = None,
    template_vars: dict[str, Any] | None = None,
    provider: str | None = None,
    approval_token: str | None = None,
    confirmed: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Send an email from user account with human approval and control plane audit tracking."""
    try:
        from nexcoder_control.email import (
            EmailApprovalRequiredError,
            EmailAttachment,
            EmailMessage,
            EmailNotConfiguredError,
            EmailRateLimitExceededError,
            EmailService,
        )
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"nexcoder-control email module not available: {exc}",
        }

    attachment_objs = []
    if attachments:
        for att in attachments:
            attachment_objs.append(
                EmailAttachment(
                    filename=att.get("filename", "attachment.bin"),
                    content=att.get("content"),
                    file_path=att.get("file_path"),
                    content_type=att.get("content_type"),
                )
            )

    msg = EmailMessage(
        subject=subject,
        recipients=recipients,
        body_text=body_text,
        body_html=body_html,
        attachments=attachment_objs,
        template_name=template_name,
        template_vars=template_vars or {},
    )

    service = EmailService()
    try:
        res = service.send_email(
            message=msg,
            provider=provider,
            approval_token=approval_token,
            confirmed=confirmed,
            dry_run=dry_run,
        )
        return {
            "status": "success" if res.success else res.status,
            "provider": res.provider,
            "message_id": res.message_id,
            "sender": res.sender,
            "recipients": res.recipients,
            "audit_event_id": res.audit_event_id,
            "error_message": res.error_message,
            "preview": res.preview_data,
        }
    except EmailApprovalRequiredError as exc:
        return {
            "status": "approval_required",
            "message": str(exc),
            "token_id": exc.token_id,
            "preview": exc.preview,
        }
    except EmailRateLimitExceededError as exc:
        return {
            "status": "rate_limited",
            "message": str(exc),
            "provider": exc.provider,
            "retry_after_seconds": exc.retry_after_seconds,
        }
    except EmailNotConfiguredError as exc:
        return {
            "status": "disabled",
            "message": str(exc),
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
        }
