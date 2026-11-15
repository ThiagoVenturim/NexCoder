"""Comprehensive offline tests for NexCoder email sending, connectors, approval, and audit."""

from __future__ import annotations

import base64
import json
from email import message_from_bytes
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from nexcoder_control.approval.tokens import ApprovalTokenManager
from nexcoder_control.email.config import (
    EmailSettings,
    GmailOAuthSettings,
    OutlookGraphSettings,
    SMTPSettings,
)
from nexcoder_control.email.connectors.gmail import GmailOAuthConnector
from nexcoder_control.email.connectors.outlook import OutlookGraphConnector
from nexcoder_control.email.connectors.smtp import SMTPConnector
from nexcoder_control.email.models import (
    EmailApprovalRequiredError,
    EmailAttachment,
    EmailDeliveryError,
    EmailMessage,
    EmailNotConfiguredError,
    EmailRateLimitExceededError,
)
from nexcoder_control.email.rate_limiter import EmailRateLimiter
from nexcoder_control.email.service import EmailService
from nexcoder_control.email.templates import EmailTemplateManager
from nexcoder_control.metering.audit import AppendOnlyAuditLog

# ---------------------------------------------------------------------------
# Gmail OAuth Connector Tests
# ---------------------------------------------------------------------------


def test_gmail_connector_unconfigured() -> None:
    connector = GmailOAuthConnector(settings=GmailOAuthSettings())
    assert not connector.is_configured()

    msg = EmailMessage(subject="Test", recipients=["lead@example.com"], body_text="Hello")
    with pytest.raises(EmailNotConfiguredError):
        connector.send(msg)


def test_gmail_connector_send_with_mock_transport() -> None:
    captured_requests: list[httpx.Request] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        if request.url.path == "/gmail/v1/users/me/messages/send":
            body = json.loads(request.content.decode("utf-8"))
            assert "raw" in body
            return httpx.Response(200, json={"id": "mock_gmail_msg_001", "threadId": "th_123"})
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    settings = GmailOAuthSettings(
        access_token="mock_access_token_12345",
        user_email="engineer@example.com",
    )
    connector = GmailOAuthConnector(settings=settings, http_client=client)
    assert connector.is_configured()

    att = EmailAttachment(
        filename="report.pdf",
        content=b"%PDF-1.4 sample pdf content",
        content_type="application/pdf",
    )
    msg = EmailMessage(
        subject="Sprint 1 Productivity Report",
        recipients=["manager@example.com"],
        cc=["lead@example.com"],
        body_html="<h1>Report</h1><p>Sprint 1 metrics attached.</p>",
        body_text="Report: Sprint 1 metrics attached.",
        attachments=[att],
    )

    result = connector.send(msg)

    assert result.success is True
    assert result.provider == "gmail"
    assert result.message_id == "mock_gmail_msg_001"
    assert len(captured_requests) == 1

    # Verify captured message payload
    req = captured_requests[0]
    assert req.headers["authorization"] == "Bearer mock_access_token_12345"
    raw_b64 = json.loads(req.content)["raw"]
    raw_mime_bytes = base64.urlsafe_b64decode(raw_b64.encode("ascii"))
    parsed_msg = message_from_bytes(raw_mime_bytes)

    assert parsed_msg["Subject"] == "Sprint 1 Productivity Report"
    assert "manager@example.com" in parsed_msg["To"]
    assert "lead@example.com" in parsed_msg["Cc"]

    # Verify attachment was encoded
    attachments = [part for part in parsed_msg.walk() if part.get_filename() == "report.pdf"]
    assert len(attachments) == 1
    assert attachments[0].get_payload(decode=True) == b"%PDF-1.4 sample pdf content"


def test_gmail_connector_oauth_token_refresh() -> None:
    token_refreshed = False

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_refreshed
        if request.url.path == "/token":
            token_refreshed = True
            return httpx.Response(200, json={"access_token": "refreshed_access_token_999"})
        if request.url.path == "/gmail/v1/users/me/messages/send":
            auth = request.headers.get("authorization")
            if auth == "Bearer refreshed_access_token_999":
                return httpx.Response(200, json={"id": "msg_refreshed_ok"})
            return httpx.Response(401, json={"error": "invalid_grant"})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    settings = GmailOAuthSettings(
        client_id="mock_client_id",
        client_secret="mock_client_secret",
        refresh_token="mock_refresh_token",
        user_email="engineer@example.com",
    )
    connector = GmailOAuthConnector(settings=settings, http_client=client)
    msg = EmailMessage(subject="Refreshed Test", recipients=["peer@example.com"], body_text="Hello")

    result = connector.send(msg)

    assert token_refreshed is True
    assert result.success is True
    assert result.message_id == "msg_refreshed_ok"


# ---------------------------------------------------------------------------
# Microsoft Graph / Outlook Connector Tests
# ---------------------------------------------------------------------------


def test_outlook_connector_unconfigured() -> None:
    connector = OutlookGraphConnector(settings=OutlookGraphSettings())
    assert not connector.is_configured()

    msg = EmailMessage(subject="Test", recipients=["lead@example.com"], body_text="Hello")
    with pytest.raises(EmailNotConfiguredError):
        connector.send(msg)


def test_outlook_connector_send_with_mock_transport() -> None:
    captured_payload: dict[str, Any] = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        if request.url.path == "/v1.0/me/sendMail":
            captured_payload = json.loads(request.content.decode("utf-8"))
            return httpx.Response(202, headers={"client-request-id": "req-guid-12345"})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    settings = OutlookGraphSettings(
        access_token="mock_graph_access_token",
        user_email="architect@example.com",
    )
    connector = OutlookGraphConnector(settings=settings, http_client=client)
    assert connector.is_configured()

    att = EmailAttachment(
        filename="proposal.docx",
        content=b"sample docx proposal content",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    msg = EmailMessage(
        subject="Architecture Proposal for Microservices",
        recipients=["cto@example.com"],
        cc=["vp@example.com"],
        body_html="<p>Please review the proposal.</p>",
        attachments=[att],
    )

    result = connector.send(msg)

    assert result.success is True
    assert result.provider == "outlook"
    assert result.message_id == "req-guid-12345"

    # Verify Microsoft Graph JSON structure
    assert "message" in captured_payload
    gmsg = captured_payload["message"]
    assert gmsg["subject"] == "Architecture Proposal for Microservices"
    assert gmsg["body"]["contentType"] == "HTML"
    assert gmsg["body"]["content"] == "<p>Please review the proposal.</p>"
    assert gmsg["toRecipients"][0]["emailAddress"]["address"] == "cto@example.com"
    assert gmsg["ccRecipients"][0]["emailAddress"]["address"] == "vp@example.com"

    # Verify attachment in Microsoft Graph format
    assert len(gmsg["attachments"]) == 1
    att_payload = gmsg["attachments"][0]
    assert att_payload["@odata.type"] == "#microsoft.graph.fileAttachment"
    assert att_payload["name"] == "proposal.docx"
    decoded = base64.b64decode(att_payload["contentBytes"])
    assert decoded == b"sample docx proposal content"


def test_outlook_connector_oauth_token_refresh() -> None:
    refreshed = False

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal refreshed
        if "/oauth2/v2.0/token" in request.url.path:
            refreshed = True
            return httpx.Response(200, json={"access_token": "graph_token_refreshed_555"})
        if request.url.path == "/v1.0/me/sendMail":
            assert request.headers.get("authorization") == "Bearer graph_token_refreshed_555"
            return httpx.Response(202, headers={"client-request-id": "req-refreshed-999"})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    settings = OutlookGraphSettings(
        client_id="mock_client_id",
        client_secret="mock_client_secret",
        refresh_token="mock_refresh_token",
        tenant_id="common",
    )
    connector = OutlookGraphConnector(settings=settings, http_client=client)
    msg = EmailMessage(subject="Graph Refresh Test", recipients=["eng@example.com"], body_text="Test")

    result = connector.send(msg)

    assert refreshed is True
    assert result.success is True
    assert result.message_id == "req-refreshed-999"


# ---------------------------------------------------------------------------
# Fallback SMTP Connector Tests
# ---------------------------------------------------------------------------


def test_smtp_connector_unconfigured() -> None:
    connector = SMTPConnector(settings=SMTPSettings())
    assert not connector.is_configured()

    msg = EmailMessage(subject="Test", recipients=["user@example.com"], body_text="Hello")
    with pytest.raises(EmailNotConfiguredError):
        connector.send(msg)


def test_smtp_connector_send_with_mock_client() -> None:
    mock_smtp_instance = MagicMock()
    connector = SMTPConnector(
        settings=SMTPSettings(
            host="smtp.example.com",
            port=587,
            username="smtp_user",
            password="smtp_password",
            use_tls=True,
            from_email="noreply@example.com",
        ),
        smtp_factory=lambda: mock_smtp_instance,
    )
    assert connector.is_configured()

    msg = EmailMessage(
        subject="SMTP Test Message",
        recipients=["dest@example.com"],
        body_text="Hello via SMTP",
    )
    result = connector.send(msg)

    assert result.success is True
    assert result.provider == "smtp"
    assert result.message_id.startswith("smtp_")
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("smtp_user", "smtp_password")
    mock_smtp_instance.send_message.assert_called_once()


def test_smtp_delivery_error_wrapping() -> None:
    mock_smtp_instance = MagicMock()
    mock_smtp_instance.send_message.side_effect = RuntimeError("SMTP connection timeout")

    connector = SMTPConnector(
        settings=SMTPSettings(host="smtp.example.com"),
        smtp_factory=lambda: mock_smtp_instance,
    )
    msg = EmailMessage(subject="Fail Test", recipients=["dest@example.com"], body_text="Hello")

    with pytest.raises(EmailDeliveryError) as exc_info:
        connector.send(msg)
    assert "SMTP connection timeout" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Email Service Governance, Approval, Rate Limits, and Audit Tests
# ---------------------------------------------------------------------------


def test_email_service_unconfigured_safe_degradation() -> None:
    """Without credentials, email service safely deactivates without crashing."""
    settings = EmailSettings()
    service = EmailService(settings=settings)
    assert not service.is_configured()

    msg = EmailMessage(subject="Test", recipients=["peer@example.com"], body_text="Hello")
    result = service.send_email(msg)

    assert result.success is False
    assert result.status == "disabled"
    assert "unconfigured" in (result.error_message or "").lower()


def test_email_service_requires_human_approval_fail_closed() -> None:
    """Every email dispatch requires human confirmation or a valid approval token."""
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"id": "msg_001"}))
    mock_client = httpx.Client(transport=mock_transport)

    settings = EmailSettings(
        require_human_approval=True,
        gmail=GmailOAuthSettings(access_token="mock_token", user_email="user@example.com"),
    )
    gmail_conn = GmailOAuthConnector(settings=settings.gmail, http_client=mock_client)
    audit_log = AppendOnlyAuditLog()
    token_mgr = ApprovalTokenManager()

    service = EmailService(
        settings=settings,
        audit_log=audit_log,
        token_manager=token_mgr,
        gmail_connector=gmail_conn,
    )

    msg = EmailMessage(
        subject="Important Client Proposal",
        recipients=["client@enterprise.com"],
        body_text="Proposal terms attached.",
    )

    # 1. Dispatch without approval token or confirmation must raise EmailApprovalRequiredError
    with pytest.raises(EmailApprovalRequiredError) as exc_info:
        service.send_email(msg, confirmed=False)

    assert exc_info.value.token_id is not None
    assert "preview" in dir(exc_info.value)
    preview = exc_info.value.preview
    assert preview["subject"] == "Important Client Proposal"
    assert "client@enterprise.com" in preview["recipients"]

    # Verify audit event logged as blocked
    blocked_events = [e for e in audit_log.query() if e.event_type == "email_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0].details["reason"] == "human_approval_required"


def test_email_service_send_with_valid_approval_token() -> None:
    """Valid human approval token permits send, consumes token, and logs audit."""
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"id": "msg_approved_100"}))
    mock_client = httpx.Client(transport=mock_transport)

    settings = EmailSettings(
        require_human_approval=True,
        gmail=GmailOAuthSettings(access_token="mock_token", user_email="engineer@example.com"),
    )
    gmail_conn = GmailOAuthConnector(settings=settings.gmail, http_client=mock_client)
    audit_log = AppendOnlyAuditLog()
    token_mgr = ApprovalTokenManager()

    service = EmailService(
        settings=settings,
        audit_log=audit_log,
        token_manager=token_mgr,
        gmail_connector=gmail_conn,
    )

    msg = EmailMessage(
        subject="Weekly Report",
        recipients=["team@example.com"],
        body_text="Here is the weekly update.",
    )

    # 1. Human requests pre-flight approval token
    token_id, raw_secret, preview = service.request_approval(msg, approver="lead_engineer")
    assert token_id.startswith("apr_")
    assert preview["subject"] == "Weekly Report"

    # 2. Dispatch with the raw approval secret
    res = service.send_email(msg, approval_token=raw_secret)
    assert res.success is True
    assert res.status == "sent"
    assert res.message_id == "msg_approved_100"
    assert res.audit_event_id is not None

    # 3. Cryptographically verify audit log
    is_valid, msg_verify = audit_log.verify_integrity()
    assert is_valid is True
    dispatch_events = [e for e in audit_log.query() if e.event_type == "email_dispatch"]
    assert len(dispatch_events) >= 1
    assert dispatch_events[-1].details["message_id"] == "msg_approved_100"

    # 4. Token cannot be reused (single-use enforcement)
    with pytest.raises(Exception):
        service.send_email(msg, approval_token=raw_secret)


def test_email_service_explicit_confirmation() -> None:
    """Passing confirmed=True bypasses token check when human has verified in UI/CLI."""
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"id": "msg_confirmed_200"}))
    mock_client = httpx.Client(transport=mock_transport)

    settings = EmailSettings(
        require_human_approval=True,
        gmail=GmailOAuthSettings(access_token="mock_token", user_email="lead@example.com"),
    )
    gmail_conn = GmailOAuthConnector(settings=settings.gmail, http_client=mock_client)

    service = EmailService(
        settings=settings,
        gmail_connector=gmail_conn,
    )

    msg = EmailMessage(
        subject="Quick Update",
        recipients=["dev@example.com"],
        body_text="Sync at 10am.",
    )

    res = service.send_email(msg, confirmed=True)
    assert res.success is True
    assert res.message_id == "msg_confirmed_200"


def test_email_service_anti_bulk_limit() -> None:
    """Service blocks automated bulk mailing exceeding recipient limit."""
    settings = EmailSettings(
        max_recipients_per_send=3,
        gmail=GmailOAuthSettings(access_token="mock_token", user_email="lead@example.com"),
    )
    service = EmailService(settings=settings)

    recipients = ["u1@ex.org", "u2@ex.org", "u3@ex.org", "u4@ex.org"]
    msg = EmailMessage(subject="Mass Email", recipients=recipients, body_text="Promo")

    with pytest.raises(ValueError) as exc:
        service.send_email(msg, confirmed=True)
    assert "exceeds maximum allowed" in str(exc.value)


def test_email_service_platform_rate_limiting() -> None:
    """EmailRateLimiter throttles requests exceeding provider RPM."""
    limiter = EmailRateLimiter(limits_rpm={"gmail": 2}, window_seconds=60.0)

    # 2 requests allowed
    limiter.enforce("gmail")
    limiter.enforce("gmail")

    # 3rd request in same minute must raise EmailRateLimitExceededError
    with pytest.raises(EmailRateLimitExceededError) as exc:
        limiter.enforce("gmail")
    assert "Rate limit exceeded" in str(exc.value)
    assert exc.value.provider == "gmail"

    # Reset clears throttling
    limiter.reset("gmail")
    limiter.enforce("gmail")


def test_email_service_reusable_templates() -> None:
    """Test rendering and dispatching reusable report and proposal templates."""
    mgr = EmailTemplateManager()

    # 1. Test Report Delivery Template
    subj, html_b, text_b = mgr.render(
        "report_delivery",
        {
            "project_name": "NexCoder Core",
            "report_type": "Security Posture Report",
            "period": "2026-Q4",
            "summary": "Zero critical CVEs found across all 13 modules.",
            "metrics_summary": "Test coverage: 94.2%, Gates: PASSED.",
            "recipient_name": "CTO",
            "sender_name": "Security Bot",
        },
    )
    assert "NexCoder Core - Security Posture Report (2026-Q4)" in subj
    assert "Zero critical CVEs" in html_b
    assert "Zero critical CVEs" in text_b
    assert "CTO" in html_b

    # 2. Test Proposal Template
    p_subj, p_html, p_text = mgr.render(
        "proposal_submission",
        {
            "proposal_title": "Event-Driven Microservices RFC",
            "verdict": "APPROVED",
            "score": "9.2/10",
            "author": "Architecture Team",
            "executive_summary": "Approved by unanimous 6-member jury.",
            "recipient_name": "Engineering Staff",
            "sender_name": "NexCoder Jury",
        },
    )
    assert "Event-Driven Microservices RFC" in p_subj
    assert "APPROVED" in p_html
    assert "Approved by unanimous" in p_text


def test_email_service_send_test_email_with_attachment() -> None:
    """Service send_test_email dispatches test message with an attachment."""
    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"id": "msg_test_001"}))
    mock_client = httpx.Client(transport=mock_transport)

    settings = EmailSettings(
        gmail=GmailOAuthSettings(access_token="mock_token", user_email="lead@example.com"),
    )
    gmail_conn = GmailOAuthConnector(settings=settings.gmail, http_client=mock_client)

    service = EmailService(settings=settings, gmail_connector=gmail_conn)

    res = service.send_test_email(
        recipient="test-receiver@example.com",
        provider="gmail",
        attachment_name="artifact.txt",
        attachment_content=b"Sample automated test payload",
        confirmed=True,
    )

    assert res.success is True
    assert res.provider == "gmail"
    assert res.message_id == "msg_test_001"
    assert "test-receiver@example.com" in res.recipients
    assert res.preview_data is not None
    assert res.preview_data["attachments_count"] == 1


def test_email_service_fallback_to_smtp_when_gmail_unconfigured() -> None:
    """When primary provider is unconfigured, auto-fallback to operational SMTP."""
    mock_smtp_instance = MagicMock()
    smtp_conn = SMTPConnector(
        settings=SMTPSettings(host="smtp.example.com", from_email="system@example.com"),
        smtp_factory=lambda: mock_smtp_instance,
    )

    # Gmail unconfigured, SMTP configured
    settings = EmailSettings(
        default_provider="auto",
        gmail=GmailOAuthSettings(),
        smtp=SMTPSettings(host="smtp.example.com", from_email="system@example.com"),
    )

    service = EmailService(
        settings=settings,
        smtp_connector=smtp_conn,
    )

    msg = EmailMessage(
        subject="Fallback Test",
        recipients=["target@example.com"],
        body_text="Delivered via SMTP fallback.",
    )

    res = service.send_email(msg, confirmed=True)
    assert res.success is True
    assert res.provider == "smtp"
    mock_smtp_instance.send_message.assert_called_once()
