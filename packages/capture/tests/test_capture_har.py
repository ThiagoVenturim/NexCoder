"""Unit tests for faccoder_capture.web.har."""

from __future__ import annotations

import json

from faccoder_capture.web.har import HarRecorder, sanitize_headers


def test_sanitize_headers() -> None:
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer secret-token-xyz",
        "cookie": "session_id=12345; auth=true",
        "Set-Cookie": "jwt=abcd; Secure",
        "X-API-KEY": "supersecretkey",
        "Proxy-Authorization": "Basic dXNlcjpwYXNz",
        "User-Agent": "test-agent",
    }
    sanitized = sanitize_headers(headers)

    assert sanitized["Content-Type"] == "application/json"
    assert sanitized["User-Agent"] == "test-agent"
    assert sanitized["Authorization"] == "[REDACTED]"
    assert sanitized["cookie"] == "[REDACTED]"
    assert sanitized["Set-Cookie"] == "[REDACTED]"
    assert sanitized["X-API-KEY"] == "[REDACTED]"
    assert sanitized["Proxy-Authorization"] == "[REDACTED]"


def test_har_recorder_add_entry() -> None:
    recorder = HarRecorder()
    entry = recorder.add_entry(
        url="https://example.com/api/test",
        method="post",
        status=201,
        request_headers={"Authorization": "secret", "Content-Type": "application/json"},
        response_headers={"Set-Cookie": "sess=123", "Content-Type": "application/json"},
        mime_type="application/json",
        time_ms=120.5,
        size_bytes=512,
    )

    assert entry.method == "POST"
    assert entry.status == 201
    assert entry.request_headers["Authorization"] == "[REDACTED]"
    assert entry.response_headers["Set-Cookie"] == "[REDACTED]"
    assert len(recorder.entries) == 1


def test_to_har_dict() -> None:
    recorder = HarRecorder()
    recorder.add_entry(
        url="https://example.com/index.html",
        method="GET",
        status=200,
        request_headers={"Accept": "text/html"},
        response_headers={"Content-Type": "text/html; charset=utf-8"},
        mime_type="text/html",
        time_ms=50.0,
        size_bytes=2048,
    )

    har_dict = recorder.to_har_dict(creator_name="faccoder-capture-test")
    assert "log" in har_dict
    log = har_dict["log"]
    assert log["version"] == "1.2"
    assert log["creator"]["name"] == "faccoder-capture-test"
    assert len(log["entries"]) == 1

    entry = log["entries"][0]
    assert entry["request"]["method"] == "GET"
    assert entry["request"]["url"] == "https://example.com/index.html"
    assert entry["response"]["status"] == 200
    assert entry["response"]["content"]["mimeType"] == "text/html"
    assert entry["response"]["content"]["size"] == 2048
    assert entry["time"] == 50.0


def test_to_har_json() -> None:
    recorder = HarRecorder()
    recorder.add_entry(
        url="https://example.com/data",
        method="GET",
        status=200,
        time_ms=10.0,
    )
    json_str = recorder.to_har_json()
    parsed = json.loads(json_str)

    assert parsed["log"]["version"] == "1.2"
    assert len(parsed["log"]["entries"]) == 1
