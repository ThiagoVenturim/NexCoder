"""Screen documentation generator producing structured Markdown reports."""

from __future__ import annotations

from faccoder_capture.desktop.models import DesktopCaptureResult, DesktopControlNode
from faccoder_capture.models import WebCaptureResult
from faccoder_capture.qa.models import AccessibilityAuditResult


def _flatten_desktop_controls(nodes: list[DesktopControlNode]) -> list[DesktopControlNode]:
    """Recursively flatten control tree into a single list."""
    flattened: list[DesktopControlNode] = []
    for node in nodes:
        flattened.append(node)
        if node.children:
            flattened.extend(_flatten_desktop_controls(node.children))
    return flattened


def generate_screen_documentation(
    web_result: WebCaptureResult | None = None,
    desktop_result: DesktopCaptureResult | None = None,
    a11y_result: AccessibilityAuditResult | None = None,
    title: str | None = None,
    screenshot_path: str | None = None,
) -> str:
    """Generate structured Markdown documentation for a captured web or desktop screen."""
    lines: list[str] = []

    # Title header
    screen_title = title
    if not screen_title:
        if web_result and web_result.title:
            screen_title = web_result.title
        elif desktop_result and desktop_result.window_info:
            screen_title = desktop_result.window_info.title
        else:
            screen_title = "Captured Screen"

    lines.append(f"# Screen Documentation: {screen_title}")
    lines.append("")

    # Overview Section
    lines.append("## Overview")
    lines.append("")
    if web_result:
        lines.append("- Platform: Web")
        lines.append(f"- URL: {web_result.url}")
        lines.append(f"- Title: {web_result.title}")
        lines.append(f"- Status Code: {web_result.status_code}")
        lines.append(f"- Captured At: {web_result.captured_at.isoformat()}")
        if web_result.is_captcha_detected:
            lines.append("- Warning: CAPTCHA challenge detected on screen")
    elif desktop_result:
        win = desktop_result.window_info
        lines.append("- Platform: Desktop")
        if win:
            lines.append(f"- Window Title: {win.title}")
            lines.append(f"- Class Name: {win.class_name}")
            lines.append(f"- Handle: {win.handle}")
            if win.bounds:
                b = win.bounds
                lines.append(f"- Bounds: {b.width}x{b.height} at ({b.left}, {b.top})")
        lines.append(f"- Captured At: {desktop_result.captured_at.isoformat()}")
    lines.append("")

    # Screenshot Section
    if screenshot_path:
        lines.append("## Screenshot")
        lines.append("")
        lines.append(f"![{screen_title}]({screenshot_path})")
        lines.append("")

    # Interactive Elements & Selectors Table
    if web_result and web_result.selectors:
        lines.append("## Stable Selectors")
        lines.append("")
        lines.append("| Tag | Text / Label | Type | Primary Selector | ARIA Role |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for sel in web_result.selectors:
            tag = sel.tag or "element"
            text = (sel.text or "").replace("|", "\\|")
            primary = (sel.primary_selector or "").replace("|", "\\|")
            role = sel.role or "-"
            lines.append(f"| `{tag}` | {text} | {sel.selector_type} | `{primary}` | {role} |")
        lines.append("")

    if desktop_result and desktop_result.controls:
        flat_controls = _flatten_desktop_controls(desktop_result.controls)
        lines.append("## Control Hierarchy")
        lines.append("")
        lines.append("| Name | Control Type | Class Name | Automation ID | Enabled | Visible |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for ctrl in flat_controls:
            name = (ctrl.name or "-").replace("|", "\\|")
            ctrl_type = ctrl.control_type or "Control"
            class_name = ctrl.class_name or "-"
            auto_id = ctrl.automation_id or "-"
            enabled = "Yes" if ctrl.is_enabled else "No"
            visible = "Yes" if ctrl.is_visible else "No"
            lines.append(f"| {name} | `{ctrl_type}` | `{class_name}` | `{auto_id}` | {enabled} | {visible} |")
        lines.append("")

    # OCR Fallback Section
    if desktop_result and desktop_result.ocr_results:
        lines.append("## OCR Extracted Text")
        lines.append("")
        lines.append("| Text Block | Confidence | Coordinates (L, T, R, B) |")
        lines.append("| :--- | :--- | :--- |")
        for ocr in desktop_result.ocr_results:
            text = (ocr.text or "").replace("|", "\\|")
            conf = f"{ocr.confidence:.2f}"
            b = ocr.bounds
            bounds = f"({b.left}, {b.top}, {b.right}, {b.bottom})" if b else "-"
            lines.append(f"| {text} | {conf} | {bounds} |")
        lines.append("")

    # Accessibility Audit Section
    if a11y_result:
        lines.append("## Accessibility Audit")
        lines.append("")
        lines.append(f"- Overall Score: {a11y_result.score}%")
        lines.append(f"- Compliance Status: {'Compliant' if a11y_result.is_compliant else 'Violations Detected'}")
        lines.append(f"- Checks Passed: {a11y_result.passes} / {a11y_result.total_checked}")
        lines.append("")
        if a11y_result.violations:
            lines.append("| Rule ID | Impact | Description | Target Role | Target Name |")
            lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for v in a11y_result.violations:
                desc = v.description.replace("|", "\\|")
                name = (v.node_name or "-").replace("|", "\\|")
                lines.append(f"| `{v.rule_id}` | **{v.impact}** | {desc} | `{v.node_role}` | {name} |")
            lines.append("")
        else:
            lines.append("Zero accessibility violations detected.")
            lines.append("")

    # Network / HAR Summary (Web only)
    if web_result and web_result.network_entries:
        lines.append("## Network Summary")
        lines.append("")
        total_requests = len(web_result.network_entries)
        total_size = sum(e.response_body_size for e in web_result.network_entries)
        lines.append(f"- Total Requests: {total_requests}")
        lines.append(f"- Total Transferred: {total_size} bytes")
        lines.append("")

    return "\n".join(lines)
