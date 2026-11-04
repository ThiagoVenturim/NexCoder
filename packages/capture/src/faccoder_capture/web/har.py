"""HAR (HTTP Archive) network recording and sanitization."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from faccoder_capture.models import NetworkEntry

SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "proxy-authorization",
    "x-auth-token",
    "x-csrf-token",
    "x-session-token",
    "x-xsrf-token",
}

DEFAULT_SENSITIVE_PARAMS = {
    "token",
    "access_token",
    "api_key",
    "apikey",
    "key",
    "sig",
    "signature",
    "code",
    "secret",
    "auth",
    "auth_token",
    "passwd",
    "password",
    "session",
    "session_id",
}

SECRET_VALUE_PATTERNS = [
    re.compile(r"^(?:ghp_|gho_|glpat-|fc_key_|AKIA|AIza)[A-Za-z0-9_=-]+$"),
    re.compile(r"^eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$"),  # JWT
    re.compile(r"^[0-9a-fA-F]{32,64}$"),  # Hex tokens/hashes >= 32 chars
]


def is_secret_value(value: str) -> bool:
    """Check if a query parameter value matches high-entropy/secret formats."""
    return any(p.match(value) for p in SECRET_VALUE_PATTERNS)


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Sanitize sensitive authentication headers from captured logs."""
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADERS:
            sanitized[key] = "[REDACTED]"
        else:
            sanitized[key] = value
    return sanitized


def sanitize_url(
    url: str,
    sensitive_params: set[str] | list[str] | None = None,
    redact_replacement: str = "[REDACTED]",
) -> str:
    """Redact sensitive query parameter names and secret patterns in URLs."""
    if not url or "?" not in url:
        return url

    sensitive = {p.lower() for p in (sensitive_params if sensitive_params is not None else DEFAULT_SENSITIVE_PARAMS)}

    parts = urlsplit(url)
    if not parts.query:
        return url

    query_params = parse_qsl(parts.query, keep_blank_values=True)
    sanitized_params: list[tuple[str, str]] = []

    for name, val in query_params:
        if name.lower() in sensitive or is_secret_value(val):
            sanitized_params.append((name, redact_replacement))
        else:
            sanitized_params.append((name, val))

    new_query = urlencode(sanitized_params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


class HarRecorder:
    """Records and exports network transactions in HAR 1.2 format with sanitization."""

    def __init__(self, sensitive_params: set[str] | list[str] | None = None) -> None:
        self.entries: list[NetworkEntry] = []
        self.sensitive_params = sensitive_params

    def add_entry(
        self,
        url: str,
        method: str,
        status: int,
        request_headers: dict[str, str] | None = None,
        response_headers: dict[str, str] | None = None,
        mime_type: str = "",
        time_ms: float = 0.0,
        size_bytes: int = 0,
    ) -> NetworkEntry:
        """Add and sanitize a network transaction entry."""
        sanitized_url = sanitize_url(url, sensitive_params=self.sensitive_params)
        entry = NetworkEntry(
            url=sanitized_url,
            method=method.upper(),
            status=status,
            request_headers=sanitize_headers(request_headers or {}),
            response_headers=sanitize_headers(response_headers or {}),
            mime_type=mime_type,
            time_ms=time_ms,
            size_bytes=size_bytes,
        )
        self.entries.append(entry)
        return entry

    def to_har_dict(self, creator_name: str = "faccoder-capture") -> dict[str, Any]:
        """Convert recorded entries to HAR 1.2 standard dictionary structure."""
        har_entries: list[dict[str, Any]] = []
        for e in self.entries:
            req_headers = [{"name": k, "value": v} for k, v in e.request_headers.items()]
            res_headers = [{"name": k, "value": v} for k, v in e.response_headers.items()]
            query_string = [
                {"name": k, "value": v}
                for k, v in parse_qsl(urlsplit(e.url).query, keep_blank_values=True)
            ]
            har_entries.append(
                {
                    "startedDateTime": "2026-11-01T00:00:00.000Z",
                    "time": e.time_ms,
                    "request": {
                        "method": e.method,
                        "url": e.url,
                        "httpVersion": "HTTP/1.1",
                        "headers": req_headers,
                        "queryString": query_string,
                        "headersSize": -1,
                        "bodySize": -1,
                    },
                    "response": {
                        "status": e.status,
                        "statusText": "OK" if e.status < 400 else "Error",
                        "httpVersion": "HTTP/1.1",
                        "headers": res_headers,
                        "content": {
                            "size": e.size_bytes,
                            "mimeType": e.mime_type,
                        },
                        "headersSize": -1,
                        "bodySize": e.size_bytes,
                    },
                    "cache": {},
                    "timings": {
                        "send": 0,
                        "wait": e.time_ms,
                        "receive": 0,
                    },
                }
            )

        return {
            "log": {
                "version": "1.2",
                "creator": {"name": creator_name, "version": "0.1.0"},
                "pages": [],
                "entries": har_entries,
            }
        }

    def to_har_json(self, indent: int = 2) -> str:
        """Export HAR entries as formatted JSON string."""
        return json.dumps(self.to_har_dict(), indent=indent)
