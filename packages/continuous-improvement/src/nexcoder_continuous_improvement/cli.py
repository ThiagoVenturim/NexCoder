"""CLI entrypoint for faccoder continuous improvement."""

from __future__ import annotations

import typer

from faccoder_continuous_improvement.scheduler.cron import CronJob, CronScheduler

app = typer.Typer(help="faccoder continuous improvement management CLI")


@app.command()
def run_due(
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate job executions without running handlers"),
) -> None:
    """Run all due continuous improvement jobs."""
    scheduler = CronScheduler()
    # Register default routines
    scheduler.register_job(CronJob(name="competitor_diff", schedule="@daily", task_type="research"))
    scheduler.register_job(CronJob(name="observability_monitor", schedule="@hourly", task_type="observability"))
    scheduler.register_job(CronJob(name="security_scan", schedule="@daily", task_type="security"))

    due = scheduler.get_due_jobs()
    typer.echo(f"Found {len(due)} due jobs.")
    if not dry_run and due:
        results = scheduler.run_due_jobs()
        typer.echo(f"Executed {len(results)} jobs.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
