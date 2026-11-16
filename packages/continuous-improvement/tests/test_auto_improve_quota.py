"""Unit tests for daily quota tracking and ceiling enforcement."""

from datetime import UTC, datetime, timedelta

from nexcoder_continuous_improvement.auto_improve.quota import DailyQuotaTracker


def test_quota_tracker_initial_state() -> None:
    tracker = DailyQuotaTracker(max_daily_merges=3)
    assert tracker.get_used_today() == 0
    assert tracker.get_remaining_today() == 3
    assert tracker.can_merge() is True


def test_quota_tracker_records_and_exhausts() -> None:
    tracker = DailyQuotaTracker(max_daily_merges=2)
    tracker.record_merge()
    assert tracker.get_used_today() == 1
    assert tracker.get_remaining_today() == 1
    assert tracker.can_merge() is True

    tracker.record_merge()
    assert tracker.get_used_today() == 2
    assert tracker.get_remaining_today() == 0
    assert tracker.can_merge() is False


def test_quota_tracker_distinct_dates() -> None:
    tracker = DailyQuotaTracker(max_daily_merges=2)
    today = datetime.now(UTC)
    yesterday = today - timedelta(days=1)

    tracker.record_merge(yesterday)
    tracker.record_merge(yesterday)
    assert tracker.can_merge(yesterday) is False

    # Today should still be empty
    assert tracker.get_used_today(today) == 0
    assert tracker.can_merge(today) is True


def test_quota_tracker_reset() -> None:
    tracker = DailyQuotaTracker(max_daily_merges=1)
    tracker.record_merge()
    assert tracker.can_merge() is False

    tracker.reset()
    assert tracker.can_merge() is True
    assert tracker.get_used_today() == 0
