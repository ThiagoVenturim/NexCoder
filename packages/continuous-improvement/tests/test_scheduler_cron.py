"""Unit tests for continuous improvement cron scheduler."""

from datetime import UTC, datetime, timedelta

from nexcoder_continuous_improvement.scheduler.cron import CronJob, CronScheduler, compute_next_run


def test_compute_next_run_shortcuts() -> None:
    now = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
    hourly = compute_next_run("@hourly", from_time=now)
    daily = compute_next_run("@daily", from_time=now)
    weekly = compute_next_run("@weekly", from_time=now)

    assert hourly == now + timedelta(hours=1)
    assert daily == now + timedelta(days=1)
    assert weekly == now + timedelta(weeks=1)


def test_cron_scheduler_due_execution() -> None:
    scheduler = CronScheduler()
    called_jobs: list[str] = []

    def dummy_handler(job: CronJob) -> str:
        called_jobs.append(job.name)
        return "ok"

    scheduler.register_handler("research", dummy_handler)

    past = datetime.now(UTC) - timedelta(minutes=10)
    job = CronJob(
        name="daily_research",
        schedule="@daily",
        task_type="research",
        next_run=past,
    )
    scheduler.register_job(job)

    due = scheduler.get_due_jobs()
    assert len(due) == 1
    assert due[0].name == "daily_research"

    results = scheduler.run_due_jobs()
    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert "daily_research" in called_jobs
    assert job.run_count == 1
    assert job.last_status == "success"
    assert job.next_run > datetime.now(UTC)
