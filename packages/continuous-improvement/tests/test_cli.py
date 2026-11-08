"""Tests for faccoder continuous improvement CLI interface."""

from __future__ import annotations

from unittest.mock import patch

from faccoder_continuous_improvement.cli import app, main
from faccoder_continuous_improvement.scheduler.cron import CronJob
from typer.testing import CliRunner

runner = CliRunner()


def test_ci_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Run all due continuous improvement jobs." in result.output
    assert "--dry-run" in result.output


def test_ci_cli_run_due_no_jobs_default() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Found 0 due jobs." in result.output


def test_ci_cli_run_due_dry_run() -> None:
    result = runner.invoke(app, ["--dry-run"])
    assert result.exit_code == 0
    assert "Found 0 due jobs." in result.output


def test_ci_cli_run_due_with_jobs_executed() -> None:
    fake_job = CronJob(name="mock_job", schedule="@daily", task_type="research")
    with (
        patch(
            "faccoder_continuous_improvement.scheduler.cron.CronScheduler.get_due_jobs",
            return_value=[fake_job],
        ),
        patch(
            "faccoder_continuous_improvement.scheduler.cron.CronScheduler.run_due_jobs",
            return_value=[{"job_name": "mock_job", "status": "success"}],
        ) as mock_run,
    ):
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Found 1 due jobs." in result.output
        assert "Executed 1 jobs." in result.output
        mock_run.assert_called_once()


def test_ci_cli_run_due_with_jobs_dry_run() -> None:
    fake_job = CronJob(name="mock_job", schedule="@daily", task_type="research")
    with (
        patch(
            "faccoder_continuous_improvement.scheduler.cron.CronScheduler.get_due_jobs",
            return_value=[fake_job],
        ),
        patch(
            "faccoder_continuous_improvement.scheduler.cron.CronScheduler.run_due_jobs",
        ) as mock_run,
    ):
        result = runner.invoke(app, ["--dry-run"])
        assert result.exit_code == 0
        assert "Found 1 due jobs." in result.output
        assert "Executed" not in result.output
        mock_run.assert_not_called()


def test_ci_cli_invalid_option() -> None:
    result = runner.invoke(app, ["--unknown-flag"])
    assert result.exit_code != 0


def test_ci_cli_main_entrypoint() -> None:
    with patch("faccoder_continuous_improvement.cli.app") as mock_app:
        main()
        mock_app.assert_called_once()
