"""Unit tests for faccoder_capture.web.har."""

from __future__ import annotations

import json

from faccoder_capture.web.har import HarRecorder, sanitize_headers, sanitize_url


def test_sanitize_headers() -> None:
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer secret-token-xyz",
        "cookie": "session_id=12345; auth=true",
        "Set-Cookie": "jwt=abcd; Secure",
        "X-API-KEY": "supersecretkey",
        "Proxy-Authorization": "Basic dXNlcjpwYXNz",
        "X-Auth-Token": "token-123",
        "x-csrf-token": "csrf-456",
        "X-Session-Token": "sess-789",
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
    assert sanitized["X-Auth-Token"] == "[REDACTED]"
    assert sanitized["x-csrf-token"] == "[REDACTED]"
    assert sanitized["X-Session-Token"] == "[REDACTED]"


def test_sanitize_url_sensitive_params() -> None:
    # URL containing various sensitive parameter names
    url = (
        "https://api.example.com/oauth/callback"
        "?code=auth_code_secret"
        "&token=jwt_token_here"
        "&access_token=bearer_xyz"
        "&api_key=my_api_key_123"
        "&key=private_key"
        "&sig=hmac_signature_value"
        "&page=2"
        "&sort=asc"
    )
    sanitized = sanitize_url(url)

    assert "page=2" in sanitized
    assert "sort=asc" in sanitized
    assert "code=%5BREDACTED%5D" in sanitized or "code=[REDACTED]" in sanitized
    assert "token=%5BREDACTED%5D" in sanitized or "token=[REDACTED]" in sanitized
    assert "access_token=%5BREDACTED%5D" in sanitized or "access_token=[REDACTED]" in sanitized
    assert "api_key=%5BREDACTED%5D" in sanitized or "api_key=[REDACTED]" in sanitized
    assert "key=%5BREDACTED%5D" in sanitized or "key=[REDACTED]" in sanitized
    assert "sig=%5BREDACTED%5D" in sanitized or "sig=[REDACTED]" in sanitized

    # Sensitive values must NOT appear in output
    assert "auth_code_secret" not in sanitized
    assert "jwt_token_here" not in sanitized
    assert "bearer_xyz" not in sanitized
    assert "my_api_key_123" not in sanitized
    assert "private_key" not in sanitized
    assert "hmac_signature_value" not in sanitized


def test_sanitize_url_custom_params() -> None:
    url = "https://example.com/search?custom_secret=12345&query=testing"
    # By default custom_secret is not redacted
    assert "custom_secret=12345" in sanitize_url(url)

    # With custom list
    sanitized = sanitize_url(url, sensitive_params={"custom_secret"})
    assert "12345" not in sanitized
    assert "query=testing" in sanitized


def test_sanitize_url_secret_value_patterns() -> None:
    # Query parameter with non-sensitive name but containing an obvious API key or JWT value
    fake_jwt = "eyJ" + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0.do_not_leak"
    url = (
        f"https://example.com/hook"
        f"?callback_payload={fake_jwt}"
        "&meta=fc_key_secret_1234567890abcdef"
        "&id=normal_id"
    )
    sanitized = sanitize_url(url)
    assert "id=normal_id" in sanitized
    assert "do_not_leak" not in sanitized
    assert "fc_key_secret_1234567890abcdef" not in sanitized


def test_har_recorder_redacts_urls_and_querystrings() -> None:
    recorder = HarRecorder()
    entry = recorder.add_entry(
        url="https://example.com/api/v1/user?id=42&token=super_secret_token",
        method="GET",
        status=200,
        request_headers={"Authorization": "Bearer secret-token"},
    )

    # Entry url is sanitized
    assert "super_secret_token" not in entry.url
    assert "id=42" in entry.url

    har_dict = recorder.to_har_dict()
    har_entry = har_dict["log"]["entries"][0]

    assert "super_secret_token" not in har_entry["request"]["url"]
    query_params = {q["name"]: q["value"] for q in har_entry["request"]["queryString"]}
    assert query_params["id"] == "42"
    assert query_params["token"] in ("[REDACTED]", "%5BREDACTED%5D")


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
