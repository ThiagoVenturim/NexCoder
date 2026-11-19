"""HTTP transport that only reaches the user's declared local target.

Every runner sends its requests through ``gated_http_request``. Each call checks the target host
again, so a runner used on its own (outside the orchestrator) still cannot reach a third-party
host, and offline mode never leaves the loopback interface.
"""

from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.request
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = ("localhost", "127.0.0.1", "::1", "testserver")
_LOOPBACK_NAMES = frozenset({"localhost", "testserver"})


class TargetHostNotAllowedError(PermissionError):
    """Raised when a request would leave the declared local or owned target."""


def is_loopback_host(hostname: str) -> bool:
    """Return True when hostname is a loopback name or address (the only hosts offline mode allows)."""
    host = hostname.lower().strip("[]")
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_target_host(
    base_url: str,
    *,
    offline: bool = True,
    allowed_hosts: Iterable[str] | None = None,
) -> str:
    """Validate base_url against the allowed hosts and offline mode; return the lowercase hostname."""
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise TargetHostNotAllowedError(f"Unsupported scheme '{parsed.scheme}' for target '{base_url}'")
    hostname = (parsed.hostname or "").lower()
    allowed = {h.lower() for h in (allowed_hosts if allowed_hosts is not None else DEFAULT_ALLOWED_HOSTS)}
    if hostname not in allowed:
        raise TargetHostNotAllowedError(
            f"Host '{hostname}' is outside the allowed local/owned hosts {sorted(allowed)}"
        )
    if offline and not is_loopback_host(hostname):
        raise TargetHostNotAllowedError(f"Host '{hostname}' is not local and offline mode is enabled")
    return hostname


def gated_http_request(
    base_url: str,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: Any = None,
    *,
    timeout: float = 10.0,
    offline: bool = True,
    allowed_hosts: Iterable[str] | None = None,
) -> tuple[int, dict[str, str], str]:
    """Send one HTTP request to the owned target and return (status, headers, body text)."""
    check_target_host(base_url, offline=offline, allowed_hosts=allowed_hosts)
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    req_headers = dict(headers or {})
    data_bytes: bytes | None = None
    if isinstance(body, (dict, list)):
        data_bytes = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    elif isinstance(body, str):
        data_bytes = body.encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method.upper())  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, dict(resp.headers.items()), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        resp_headers = dict(exc.headers.items()) if exc.headers else {}
        err_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, resp_headers, err_body
