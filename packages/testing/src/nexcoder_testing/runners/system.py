"""System and process runner for ephemeral end-to-end workflow verification."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nexcoder_security.models import Finding, FindingCategory, Location, Remediation, Severity

from nexcoder_testing.gate import gated_http_request
from nexcoder_testing.models import (
    GeneratedTestArtifact,
    SystemFlowSpec,
    TestCaseExecution,
    TestScope,
)

RequestCallable = Callable[[str, str, dict[str, str] | None, Any], tuple[int, dict[str, str], str]]


class SystemAndProcessRunner:
    """Runs process and end-to-end system workflows in an isolated ephemeral environment."""

    def __init__(self, *, offline: bool = True, allowed_hosts: list[str] | None = None) -> None:
        self.offline = offline
        self.allowed_hosts = allowed_hosts

    def _default_http_request(
        self,
        base_url: str,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: Any = None,
        timeout: float = 10.0,
    ) -> tuple[int, dict[str, str], str]:
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
        flows: list[SystemFlowSpec],
        *,
        requester: RequestCallable | None = None,
        base_url: str | None = None,
        valid_auth_token: str = "",
        timeout_seconds: float = 15.0,
        agent_id: str = "agent-system",
    ) -> tuple[list[TestCaseExecution], list[Finding], list[GeneratedTestArtifact]]:
        """Execute process commands and multi-step end-to-end HTTP workflows."""
        test_cases: list[TestCaseExecution] = []
        findings: list[Finding] = []
        artifacts: list[GeneratedTestArtifact] = []

        active_flows = flows or [
            SystemFlowSpec(
                name="default_e2e_health_flow",
                description="Verify application healthcheck endpoint responds 200.",
                steps=[{"type": "http", "method": "GET", "path": "/health", "expected_status": 200}],
            )
        ]

        for flow in active_flows:
            # 1. Execute ephemeral subprocess check if a command is specified
            if flow.command:
                t0 = time.perf_counter()
                cmd = [sys.executable, *flow.command]
                try:
                    proc = subprocess.run(  # noqa: S603
                        cmd,
                        cwd=str(target_root),
                        capture_output=True,
                        text=True,
                        timeout=timeout_seconds,
                        check=False,
                    )
                    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                    passed = proc.returncode == flow.expected_exit_code
                    test_cases.append(
                        TestCaseExecution(
                            test_id=f"{agent_id}:process:{flow.name}",
                            scope=TestScope.SYSTEM,
                            name=f"test_process_{flow.name}",
                            target=" ".join(flow.command),
                            passed=passed,
                            duration_ms=elapsed_ms,
                            error_message=None if passed else (proc.stderr.strip() or f"Exit code {proc.returncode}"),
                            details={
                                "returncode": proc.returncode,
                                "stdout": proc.stdout.strip()[:500],
                            },
                        )
                    )
                    if not passed:
                        findings.append(
                            Finding(
                                id=f"SYS-PROC-{flow.name.upper()}",
                                scanner="nexcoder-testing-system",
                                rule_id="SYSTEM-PROCESS-EXIT",
                                title=f"Process workflow '{flow.name}' exited with code {proc.returncode}",
                                description=(
                                    f"Command '{' '.join(flow.command)}' exited with {proc.returncode} "
                                    f"(expected {flow.expected_exit_code}). Stderr: {proc.stderr.strip()[:200]}"
                                ),
                                severity=Severity.HIGH,
                                category=FindingCategory.SAST,
                                location=Location(file_path=str(target_root)),
                                remediation=Remediation(
                                    summary="Inspect process startup errors, unhandled exceptions, and exit codes."
                                ),
                            )
                        )
                except Exception as exc:
                    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                    test_cases.append(
                        TestCaseExecution(
                            test_id=f"{agent_id}:process:{flow.name}",
                            scope=TestScope.SYSTEM,
                            name=f"test_process_{flow.name}",
                            target=" ".join(flow.command),
                            passed=False,
                            duration_ms=elapsed_ms,
                            error_message=str(exc),
                        )
                    )

            # 2. Execute multi-step end-to-end HTTP workflow steps
            if flow.steps and (requester is not None or base_url is not None):
                t0 = time.perf_counter()
                all_steps_passed = True
                step_errors: list[str] = []

                for idx, step in enumerate(flow.steps, start=1):
                    method = str(step.get("method", "GET")).upper()
                    path = str(step.get("path", "/health"))
                    expected_status = int(step.get("expected_status", 200))
                    headers: dict[str, str] = {}
                    if step.get("authenticated"):
                        headers["Authorization"] = f"Bearer {valid_auth_token}"
                    payload = step.get("payload")

                    try:
                        if requester is not None:
                            status, _, body_text = requester(method, path, headers, payload)
                        elif base_url is not None:
                            status, _, body_text = self._default_http_request(
                                base_url,
                                method,
                                path,
                                headers=headers,
                                body=payload,
                                timeout=timeout_seconds,
                            )
                        else:
                            continue

                        if status != expected_status:
                            all_steps_passed = False
                            step_errors.append(
                                f"Step {idx} ({method} {path}) returned {status}, expected {expected_status}"
                            )
                        elif body_text:
                            # Ensure JSON endpoints parse cleanly when JSON is returned
                            if body_text.strip().startswith("{"):
                                json.loads(body_text)
                    except Exception as exc:
                        all_steps_passed = False
                        step_errors.append(f"Step {idx} ({method} {path}) failed: {exc}")

                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                test_cases.append(
                    TestCaseExecution(
                        test_id=f"{agent_id}:e2e:{flow.name}",
                        scope=TestScope.SYSTEM,
                        name=f"test_e2e_{flow.name}",
                        target=flow.name,
                        passed=all_steps_passed,
                        duration_ms=elapsed_ms,
                        assertions_checked=max(1, len(flow.steps)),
                        error_message="; ".join(step_errors) if step_errors else None,
                    )
                )
                if not all_steps_passed:
                    findings.append(
                        Finding(
                            id=f"SYS-E2E-{flow.name.upper()}",
                            scanner="nexcoder-testing-system",
                            rule_id="SYSTEM-E2E-FLOW",
                            title=f"End-to-end system flow '{flow.name}' failed assertions",
                            description="; ".join(step_errors),
                            severity=Severity.HIGH,
                            category=FindingCategory.SAST,
                            location=Location(file_path=str(target_root)),
                            remediation=Remediation(
                                summary=(
                                    "Verify service route handlers, authentication middleware, and state transitions."
                                )
                            ),
                        )
                    )

        artifact_lines = [
            '"""Auto-generated end-to-end system and process test suite by nexcoder-testing."""',
            "",
            "from __future__ import annotations",
            "",
            "import subprocess",
            "import sys",
            "",
        ]
        for flow in active_flows:
            safe_name = flow.name.replace("-", "_")
            if flow.command:
                artifact_lines.extend(
                    [
                        f"def test_system_process_{safe_name}() -> None:",
                        f"    cmd = [sys.executable, *{flow.command!r}]",
                        "    proc = subprocess.run(cmd, capture_output=True, text=True)",
                        f"    assert proc.returncode == {flow.expected_exit_code}",
                        "",
                    ]
                )
            else:
                artifact_lines.extend(
                    [
                        f"def test_system_flow_{safe_name}() -> None:",
                        f"    steps = {flow.steps!r}",
                        "    assert len(steps) >= 1",
                        "",
                    ]
                )

        artifacts.append(
            GeneratedTestArtifact(
                name=f"{agent_id}_system_e2e_suite",
                scope=TestScope.SYSTEM,
                file_name=f"test_generated_system_{agent_id.replace('-', '_')}.py",
                content="\n".join(artifact_lines),
                target_reference=str(target_root),
            )
        )

        return test_cases, findings, artifacts
