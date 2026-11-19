"""Gated HTTP transport: the only place nexcoder-testing opens network connections."""

from nexcoder_testing.gate.transport import (
    DEFAULT_ALLOWED_HOSTS,
    TargetHostNotAllowedError,
    check_target_host,
    gated_http_request,
    is_loopback_host,
)

__all__ = [
    "DEFAULT_ALLOWED_HOSTS",
    "TargetHostNotAllowedError",
    "check_target_host",
    "gated_http_request",
    "is_loopback_host",
]
