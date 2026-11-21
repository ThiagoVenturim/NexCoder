"""Defensive application security runner reusing nexcoder-security scanners, gate, and app probes."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nexcoder_control.approval import TargetAuthorizationGate, redact_secrets
from nexcoder_core.sandbox import resolve_inside
from nexcoder_security import (
    Finding,
    FindingCategory,
    GatePolicy,
    GateVerdict,
    Location,
    MultiScannerEngine,
    Remediation,
    SecurityGateEvaluator,
    Severity,
)

from nexcoder_testing.gate import gated_http_request
from nexcoder_testing.models import (
    APIEndpointSpec,
    TestCaseExecution,
    TestScope,
)

RequestCallable = Callable[[str, str, dict[str, str] | None, Any], tuple[int, dict[str, str], str]]

_RESPONSE_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OpenAI/API Secret Key", re.compile(r"sk-[A-Za-z0-9_-]{12,}")),
    ("GitHub Token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{16,}")),
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Private Key Block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

_REQUIRED_SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("x-content-type-options", "X-Content-Type-Options: nosniff"),
    ("x-frame-options", "X-Frame-Options: DENY or SAMEORIGIN"),
    ("content-security-policy", "Content-Security-Policy"),
)


class ApplicationSecurityRunner:
    """Runs nexcoder-security scanners, release gate, and defensive application security checks."""

    def __init__(
        self,
        target_gate: TargetAuthorizationGate,
        *,
        offline: bool = True,
        allowed_hosts: list[str] | None = None,
    ) -> None:
        self.target_gate = target_gate
        self.offline = offline
        self.allowed_hosts = allowed_hosts

    def _http_dispatch(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None,
        body: Any,
        *,
        requester: RequestCallable | None,
        base_url: str | None,
        timeout: float = 10.0,
    ) -> tuple[int, dict[str, str], str]:
        if requester is not None:
            return requester(method, path, headers, body)
        if base_url is None:
            raise ValueError("Either requester or base_url is required")

        return gated_http_request(
            base_url,
            method,
            path,
            headers,
            body,
            timeout=timeout,
            offline=self.offline,
            allowed_hosts=self.allowed_hosts,
        )

    def run(
        self,
        target_root: Path,
        endpoints: list[APIEndpointSpec],
        *,
        scanners: list[str] | None = None,
        offline: bool = True,
        owned_target: bool = True,
        authorized_by: str = "owner",
        approval_token: str | None = None,
        requester: RequestCallable | None = None,
        base_url: str | None = None,
        agent_id: str = "agent-security",
    ) -> tuple[list[TestCaseExecution], list[Finding], GateVerdict]:
        """Execute static scanners, log secret checks, header checks, and malformed input checks."""
        test_cases: list[TestCaseExecution] = []
        findings: list[Finding] = []

        # 1. Run MultiScannerEngine from nexcoder-security (static code, secrets, vulnerable deps, SBOM)
        t0 = time.perf_counter()
        scanner_engine = MultiScannerEngine(
            target_gate=self.target_gate,
            audit_log=self.target_gate.audit_log,
        )
        scan_result = scanner_engine.scan(
            target_path=target_root,
            enabled_scanners=scanners,
            force_offline=offline,
            owned_target=owned_target,
            authorized_by=authorized_by,
            approval_token=approval_token,
        )
        scan_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        findings.extend(scan_result.findings)

        test_cases.append(
            TestCaseExecution(
                test_id=f"{agent_id}:sec:static_scanners",
                scope=TestScope.SECURITY,
                name="test_security_static_and_dependency_scanners",
                target=str(target_root),
                passed=not scan_result.has_high_or_critical(),
                duration_ms=scan_ms,
                assertions_checked=max(1, len(scanners or list(scanner_engine.scanners.keys()))),
                error_message=(
                    f"{len(scan_result.findings)} security scanner finding(s) detected"
                    if scan_result.has_high_or_critical()
                    else None
                ),
                details={"total_scanner_findings": len(scan_result.findings)},
            )
        )

        # 2. Check application log files for leaked secrets (redacting actual values)
        root_resolved = target_root.resolve()
        for log_file in sorted(root_resolved.rglob("*.log")):
            resolved_log = resolve_inside(root_resolved, log_file)
            rel_log = str(resolved_log.relative_to(root_resolved)).replace("\\", "/")
            t_log = time.perf_counter()
            log_text = resolved_log.read_text(encoding="utf-8", errors="replace")
            leaked_in_log = False
            for label, pattern in _RESPONSE_SECRET_PATTERNS:
                if pattern.search(log_text):
                    leaked_in_log = True
                    redacted_preview = str(redact_secrets(log_text))[:160]
                    findings.append(
                        Finding(
                            id=f"SEC-LOG-SECRET-{rel_log}",
                            scanner="nexcoder-testing-security",
                            rule_id="SEC-LOG-LEAK-001",
                            title=f"Secret or token leaked in application log '{rel_log}' ({label})",
                            description=(
                                f"Detected unredacted {label} pattern inside log file '{rel_log}'. "
                                f"Redacted snippet: {redacted_preview}"
                            ),
                            severity=Severity.CRITICAL,
                            category=FindingCategory.SECRET,
                            location=Location(file_path=rel_log, line_start=1),
                            cwe_ids=["CWE-532"],
                            remediation=Remediation(
                                summary=(
                                    "Apply secret redaction filter (such as redact_secrets) "
                                    "before writing log events."
                                )
                            ),
                        )
                    )
            log_ms = round((time.perf_counter() - t_log) * 1000.0, 3)
            test_cases.append(
                TestCaseExecution(
                    test_id=f"{agent_id}:sec:log_leak:{rel_log}",
                    scope=TestScope.SECURITY,
                    name=f"test_security_log_redaction_{resolved_log.stem}",
                    target=rel_log,
                    passed=not leaked_in_log,
                    duration_ms=log_ms,
                    error_message="Secret pattern detected in log file" if leaked_in_log else None,
                )
            )

        # 3. Defensive HTTP security checks on application endpoints (headers, response secret leaks, stack traces)
        if requester is not None or base_url is not None:
            for ep in endpoints:
                method = ep.method.upper()
                target_id = f"{method} {ep.path}"
                t_ep = time.perf_counter()
                status, resp_headers, resp_body = self._http_dispatch(
                    method,
                    ep.path,
                    None,
                    ep.valid_payload,
                    requester=requester,
                    base_url=base_url,
                )
                ep_ms = round((time.perf_counter() - t_ep) * 1000.0, 3)
                lower_headers = {k.lower(): v for k, v in resp_headers.items()}

                # 3a. Security headers check
                missing_sec_headers = [
                    desc for h_key, desc in _REQUIRED_SECURITY_HEADERS if h_key not in lower_headers
                ]
                headers_ok = len(missing_sec_headers) == 0
                test_cases.append(
                    TestCaseExecution(
                        test_id=f"{agent_id}:sec:headers:{method}:{ep.path}",
                        scope=TestScope.SECURITY,
                        name=f"test_security_headers_{method.lower()}_{ep.path.strip('/').replace('/', '_') or 'root'}",
                        target=target_id,
                        passed=headers_ok,
                        duration_ms=ep_ms,
                        assertions_checked=len(_REQUIRED_SECURITY_HEADERS),
                        error_message=(
                            f"Missing security headers: {', '.join(missing_sec_headers)}"
                            if not headers_ok
                            else None
                        ),
                    )
                )
                if not headers_ok:
                    findings.append(
                        Finding(
                            id=f"SEC-HEADERS-{method}-{ep.path}",
                            scanner="nexcoder-testing-security",
                            rule_id="SEC-HEADER-001",
                            title=f"Missing defensive HTTP security headers on '{target_id}'",
                            description=(
                                f"Endpoint '{target_id}' omitted defensive headers: {', '.join(missing_sec_headers)}."
                            ),
                            severity=Severity.MEDIUM,
                            category=FindingCategory.COMPLIANCE,
                            location=Location(file_path=ep.path),
                            cwe_ids=["CWE-693"],
                            remediation=Remediation(
                                summary=(
                                    "Configure HTTP response middleware to set Content-Security-Policy, "
                                    "X-Content-Type-Options: nosniff, and X-Frame-Options: DENY."
                                )
                            ),
                        )
                    )

                # 3b. Secret leakage in HTTP response body
                leaked_in_resp = False
                for label, pattern in _RESPONSE_SECRET_PATTERNS:
                    if pattern.search(resp_body):
                        leaked_in_resp = True
                        redacted_body = str(redact_secrets(resp_body))[:160]
                        findings.append(
                            Finding(
                                id=f"SEC-RESP-SECRET-{method}-{ep.path}",
                                scanner="nexcoder-testing-security",
                                rule_id="SEC-RESP-LEAK-001",
                                title=f"Secret or credential leaked in HTTP response from '{target_id}'",
                                description=(
                                    f"Response from '{target_id}' exposed a {label} pattern. "
                                    f"Redacted response: {redacted_body}"
                                ),
                                severity=Severity.CRITICAL,
                                category=FindingCategory.SECRET,
                                location=Location(file_path=ep.path),
                                cwe_ids=["CWE-200", "CWE-522"],
                                remediation=Remediation(
                                    summary=(
                                        "Remove debug/internal credentials from API responses and "
                                        "serialize only public DTO fields."
                                    )
                                ),
                            )
                        )
                test_cases.append(
                    TestCaseExecution(
                        test_id=f"{agent_id}:sec:resp_secret:{method}:{ep.path}",
                        scope=TestScope.SECURITY,
                        name=f"test_security_response_no_secrets_{ep.path.strip('/').replace('/', '_') or 'root'}",
                        target=target_id,
                        passed=not leaked_in_resp,
                        duration_ms=1.0,
                        error_message="Secret pattern leaked in HTTP response" if leaked_in_resp else None,
                    )
                )

                # 3c. Malformed input / stack trace exposure probe
                t_mal = time.perf_counter()
                mal_status, _, mal_body = self._http_dispatch(
                    "POST",
                    ep.path,
                    {"Content-Type": "application/json"},
                    "__malformed__",
                    requester=requester,
                    base_url=base_url,
                )
                mal_ms = round((time.perf_counter() - t_mal) * 1000.0, 3)
                leaked_trace = mal_status >= 500 or "Traceback (most recent call last)" in mal_body
                test_cases.append(
                    TestCaseExecution(
                        test_id=f"{agent_id}:sec:malformed_input:{ep.path}",
                        scope=TestScope.SECURITY,
                        name=f"test_security_malformed_input_{ep.path.strip('/').replace('/', '_') or 'root'}",
                        target=f"POST {ep.path}",
                        passed=not leaked_trace,
                        duration_ms=mal_ms,
                        error_message=(
                            f"Malformed input caused HTTP {mal_status} or stack trace leak"
                            if leaked_trace
                            else None
                        ),
                    )
                )
                if leaked_trace:
                    findings.append(
                        Finding(
                            id=f"SEC-STACKTRACE-{ep.path}",
                            scanner="nexcoder-testing-security",
                            rule_id="SEC-ERR-LEAK-001",
                            title=f"Unhandled error or stack trace exposure on 'POST {ep.path}'",
                            description=(
                                f"Sending malformed input to 'POST {ep.path}' returned HTTP {mal_status} "
                                "with internal traceback details."
                            ),
                            severity=Severity.HIGH,
                            category=FindingCategory.SAST,
                            location=Location(file_path=ep.path),
                            cwe_ids=["CWE-209"],
                            remediation=Remediation(
                                summary=(
                                    "Catch parsing/validation errors globally and return generic "
                                    "400/422 JSON error responses without stack traces."
                                )
                            ),
                        )
                    )

        # Evaluate combined findings against SecurityGateEvaluator from nexcoder-security
        combined_scan = scan_result.model_copy(update={"findings": findings})
        evaluator = SecurityGateEvaluator(
            default_policy=GatePolicy(
                name="extreme-testing-gate",
                max_critical=0,
                max_high=0,
                block_on_secrets=True,
                allow_fallbacks=True,
            )
        )
        verdict = evaluator.evaluate(combined_scan, sbom=scan_result.sbom)

        return test_cases, findings, verdict
