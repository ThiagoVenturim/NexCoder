"""Unit tests for nexcoder_capture.models."""

from __future__ import annotations

import pytest
from nexcoder_capture.models import (
    AccessibilityNode,
    CaptchaDetectedError,
    CapturePolicyError,
    DomainNotAllowedError,
    NetworkEntry,
    ReadOnlyViolationError,
    RobotsDisallowedError,
    StableSelector,
    WebCaptureConfig,
    WebCaptureResult,
)


def test_accessibility_node_defaults() -> None:
    node = AccessibilityNode(role="button", name="Submit")
    assert node.role == "button"
    assert node.name == "Submit"
    assert node.value is None
    assert node.disabled is False
    assert node.children == []


def test_accessibility_node_with_children() -> None:
    child1 = AccessibilityNode(role="statictext", name="Click me")
    child2 = AccessibilityNode(role="img", name="Icon")
    parent = AccessibilityNode(role="button", name="Button", children=[child1, child2])

    assert len(parent.children) == 2
    assert parent.children[0].role == "statictext"
    assert parent.children[1].name == "Icon"


def test_stable_selector_creation() -> None:
    selector = StableSelector(
        primary="getByTestId('login-btn')",
        css="[data-testid='login-btn']",
        xpath="//*[@data-testid='login-btn']",
        tag="button",
        role="button",
        name="Log In",
        test_id="login-btn",
        confidence=1.0,
        strategy="test_id",
    )
    assert selector.strategy == "test_id"
    assert selector.confidence == 1.0
    assert selector.primary == "getByTestId('login-btn')"


def test_network_entry_creation() -> None:
    entry = NetworkEntry(
        url="https://example.com/api/v1/data",
        method="GET",
        status=200,
        request_headers={"accept": "application/json"},
        response_headers={"content-type": "application/json"},
        mime_type="application/json",
        time_ms=45.2,
        size_bytes=1024,
    )
    assert entry.status == 200
    assert entry.method == "GET"
    assert entry.time_ms == 45.2
    assert entry.size_bytes == 1024


def test_web_capture_config_defaults() -> None:
    config = WebCaptureConfig()
    assert config.capture_dom is True
    assert config.capture_accessibility is True
    assert config.capture_screenshot is False
    assert config.capture_har is True
    assert config.extract_selectors is True
    assert config.timeout_ms == 30000
    assert config.user_agent == "nexcoder-capture/0.1.0"
    assert config.honor_robots_txt is True
    assert config.allowed_domains == []
    assert config.read_only is True


def test_web_capture_result_defaults() -> None:
    result = WebCaptureResult(url="https://example.com")
    assert result.url == "https://example.com"
    assert result.title == ""
    assert result.dom == ""
    assert result.accessibility_tree is None
    assert result.screenshot_bytes is None
    assert result.har_entries == []
    assert result.selectors == []
    assert result.warnings == []
    assert result.is_captcha_detected is False


def test_exception_hierarchy() -> None:
    assert issubclass(RobotsDisallowedError, CapturePolicyError)
    assert issubclass(CaptchaDetectedError, CapturePolicyError)
    assert issubclass(DomainNotAllowedError, CapturePolicyError)
    assert issubclass(ReadOnlyViolationError, CapturePolicyError)

    with pytest.raises(CapturePolicyError):
        raise CaptchaDetectedError("Captcha found")
