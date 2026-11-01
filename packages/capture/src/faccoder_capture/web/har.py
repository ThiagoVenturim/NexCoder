"""HAR (HTTP Archive) network recording and sanitization."""

from __future__ import annotations

import json
from typing import Any

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


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Sanitize sensitive authentication headers from captured logs."""
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADERS:
            sanitized[key] = "[REDACTED]"
        else:
            sanitized[key] = value
    return sanitized


class HarRecorder:
    """Records and exports network transactions in HAR 1.2 format."""

    def __init__(self) -> None:
        self.entries: list[NetworkEntry] = []

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
        entry = NetworkEntry(
            url=url,
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
            har_entries.append(
                {
                    "startedDateTime": "2026-11-01T00:00:00.000Z",
                    "time": e.time_ms,
                    "request": {
                        "method": e.method,
                        "url": e.url,
                        "httpVersion": "HTTP/1.1",
                        "headers": req_headers,
                        "queryString": [],
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
