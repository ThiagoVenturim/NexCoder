"""Unit tests for nexcoder_capture.web.policy."""

from __future__ import annotations

import pytest
from nexcoder_capture.models import (
    CaptchaDetectedError,
    DomainNotAllowedError,
    ReadOnlyViolationError,
    RobotsDisallowedError,
    WebCaptureConfig,
)
from nexcoder_capture.web.policy import PolicyEnforcer


def test_url_scheme_validation() -> None:
    enforcer = PolicyEnforcer(WebCaptureConfig())

    enforcer.validate_url("http://example.com")
    enforcer.validate_url("https://example.com/path")
    enforcer.validate_url("file:///path/to/fixture.html")

    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        enforcer.validate_url("ftp://example.com/file.txt")

    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        enforcer.validate_url("javascript:alert(1)")


def test_file_scheme_always_allowed() -> None:
    config = WebCaptureConfig(allowed_domains=["example.com"])
    enforcer = PolicyEnforcer(config)
    # File URLs bypass domain allowlist checks
    enforcer.validate_url("file:///workspace/page.html")


def test_domain_allowlist() -> None:
    config = WebCaptureConfig(allowed_domains=["example.com", "api.example.org", "localhost:8080"])
    enforcer = PolicyEnforcer(config)

    enforcer.validate_url("https://example.com/home")
    enforcer.validate_url("https://sub.example.com/profile")
    enforcer.validate_url("https://api.example.org/v1")
    enforcer.validate_url("http://localhost:8080/app")

    with pytest.raises(DomainNotAllowedError):
        enforcer.validate_url("https://example.net/landing")

    with pytest.raises(DomainNotAllowedError):
        enforcer.validate_url("https://fakeexample.com")


def test_robots_txt_enforcement() -> None:
    config = WebCaptureConfig(
        honor_robots_txt=True,
        user_agent="nexcoder-capture/0.1.0",
    )
    enforcer = PolicyEnforcer(config)

    robots_content = """
User-agent: *
Disallow: /private/
Disallow: /admin/
Allow: /public/
"""
    enforcer.register_robots_txt("https://example.com", robots_content)

    # Allowed URL
    enforcer.validate_url("https://example.com/public/data")

    # Disallowed URL
    with pytest.raises(RobotsDisallowedError):
        enforcer.validate_url("https://example.com/private/secret")


def test_robots_txt_disabled() -> None:
    config = WebCaptureConfig(
        honor_robots_txt=False,
        user_agent="nexcoder-capture/0.1.0",
    )
    enforcer = PolicyEnforcer(config)

    robots_content = """
User-agent: *
Disallow: /private/
"""
    enforcer.register_robots_txt("https://example.com", robots_content)

    # Allowed because honor_robots_txt is False
    enforcer.validate_url("https://example.com/private/page")


@pytest.mark.parametrize(
    "snippet",
    [
        '<div id="g-recaptcha" class="g-recaptcha"></div>',
        '<script src="https://js.hcaptcha.com/1/api.js"></script>',
        '<div class="cf-turnstile" data-sitekey="xxx"></div>',
        '<div id="cf-challenge">Checking your browser</div>',
        '<script src="https://client-api.arkoselabs.com/fc/api/"></script>',
        '<div class="funcaptcha-holder"></div>',
        '<span class="challenge-running">Checking connection</span>',
        "<p>Please verify you are human before continuing</p>",
        "<p>Complete the captcha to proceed</p>",
    ],
)
def test_captcha_detection(snippet: str) -> None:
    enforcer = PolicyEnforcer(WebCaptureConfig())
    assert enforcer.detect_captcha(f"<html><body>{snippet}</body></html>") is True

    with pytest.raises(CaptchaDetectedError):
        enforcer.assert_no_captcha(f"<html><body>{snippet}</body></html>")


def test_clean_content_no_captcha() -> None:
    enforcer = PolicyEnforcer(WebCaptureConfig())
    clean_html = "<html><body><h1>Hello World</h1><p>Welcome to our app</p></body></html>"
    assert enforcer.detect_captcha(clean_html) is False
    enforcer.assert_no_captcha(clean_html)


def test_validate_action_read_only() -> None:
    enforcer_ro = PolicyEnforcer(WebCaptureConfig(read_only=True))

    # Read-only actions pass
    enforcer_ro.validate_action("inspect_element", is_mutating=False)

    # Mutating actions fail in read-only mode
    with pytest.raises(ReadOnlyViolationError):
        enforcer_ro.validate_action("click_submit", is_mutating=True)

    # Non-read-only permits mutating actions
    enforcer_rw = PolicyEnforcer(WebCaptureConfig(read_only=False))
    enforcer_rw.validate_action("click_submit", is_mutating=True)


def test_capture_target_authorization_gate() -> None:
    from nexcoder_control.approval import TargetNotAuthorizedError

    enforcer = PolicyEnforcer(WebCaptureConfig(allowed_domains=["example.com"]))

    with pytest.raises(TargetNotAuthorizedError, match="USAGE_POLICY.md"):
        enforcer.verify_target_authorization("https://example.com/login", owned_target=False)

    denied = enforcer.audit_log.query(event_type="target.authorization.denied")
    assert len(denied) == 1
    assert denied[0].resource == "https://example.com/login"

    rec = enforcer.verify_target_authorization(
        "https://example.com/login",
        owned_target=True,
        authorized_by="qa-owner",
        metadata={"session_token": "super_secret_cookie_12345"},
    )
    assert rec.authorized_by == "qa-owner"
    granted = enforcer.audit_log.query(event_type="target.authorization.granted")
    assert len(granted) == 1
    assert granted[0].actor == "qa-owner"
    assert "super_secret_cookie_12345" not in granted[0].model_dump_json()
