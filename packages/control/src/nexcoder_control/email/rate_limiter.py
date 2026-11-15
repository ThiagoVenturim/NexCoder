"""Thread-safe rate limiter respecting Gmail, Microsoft Graph, and SMTP platform limits."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from nexcoder_control.email.models import EmailRateLimitExceededError


class EmailRateLimiter:
    """Sliding-window rate limiter preventing API throttling across email providers."""

    def __init__(self, limits_rpm: dict[str, int] | None = None, window_seconds: float = 60.0) -> None:
        self.window_seconds = window_seconds
        self.limits_rpm = limits_rpm or {
            "gmail": 60,
            "outlook": 30,
            "smtp": 30,
        }
        self._history: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def get_limit(self, provider: str) -> int:
        norm = provider.lower()
        if norm in ("outlook", "graph", "m365"):
            norm = "outlook"
        return self.limits_rpm.get(norm, 30)

    def set_limit(self, provider: str, limit_rpm: int) -> None:
        with self._lock:
            self.limits_rpm[provider.lower()] = max(1, limit_rpm)

    def check_and_acquire(self, provider: str) -> tuple[bool, float]:
        """Check if request is within rate limit and record consumption.

        Returns (is_allowed, wait_seconds_needed).
        """
        norm = provider.lower()
        if norm in ("outlook", "graph", "m365"):
            norm = "outlook"

        limit = self.get_limit(norm)
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            dq = self._history[norm]
            while dq and dq[0] <= cutoff:
                dq.popleft()

            if len(dq) < limit:
                dq.append(now)
                return True, 0.0

            # Window is saturated. Time until oldest entry rolls out
            oldest = dq[0]
            wait_needed = max(0.1, (oldest + self.window_seconds) - now)
            return False, wait_needed

    def enforce(self, provider: str) -> None:
        """Enforce rate limits, raising EmailRateLimitExceededError on violation."""
        allowed, wait_seconds = self.check_and_acquire(provider)
        if not allowed:
            limit = self.get_limit(provider)
            raise EmailRateLimitExceededError(provider=provider, limit_rpm=limit, retry_after_seconds=wait_seconds)

    def reset(self, provider: str | None = None) -> None:
        """Clear usage history for testing or resetting."""
        with self._lock:
            if provider:
                norm = provider.lower()
                if norm in ("outlook", "graph", "m365"):
                    norm = "outlook"
                self._history[norm].clear()
            else:
                self._history.clear()
