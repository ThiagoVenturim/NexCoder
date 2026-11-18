"""Daily quota tracker to enforce daily ceiling on automated PRs and merges."""

from __future__ import annotations

import threading
from datetime import UTC, datetime


class DailyQuotaTracker:
    """Enforces daily ceilings for automated pull requests and merges into develop."""

    DEFAULT_DAILY_LIMIT = 5

    def __init__(self, max_daily_merges: int = DEFAULT_DAILY_LIMIT) -> None:
        self.max_daily_merges = max(1, max_daily_merges)
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def _get_key(self, date: datetime | None = None) -> str:
        d = date or datetime.now(UTC)
        return d.strftime("%Y-%m-%d")

    def get_used_today(self, date: datetime | None = None) -> int:
        """Return the number of merges performed on the given date (UTC)."""
        key = self._get_key(date)
        with self._lock:
            return self._counts.get(key, 0)

    def get_remaining_today(self, date: datetime | None = None) -> int:
        """Return remaining merge capacity for today."""
        used = self.get_used_today(date)
        return max(0, self.max_daily_merges - used)

    def can_merge(self, date: datetime | None = None) -> bool:
        """Return True if daily quota has not been exhausted."""
        return self.get_remaining_today(date) > 0

    def record_merge(self, date: datetime | None = None) -> int:
        """Record a successful automated merge for today.

        Returns updated count for today.
        """
        key = self._get_key(date)
        with self._lock:
            current = self._counts.get(key, 0)
            self._counts[key] = current + 1
            return self._counts[key]

    def reset(self, date: datetime | None = None) -> None:
        """Reset counter for a specific date or today."""
        key = self._get_key(date)
        with self._lock:
            self._counts[key] = 0
