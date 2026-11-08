"""Tests for faccoder-control CLI interface."""

from __future__ import annotations

from unittest.mock import patch

from faccoder_control.cli import _audit_log, _machine_mgr, app, main
from typer.testing import CliRunner

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Control plane management CLI for faccoder." in result.output
    assert "status" in result.output
    assert "keys" in result.output
    assert "machines" in result.output
    assert "audit" in result.output


def test_cli_subcommand_helps() -> None:
    for sub in ["keys", "machines", "audit"]:
        result = runner.invoke(app, [sub, "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output


def test_cli_status() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "faccoder Control Plane Status" in result.output
    assert "Total Spend (USD)" in result.output
    assert "Active API Keys" in result.output


def test_cli_keys_create_and_list() -> None:
    # Test keys create
    result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "dev-key",
            "--owner",
            "ci-team",
            "--usd-cap",
            "50.0",
            "--rpm",
            "120",
            "--scopes",
            "tools:execute,metrics:read",
        ],
    )
    assert result.exit_code == 0
    assert "API Key Created Successfully" in result.output
    assert "Key ID:" in result.output
    assert "Secret Key" in result.output

    # Test keys list
    result_list = runner.invoke(app, ["keys", "list"])
    assert result_list.exit_code == 0
    assert "Configured API Keys" in result_list.output
    assert "dev-key" in result_list.output
    assert "ci-team" in result_list.output


def test_cli_keys_create_missing_name() -> None:
    result = runner.invoke(app, ["keys", "create"])
    assert result.exit_code != 0


def test_cli_machines_list_and_approve() -> None:
    # List machines initially
    result_list = runner.invoke(app, ["machines", "list"])
    assert result_list.exit_code == 0
    assert "CLI Workstations" in result_list.output

    # Register machine in manager
    m = _machine_mgr.register_machine(
        machine_id="worker-node-42",
        hostname="node42.local",
        platform="win32",
        registered_by="devops",
    )
    assert m.status == "pending"

    # Approve machine
    result_app = runner.invoke(
        app,
        ["machines", "approve", "worker-node-42", "--approver", "security-lead"],
    )
    assert result_app.exit_code == 0
    assert "approved for execution access" in result_app.output

    # Approve nonexistent machine -> code 1
    result_err = runner.invoke(app, ["machines", "approve", "nonexistent-id"])
    assert result_err.exit_code == 1
    assert "not found" in result_err.output


def test_cli_audit_verify_success() -> None:
    result = runner.invoke(app, ["audit", "verify"])
    assert result.exit_code == 0
    assert "Ledger Verified:" in result.output


def test_cli_audit_verify_tampered() -> None:
    with patch.object(_audit_log, "verify_integrity", return_value=(False, "tampered hash sequence")):
        result = runner.invoke(app, ["audit", "verify"])
        assert result.exit_code == 1
        assert "INTEGRITY BREACH:" in result.output


def test_cli_main_entrypoint() -> None:
    with patch("faccoder_control.cli.app") as mock_app:
        main()
        mock_app.assert_called_once()
