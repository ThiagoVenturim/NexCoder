"""DOM scraping, accessibility verification, and UI test generation using nexcoder-capture."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nexcoder_capture import (
    WebCaptureConfig,
    WebCaptureEngine,
    audit_accessibility_tree,
    generate_page_object,
    generate_playwright_test,
)
from nexcoder_control.approval import TargetAuthorizationGate
from nexcoder_core.sandbox import resolve_inside
from nexcoder_security.models import Finding, FindingCategory, Location, Remediation, Severity

from nexcoder_testing.models import (
    DOMScreenSpec,
    GeneratedTestArtifact,
    TestCaseExecution,
    TestScope,
)

RequestCallable = Callable[[str, str, dict[str, str] | None, Any], tuple[int, dict[str, str], str]]


class DOMScrapingRunner:
    """Scrapes target HTML screens using nexcoder-capture, checks DOM contracts, and generates UI tests."""

    def __init__(self, target_gate: TargetAuthorizationGate | None = None) -> None:
        self.target_gate = target_gate

    def discover_screens(self, target_root: Path, configured: list[DOMScreenSpec]) -> list[DOMScreenSpec]:
        """Return configured screens or auto-discover HTML templates inside target_root."""
        if configured:
            return configured

        root = target_root.resolve()
        screens: list[DOMScreenSpec] = []
        for html_file in sorted(root.rglob("*.html")):
            resolved = resolve_inside(root, html_file)
            screens.append(
                DOMScreenSpec(
                    name=resolved.stem,
                    url_or_path=str(resolved),
                    html_content=resolved.read_text(encoding="utf-8"),
                )
            )
        return screens

    def run(
        self,
        target_root: Path,
        screens: list[DOMScreenSpec],
        *,
        requester: RequestCallable | None = None,
        owned_target: bool = True,
        authorized_by: str = "owner",
        agent_id: str = "agent-dom",
    ) -> tuple[list[TestCaseExecution], list[Finding], list[GeneratedTestArtifact]]:
        """Capture DOM for each screen, validate selectors/texts/accessibility, and generate Playwright suites."""
        active_screens = self.discover_screens(target_root, screens)
        capture_cfg = WebCaptureConfig(
            capture_dom=True,
            capture_accessibility=True,
            extract_selectors=True,
            read_only=True,
            owned_target=owned_target,
            authorized_by=authorized_by,
        )
        engine = WebCaptureEngine(
            config=capture_cfg,
            target_gate=self.target_gate,
            audit_log=self.target_gate.audit_log if self.target_gate else None,
        )

        test_cases: list[TestCaseExecution] = []
        findings: list[Finding] = []
        artifacts: list[GeneratedTestArtifact] = []

        for screen in active_screens:
            t0 = time.perf_counter()
            html_text = screen.html_content
            base_url = f"http://localhost/{screen.name}.html"

            if not html_text:
                if screen.url_or_path.startswith("/") and requester is not None:
                    _, _, html_text = requester("GET", screen.url_or_path, None, None)
                    base_url = f"http://localhost{screen.url_or_path}"
                else:
                    cand_path = Path(screen.url_or_path)
                    resolved = resolve_inside(target_root, cand_path)
                    if resolved.exists():
                        html_text = resolved.read_text(encoding="utf-8")
                        base_url = resolved.as_uri()

            if not html_text:
                test_cases.append(
                    TestCaseExecution(
                        test_id=f"{agent_id}:dom:{screen.name}:load",
                        scope=TestScope.DOM,
                        name=f"test_dom_load_{screen.name}",
                        target=screen.url_or_path,
                        passed=False,
                        error_message="Screen HTML content could not be loaded",
                    )
                )
                continue

            capture_res = engine.capture_html(
                html=html_text,
                base_url=base_url,
                title=screen.name,
            )

            # 1. Verify expected texts and selectors in scraped DOM
            missing_texts = [txt for txt in screen.expected_texts if txt not in capture_res.dom]
            extracted_primaries = {sel.primary for sel in capture_res.selectors}
            extracted_testids = {sel.test_id for sel in capture_res.selectors if sel.test_id}

            missing_selectors: list[str] = []
            for expected_sel in screen.expected_selectors:
                if expected_sel in extracted_primaries or expected_sel in capture_res.dom:
                    continue
                # Check data-testid shorthand
                matched_tid = any(tid and tid in expected_sel for tid in extracted_testids)
                if not matched_tid:
                    missing_selectors.append(expected_sel)

            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            dom_passed = not missing_texts and not missing_selectors
            err_parts: list[str] = []
            if missing_texts:
                err_parts.append(f"Missing expected texts: {missing_texts}")
            if missing_selectors:
                err_parts.append(f"Missing expected selectors: {missing_selectors}")

            test_cases.append(
                TestCaseExecution(
                    test_id=f"{agent_id}:dom:{screen.name}:elements",
                    scope=TestScope.DOM,
                    name=f"test_dom_elements_{screen.name}",
                    target=screen.url_or_path,
                    passed=dom_passed,
                    duration_ms=elapsed_ms,
                    assertions_checked=max(1, len(screen.expected_texts) + len(screen.expected_selectors)),
                    error_message="; ".join(err_parts) if err_parts else None,
                    details={
                        "selectors_extracted": len(capture_res.selectors),
                        "missing_texts": missing_texts,
                        "missing_selectors": missing_selectors,
                    },
                )
            )

            if not dom_passed:
                findings.append(
                    Finding(
                        id=f"DOM-MISSING-{screen.name.upper()}",
                        scanner="nexcoder-testing-dom",
                        rule_id="DOM-CONTRACT-001",
                        title=f"Screen '{screen.name}' is missing expected DOM elements or texts",
                        description="; ".join(err_parts),
                        severity=Severity.MEDIUM,
                        category=FindingCategory.COMPLIANCE,
                        location=Location(file_path=screen.url_or_path),
                        remediation=Remediation(
                            summary=(
                                "Ensure required interactive elements, data-testid attributes, "
                                "and labels render in DOM."
                            )
                        ),
                    )
                )

            # 2. Accessibility audit via nexcoder-capture
            if capture_res.accessibility_tree is not None:
                a11y_audit = audit_accessibility_tree([capture_res.accessibility_tree])
                a11y_passed = a11y_audit.is_compliant
                test_cases.append(
                    TestCaseExecution(
                        test_id=f"{agent_id}:dom:{screen.name}:a11y",
                        scope=TestScope.DOM,
                        name=f"test_dom_a11y_{screen.name}",
                        target=screen.url_or_path,
                        passed=a11y_passed,
                        duration_ms=1.0,
                        assertions_checked=max(1, a11y_audit.total_checked),
                        error_message=(
                            f"{len(a11y_audit.violations)} accessibility violation(s)"
                            if not a11y_passed
                            else None
                        ),
                    )
                )
                for violation in a11y_audit.violations:
                    default_rem = "Add descriptive alt text or ARIA labels to interactive elements."
                    findings.append(
                        Finding(
                            id=f"DOM-A11Y-{screen.name.upper()}-{violation.rule_id.upper()}",
                            scanner="nexcoder-capture-a11y",
                            rule_id=f"A11Y-{violation.rule_id.upper()}",
                            title=f"Accessibility issue on '{screen.name}': {violation.description}",
                            description=(
                                f"Role '{violation.node_role}' violated rule "
                                f"'{violation.rule_id}': {violation.description}"
                            ),
                            severity=Severity.LOW if violation.impact in ("minor", "moderate") else Severity.MEDIUM,
                            category=FindingCategory.COMPLIANCE,
                            location=Location(file_path=screen.url_or_path),
                            remediation=Remediation(
                                summary=default_rem
                            ),
                        )
                    )

            # 3. Synthesize Playwright test and Page Object artifacts using nexcoder-capture
            pw_test_code = generate_playwright_test(capture_res, test_name=f"test_ui_{screen.name}")
            po_code = generate_page_object(capture_res)

            artifacts.append(
                GeneratedTestArtifact(
                    name=f"playwright_test_{screen.name}",
                    scope=TestScope.DOM,
                    file_name=f"test_ui_{screen.name}.py",
                    content=pw_test_code,
                    target_reference=screen.url_or_path,
                )
            )
            artifacts.append(
                GeneratedTestArtifact(
                    name=f"page_object_{screen.name}",
                    scope=TestScope.DOM,
                    file_name=f"page_{screen.name}.py",
                    content=po_code,
                    target_reference=screen.url_or_path,
                )
            )

        return test_cases, findings, artifacts
