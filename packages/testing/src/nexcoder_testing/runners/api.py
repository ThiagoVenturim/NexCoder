"""API and HTTP request testing runner for owned target endpoints."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from nexcoder_security.models import Finding, FindingCategory, Location, Remediation, Severity

from nexcoder_testing.gate import gated_http_request
from nexcoder_testing.models import (
    APIEndpointSpec,
    GeneratedTestArtifact,
    TestCaseExecution,
    TestScope,
)

RequestCallable = Callable[[str, str, dict[str, str] | None, Any], tuple[int, dict[str, str], str]]


class APIRequestRunner:
    """Exercises target API endpoints with valid, invalid, auth, schema, and boundary cases."""

    def __init__(self, *, offline: bool = True, allowed_hosts: list[str] | None = None) -> None:
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
            raise ValueError("Either requester or base_url must be provided for API testing")

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
        endpoints: list[APIEndpointSpec],
        *,
        requester: RequestCallable | None = None,
        base_url: str | None = None,
        valid_auth_token: str = "",
        timeout_seconds: float = 10.0,
        agent_id: str = "agent-api",
    ) -> tuple[list[TestCaseExecution], list[Finding], list[GeneratedTestArtifact]]:
        """Run valid, unauthenticated, invalid-schema, and boundary API checks."""
        test_cases: list[TestCaseExecution] = []
        findings: list[Finding] = []
        artifacts: list[GeneratedTestArtifact] = []

        if not endpoints:
            return test_cases, findings, artifacts

        for ep in endpoints:
            method = ep.method.upper()
            target_id = f"{method} {ep.path}"

            # 1. Valid request check (status, JSON schema keys, rate limit header)
            t0 = time.perf_counter()
            valid_headers: dict[str, str] = {}
            if ep.requires_auth:
                valid_headers["Authorization"] = f"Bearer {valid_auth_token}"

            status, resp_headers, resp_body = self._http_dispatch(
                method,
                ep.path,
                valid_headers,
                ep.valid_payload,
                requester=requester,
                base_url=base_url,
                timeout=timeout_seconds,
            )
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)

            schema_missing: list[str] = []
            parsed_json: Any = None
            if resp_body:
                try:
                    parsed_json = json.loads(resp_body)
                    if isinstance(parsed_json, dict):
                        schema_missing = [k for k in ep.expected_response_keys if k not in parsed_json]
                except json.JSONDecodeError:
                    if ep.expected_response_keys:
                        schema_missing = list(ep.expected_response_keys)

            header_map_lower = {k.lower(): v for k, v in resp_headers.items()}
            missing_rl_header = (
                ep.rate_limit_header is not None and ep.rate_limit_header.lower() not in header_map_lower
            )

            valid_passed = (status == ep.expected_status) and not schema_missing and not missing_rl_header
            err_reasons: list[str] = []
            if status != ep.expected_status:
                err_reasons.append(f"Expected status {ep.expected_status}, got {status}")
            if schema_missing:
                err_reasons.append(f"Missing response keys: {schema_missing}")
            if missing_rl_header:
                err_reasons.append(f"Missing rate limit header: {ep.rate_limit_header}")

            test_cases.append(
                TestCaseExecution(
                    test_id=f"{agent_id}:api:{method}:{ep.path}:valid",
                    scope=TestScope.API,
                    name=f"test_api_valid_{method.lower()}_{ep.path.strip('/').replace('/', '_') or 'root'}",
                    target=target_id,
                    passed=valid_passed,
                    duration_ms=elapsed_ms,
                    assertions_checked=1 + len(ep.expected_response_keys) + (1 if ep.rate_limit_header else 0),
                    error_message="; ".join(err_reasons) if err_reasons else None,
                    details={"status": status, "schema_missing": schema_missing},
                )
            )

            if not valid_passed:
                findings.append(
                    Finding(
                        id=f"API-CONTRACT-{method}-{ep.path}",
                        scanner="nexcoder-testing-api",
                        rule_id="API-CONTRACT-001",
                        title=f"Endpoint '{target_id}' failed contract assertions",
                        description="; ".join(err_reasons),
                        severity=Severity.MEDIUM,
                        category=FindingCategory.SAST,
                        location=Location(file_path=ep.path),
                        remediation=Remediation(
                            summary=(
                                "Ensure the endpoint returns the documented status code, "
                                "schema keys, and rate-limit headers."
                            )
                        ),
                    )
                )

            # 2. Authentication enforcement check when requires_auth=True
            if ep.requires_auth:
                t1 = time.perf_counter()
                unauth_status, _, _ = self._http_dispatch(
                    method,
                    ep.path,
                    {"Authorization": "Bearer invalid-unauthorized-token"},
                    ep.valid_payload,
                    requester=requester,
                    base_url=base_url,
                    timeout=timeout_seconds,
                )
                unauth_ms = round((time.perf_counter() - t1) * 1000.0, 3)
                auth_enforced = unauth_status in (401, 403)
                test_cases.append(
                    TestCaseExecution(
                        test_id=f"{agent_id}:api:{method}:{ep.path}:auth_gate",
                        scope=TestScope.API,
                        name=f"test_api_auth_{method.lower()}_{ep.path.strip('/').replace('/', '_') or 'root'}",
                        target=target_id,
                        passed=auth_enforced,
                        duration_ms=unauth_ms,
                        error_message=(
                            f"Protected endpoint returned {unauth_status} instead of 401/403"
                            if not auth_enforced
                            else None
                        ),
                        details={"unauth_status": unauth_status},
                    )
                )
                if not auth_enforced:
                    findings.append(
                        Finding(
                            id=f"API-AUTH-{method}-{ep.path}",
                            scanner="nexcoder-testing-api",
                            rule_id="API-AUTH-001",
                            title=f"Missing authentication enforcement on '{target_id}'",
                            description=(
                                f"Endpoint '{target_id}' is marked requires_auth=True "
                                f"but returned HTTP {unauth_status} "
                                "when called with an invalid authentication token."
                            ),
                            severity=Severity.HIGH,
                            category=FindingCategory.SAST,
                            location=Location(file_path=ep.path),
                            cwe_ids=["CWE-306", "CWE-287"],
                            remediation=Remediation(
                                summary=(
                                    "Enforce authentication middleware on the route and reject "
                                    "invalid/missing tokens with HTTP 401/403."
                                )
                            ),
                        )
                    )

            # 3. Invalid / malformed payload and boundary checks for mutating or parameterized endpoints
            if method in ("POST", "PUT", "PATCH") or ep.request_schema:
                oversized_dict = {
                    k: 99999999 if v == "int" else "x" * 2048 for k, v in ep.request_schema.items()
                }
                invalid_cases: list[tuple[str, Any]] = [
                    ("empty_payload", {}),
                    ("negative_boundary", {k: -1 if v == "int" else "" for k, v in ep.request_schema.items()}),
                    ("oversized_boundary", oversized_dict),
                    ("malformed_raw_json", "{malformed_json"),
                ]
                for case_label, bad_payload in invalid_cases:
                    t2 = time.perf_counter()
                    bad_status, _, bad_body = self._http_dispatch(
                        method,
                        ep.path,
                        valid_headers,
                        bad_payload,
                        requester=requester,
                        base_url=base_url,
                        timeout=timeout_seconds,
                    )
                    bad_ms = round((time.perf_counter() - t2) * 1000.0, 3)
                    handled_cleanly = 400 <= bad_status < 500
                    test_cases.append(
                        TestCaseExecution(
                            test_id=f"{agent_id}:api:{method}:{ep.path}:invalid:{case_label}",
                            scope=TestScope.API,
                            name=f"test_api_invalid_{case_label}_{ep.path.strip('/').replace('/', '_') or 'root'}",
                            target=target_id,
                            passed=handled_cleanly,
                            duration_ms=bad_ms,
                            error_message=(
                                f"Expected 4xx validation error for {case_label}, got HTTP {bad_status}"
                                if not handled_cleanly
                                else None
                            ),
                            details={"case": case_label, "status": bad_status},
                        )
                    )
                    if bad_status >= 500 or "Traceback" in bad_body:
                        findings.append(
                            Finding(
                                id=f"API-500-{method}-{ep.path}-{case_label.upper()}",
                                scanner="nexcoder-testing-api",
                                rule_id="API-ERR-500",
                                title=f"Unhandled server error (HTTP {bad_status}) on '{target_id}' with {case_label}",
                                description=(
                                    f"Endpoint '{target_id}' returned HTTP {bad_status} "
                                    f"when given invalid input ({case_label})."
                                ),
                                severity=Severity.HIGH,
                                category=FindingCategory.SAST,
                                location=Location(file_path=ep.path),
                                cwe_ids=["CWE-20", "CWE-209"],
                                remediation=Remediation(
                                    summary=(
                                        "Validate request payloads with a schema validator (such as Pydantic) "
                                        "and return HTTP 400/422 without stack traces."
                                    )
                                ),
                            )
                        )

        # Synthesize an executable pytest API contract test artifact
        lines = [
            '"""Auto-generated API contract and boundary test suite by nexcoder-testing."""',
            "",
            "from __future__ import annotations",
            "",
        ]
        for ep in endpoints:
            safe_ep = ep.path.strip("/").replace("/", "_") or "root"
            lines.extend(
                [
                    f"def test_api_contract_{ep.method.lower()}_{safe_ep}() -> None:",
                    f"    endpoint = {ep.model_dump()!r}",
                    "    assert endpoint['expected_status'] in (200, 201, 202, 204)",
                    "",
                ]
            )
        artifacts.append(
            GeneratedTestArtifact(
                name=f"{agent_id}_api_contract_suite",
                scope=TestScope.API,
                file_name=f"test_generated_api_{agent_id.replace('-', '_')}.py",
                content="\n".join(lines),
                target_reference=base_url or "in_process_api",
            )
        )

        return test_cases, findings, artifacts
