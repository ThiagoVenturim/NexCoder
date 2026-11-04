"""Rate limiting algorithms (TokenBucket and FixedWindow) and cap errors."""

from __future__ import annotations

import threading
import time


class RateLimitExceededError(Exception):
    """Raised when request rate or token throughput exceeds limits (HTTP 429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after_seconds: float = 60.0,
        status_code: int = 429,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        self.status_code = status_code


class CapExceededError(Exception):
    """Raised when cumulative USD spend exceeds configured cap (HTTP 403)."""

    def __init__(
        self,
        message: str = "USD spending cap exceeded for this API key",
        status_code: int = 403,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class TokenBucket:
    """Thread-safe Token Bucket rate limiter."""

    def __init__(self, capacity: float, refill_rate_per_sec: float) -> None:
        if capacity <= 0 or refill_rate_per_sec <= 0:
            raise ValueError("Capacity and refill rate must be positive numbers")
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate_per_sec)
        self.tokens = float(capacity)
        self.last_update = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, amount: float = 1.0) -> bool:
        """Attempt to consume tokens. Return True if granted, False if rejected."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now

            # Refill tokens up to capacity
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False

    def remaining_tokens(self) -> float:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            current = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            return current


class FixedWindowRateLimiter:
    """Thread-safe Fixed-Window rate limiter tracking counts per window."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window_seconds = window_seconds
        self._windows: dict[str, tuple[int, int]] = {}  # key -> (window_index, count)
        self._lock = threading.Lock()

    def _current_window_index(self) -> int:
        return int(time.time() // self.window_seconds)

    def check_and_increment(self, key: str, limit: int, amount: int = 1) -> tuple[bool, int, float]:
        """Check if amount is within limit and increment.

        Returns (allowed: bool, current_count: int, seconds_to_reset: float).
        """
        now = time.time()
        win_idx = int(now // self.window_seconds)
        seconds_to_reset = max(0.0, ((win_idx + 1) * self.window_seconds) - now)

        with self._lock:
            current_win, count = self._windows.get(key, (win_idx, 0))
            if current_win != win_idx:
                current_win = win_idx
                count = 0

            if count + amount > limit:
                self._windows[key] = (current_win, count)
                return False, count, seconds_to_reset

            count += amount
            self._windows[key] = (current_win, count)
            return True, count, seconds_to_reset

    def get_count(self, key: str) -> int:
        now = time.time()
        win_idx = int(now // self.window_seconds)
        with self._lock:
            current_win, count = self._windows.get(key, (win_idx, 0))
            return count if current_win == win_idx else 0
