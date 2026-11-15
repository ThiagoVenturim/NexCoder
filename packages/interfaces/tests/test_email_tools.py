"""Tests for email tools and CLI interfaces in nexcoder-interfaces."""

from __future__ import annotations

from unittest.mock import patch

from nexcoder_control.email import EmailSendResult
from nexcoder_interfaces.cli.main import app
from nexcoder_interfaces.tools import TOOL_DEFINITIONS
from nexcoder_interfaces.tools.email import send_email
from typer.testing import CliRunner

runner = CliRunner()


def test_tool_definitions_has_send_email() -> None:
    assert "send_email" in TOOL_DEFINITIONS
    tool = TOOL_DEFINITIONS["send_email"]
    assert tool.name == "send_email"
    assert tool.module == "control"
    assert "recipients" in tool.parameters["properties"]
    assert "subject" in tool.parameters["properties"]
    assert "attachments" in tool.parameters["properties"]
    assert tool.is_available is True


def test_send_email_tool_dry_run() -> None:
    result = send_email(
        recipients=["dev@example.com"],
        subject="Sprint Review",
        body_text="Review at 2pm.",
        confirmed=True,
        dry_run=True,
    )
    # If unconfigured, returns disabled; if configured or dry_run, returns clean status
    assert result["status"] in ("disabled", "dry_run", "success")


def test_send_email_tool_requires_approval() -> None:
    from nexcoder_control.email.config import EmailSettings, GmailOAuthSettings

    mock_settings = EmailSettings(
        require_human_approval=True,
        gmail=GmailOAuthSettings(access_token="mock_token", user_email="lead@example.com"),
    )
    with patch("nexcoder_control.email.service.EmailSettings.from_env", return_value=mock_settings):
        result = send_email(
            recipients=["client@example.com"],
            subject="Pricing Proposal",
            body_text="Rates attached.",
            confirmed=False,
            approval_token=None,
        )
        assert result["status"] == "approval_required"
        assert "token_id" in result
        assert result["token_id"].startswith("apr_")
        assert "preview" in result


def test_cli_email_templates() -> None:
    result = runner.invoke(app, ["email", "templates"])
    assert result.exit_code == 0
    assert "report_delivery" in result.stdout
    assert "proposal_submission" in result.stdout


def test_cli_email_send_dry_run() -> None:
    mock_res = EmailSendResult(
        success=True,
        provider="gmail",
        message_id="cli_mock_msg",
        sender="user@example.com",
        recipients=["team@example.com"],
        status="dry_run",
    )
    with patch("nexcoder_control.email.service.EmailService.send_email", return_value=mock_res):
        result = runner.invoke(
            app,
            [
                "email",
                "send",
                "--to",
                "team@example.com",
                "--subject",
                "CLI Test",
                "--body",
                "Testing CLI send",
                "--dry-run",
                "--confirm",
            ],
        )
        assert result.exit_code == 0
        assert "cli_mock_msg" in result.stdout
