"""Langfuse integration that can never take the application down.

Tracing is valuable but optional. If Langfuse is not installed, not configured,
or unreachable, ``langfuse_callbacks`` returns an empty list and the LLM call
proceeds untraced. A small circuit breaker stops retrying a failing Langfuse
for a while instead of paying the connection timeout on every call.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from faccoder_core.config import FaccoderConfig

logger = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_after_seconds: float = 300.0):
        self.failure_threshold = failure_threshold
        self.reset_after_seconds = reset_after_seconds
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if time.monotonic() - self._opened_at >= self.reset_after_seconds:
                # Half-open: let one attempt through.
                self._opened_at = None
                self._failures = self.failure_threshold - 1
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.monotonic()

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None


_breaker = CircuitBreaker()


def langfuse_configured(cfg: FaccoderConfig) -> bool:
    spec = cfg.langfuse
    return bool(spec.enabled and os.environ.get(spec.public_key_env) and os.environ.get(spec.secret_key_env))


def langfuse_callbacks(cfg: FaccoderConfig, **metadata) -> list:
    """Return ``[CallbackHandler]`` when Langfuse is usable, otherwise ``[]``."""
    if not langfuse_configured(cfg) or not _breaker.allow():
        return []
    try:
        try:
            from langfuse.langchain import CallbackHandler  # langfuse >= 3
        except ImportError:
            from langfuse.callback import CallbackHandler  # langfuse 2.x
    except ImportError:
        logger.debug("langfuse is not installed; tracing disabled")
        return []

    spec = cfg.langfuse
    try:
        try:
            handler = CallbackHandler(
                public_key=os.environ[spec.public_key_env],
                secret_key=os.environ[spec.secret_key_env],
                host=os.environ.get(spec.host_env, "http://localhost:3000"),
                metadata=metadata or None,
            )
        except TypeError:
            # langfuse >= 3 reads keys and host from the environment.
            handler = CallbackHandler()
        _breaker.record_success()
        return [handler]
    except Exception as exc:  # noqa: BLE001 - tracing must never break the caller
        _breaker.record_failure()
        logger.warning("Langfuse unavailable, continuing without tracing: %s", exc)
        return []
