"""Unit tests for faccoder_capture.qa.screen_doc."""

from __future__ import annotations

from faccoder_capture.desktop.models import (
    DesktopBoundingBox,
    DesktopCaptureResult,
    DesktopControlNode,
    DesktopWindowInfo,
    OCRTextBlock,
)
from faccoder_capture.models import NetworkEntry, StableSelector, WebCaptureResult
from faccoder_capture.qa.models import AccessibilityAuditResult, AccessibilityViolation
from faccoder_capture.qa.screen_doc import generate_screen_documentation


def test_generate_web_screen_documentation() -> None:
    selector = StableSelector(
        primary="#login-btn",
        css="#login-btn",
        xpath="//*[@id='login-btn']",
        tag="button",
        role="button",
        name="Log In",
        text="Log In",
    )
    net_entry = NetworkEntry(
        url="https://example.com/api/login",
        method="POST",
        status=200,
        size_bytes=1024,
    )
    web_res = WebCaptureResult(
        url="https://example.com/login",
        title="Portal Login",
        status_code=200,
        selectors=[selector],
        har_entries=[net_entry],
        is_captcha_detected=True,
    )

    doc = generate_screen_documentation(
        web_result=web_res,
        screenshot_path="/screenshots/portal_login.png",
    )

    assert "# Screen Documentation: Portal Login" in doc
    assert "- Platform: Web" in doc
    assert "- URL: https://example.com/login" in doc
    assert "- Warning: CAPTCHA challenge detected on screen" in doc
    assert "![Portal Login](/screenshots/portal_login.png)" in doc
    assert "## Stable Selectors" in doc
    assert "| `button` | Log In | id | `#login-btn` | button |" in doc
    assert "## Network Summary" in doc
    assert "- Total Requests: 1" in doc
    assert "- Total Transferred: 1024 bytes" in doc


def test_generate_desktop_screen_documentation() -> None:
    window = DesktopWindowInfo(
        handle=8899,
        title="Inventory Manager",
        class_name="TInventoryForm",
        bounds=DesktopBoundingBox(left=10, top=20, right=810, bottom=620),
    )
    btn_child = DesktopControlNode(
        handle=9001,
        name="Export CSV",
        control_type="Button",
        class_name="TButton",
        automation_id="btn_export",
    )
    window_control = DesktopControlNode(
        handle=8899,
        name="Main",
        control_type="Window",
        children=[btn_child],
    )
    ocr_block = OCRTextBlock(
        text="Inventory Total: 450",
        bounds=DesktopBoundingBox(left=20, top=50, right=200, bottom=70),
        confidence=0.99,
    )

    desktop_res = DesktopCaptureResult(
        window_info=window,
        controls=[window_control],
        ocr_results=[ocr_block],
    )

    doc = generate_screen_documentation(desktop_result=desktop_res)

    assert "# Screen Documentation: Inventory Manager" in doc
    assert "- Platform: Desktop" in doc
    assert "- Window Title: Inventory Manager" in doc
    assert "- Bounds: 800x600 at (10, 20)" in doc
    assert "## Control Hierarchy" in doc
    assert "Export CSV" in doc
    assert "btn_export" in doc
    assert "## OCR Extracted Text" in doc
    assert "Inventory Total: 450" in doc


def test_generate_screen_documentation_with_accessibility_audit() -> None:
    web_res = WebCaptureResult(url="https://example.com/home", title="Home")

    # With violations
    violation = AccessibilityViolation(
        rule_id="missing-image-alt",
        description="Image element missing alt attribute",
        impact="serious",
        node_role="img",
        node_name="Hero Banner",
    )
    audit_res = AccessibilityAuditResult(
        violations=[violation],
        passes=9,
        total_checked=10,
        score=90.0,
        is_compliant=False,
    )

    doc_with_violations = generate_screen_documentation(
        web_result=web_res,
        a11y_result=audit_res,
    )

    assert "## Accessibility Audit" in doc_with_violations
    assert "- Overall Score: 90.0%" in doc_with_violations
    assert "- Compliance Status: Violations Detected" in doc_with_violations
    assert "| `missing-image-alt` | **serious** |" in doc_with_violations

    # Compliant audit result
    clean_audit = AccessibilityAuditResult(
        violations=[],
        passes=15,
        total_checked=15,
        score=100.0,
        is_compliant=True,
    )
    doc_clean = generate_screen_documentation(
        web_result=web_res,
        a11y_result=clean_audit,
    )
    assert "Zero accessibility violations detected." in doc_clean
