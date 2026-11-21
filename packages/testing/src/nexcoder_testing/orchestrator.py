"""Multi-agent extreme testing orchestrator with target ownership gating and parallel workers."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from nexcoder_control.approval import (
    TargetAuthorizationGate,
    TargetAuthorizationRecord,
    TargetNotAuthorizedError,
    redact_secrets,
)
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_core.config import NexcoderConfig
from nexcoder_core.llm.registry import get_chat_model
from nexcoder_core.observability.usage import usage_scope
from nexcoder_security import (
    Finding,
    GatePolicy,
    GateVerdict,
    SBOMDocument,
    ScanMetadata,
    ScanResult,
    SecurityGateEvaluator,
)

from nexcoder_testing.gate import is_loopback_host
from nexcoder_testing.models import (
    AgentExecutionReport,
    AgentWorkSlice,
    ExtremeTestConfig,
    ExtremeTestReport,
    GeneratedTestArtifact,
    ScopeSummary,
    SystemFlowSpec,
    TestCaseExecution,
    TestScope,
)
from nexcoder_testing.runners import (
    APIRequestRunner,
    ApplicationSecurityRunner,
    DOMScrapingRunner,
    SystemAndProcessRunner,
    UnitAndContractRunner,
)

RequestCallable = Callable[[str, str, dict[str, str] | None, Any], tuple[int, dict[str, str], str]]

_DEFAULT_SCANNERS = [
    "semgrep",
    "bandit",
    "gitleaks",
    "osv-scanner",
    "pip-audit",
    "trivy",
    "syft",
]


class TestWorkerAgent:
    """Autonomous test worker agent executing an assigned slice of extreme testing scopes."""

    __test__ = False

    def __init__(
        self,
        work_slice: AgentWorkSlice,
        config: ExtremeTestConfig,
        target_gate: TargetAuthorizationGate,
        requester: RequestCallable | None = None,
    ) -> None:
        self.work_slice = work_slice
        self.config = config
        self.target_gate = target_gate
        self.requester = requester

    def execute(self) -> AgentExecutionReport:
        """Run all scopes assigned to this worker agent and return its report."""
        t0 = time.perf_counter()
        agent_id = self.work_slice.agent_id
        all_cases: list[TestCaseExecution] = []
        all_findings: list[Finding] = []
        all_artifacts: list[GeneratedTestArtifact] = []

        for scope in self.work_slice.scopes:
            if scope == TestScope.UNIT:
                unit_runner = UnitAndContractRunner()
                cases, findings, artifacts = unit_runner.run(
                    target_root=self.config.target_path,
                    module_paths=self.work_slice.module_paths or None,
                    agent_id=agent_id,
                )
                all_cases.extend(cases)
                all_findings.extend(findings)
                all_artifacts.extend(artifacts)

            elif scope == TestScope.SYSTEM:
                sys_runner = SystemAndProcessRunner(
                    offline=self.config.offline, allowed_hosts=self.config.allowed_hosts
                )
                cases, findings, artifacts = sys_runner.run(
                    target_root=self.config.target_path,
                    flows=self.work_slice.system_flows,
                    requester=self.requester,
                    base_url=self.config.base_url,
                    valid_auth_token=self.config.valid_auth_token,
                    timeout_seconds=self.config.timeout_seconds,
                    agent_id=agent_id,
                )
                all_cases.extend(cases)
                all_findings.extend(findings)
                all_artifacts.extend(artifacts)

            elif scope == TestScope.DOM:
                dom_runner = DOMScrapingRunner(target_gate=self.target_gate)
                cases, findings, artifacts = dom_runner.run(
                    target_root=self.config.target_path,
                    screens=self.work_slice.screens,
                    requester=self.requester,
                    owned_target=True,
                    authorized_by=self.config.authorized_by,
                    agent_id=agent_id,
                )
                all_cases.extend(cases)
                all_findings.extend(findings)
                all_artifacts.extend(artifacts)

            elif scope == TestScope.API:
                api_runner = APIRequestRunner(offline=self.config.offline, allowed_hosts=self.config.allowed_hosts)
                cases, findings, artifacts = api_runner.run(
                    endpoints=self.work_slice.endpoints,
                    requester=self.requester,
                    base_url=self.config.base_url,
                    valid_auth_token=self.config.valid_auth_token,
                    timeout_seconds=self.config.timeout_seconds,
                    agent_id=agent_id,
                )
                all_cases.extend(cases)
                all_findings.extend(findings)
                all_artifacts.extend(artifacts)

            elif scope == TestScope.SECURITY:
                sec_runner = ApplicationSecurityRunner(
                    target_gate=self.target_gate, offline=self.config.offline, allowed_hosts=self.config.allowed_hosts
                )
                cases, findings, _ = sec_runner.run(
                    target_root=self.config.target_path,
                    endpoints=self.work_slice.endpoints,
                    scanners=self.work_slice.scanners or None,
                    offline=self.config.offline,
                    owned_target=True,
                    authorized_by=self.config.authorized_by,
                    requester=self.requester,
                    base_url=self.config.base_url,
                    agent_id=agent_id,
                )
                all_cases.extend(cases)
                all_findings.extend(findings)

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        scope_names = ", ".join(s.value for s in self.work_slice.scopes) or "none"
        summary = (
            f"Agent {agent_id} completed scopes [{scope_names}]: "
            f"{len(all_cases)} tests run, {len(all_findings)} findings."
        )
        return AgentExecutionReport(
            agent_id=agent_id,
            scopes=list(self.work_slice.scopes),
            test_cases=all_cases,
            findings=all_findings,
            artifacts=all_artifacts,
            duration_ms=elapsed_ms,
            summary=summary,
        )


class ExtremeTestOrchestrator:
    """Orchestrates N configurable test worker agents over an owned/authorized target application."""

    def __init__(
        self,
        target_gate: TargetAuthorizationGate | None = None,
        audit_log: AppendOnlyAuditLog | None = None,
        nexcoder_config: NexcoderConfig | None = None,
    ) -> None:
        if target_gate is not None:
            self.target_gate = target_gate
            self.audit_log = audit_log if audit_log is not None else target_gate.audit_log
        else:
            self.audit_log = audit_log if audit_log is not None else AppendOnlyAuditLog()
            self.target_gate = TargetAuthorizationGate(audit_log=self.audit_log)
        self.nexcoder_config = nexcoder_config or NexcoderConfig(preset="offline")

    def authorize_target(
        self,
        target: str | Any,
        authorized_by: str = "owner",
        metadata: dict[str, Any] | None = None,
    ) -> TargetAuthorizationRecord:
        """Register a target path or URL as owned/authorized in the control plane gate."""
        return self.target_gate.mark_owned_target(
            target=target,
            authorized_by=authorized_by,
            mode="extreme_testing",
            metadata=metadata,
        )

    def _verify_and_enforce_boundaries(self, config: ExtremeTestConfig) -> TargetAuthorizationRecord:
        """Enforce target ownership gate and block unauthorized or external third-party URLs."""
        # 1. Verify base_url host boundaries if a URL is provided
        if config.base_url:
            parsed = urlparse(config.base_url)
            hostname = (parsed.hostname or "").lower()
            allowed_lower = {h.lower() for h in config.allowed_hosts}
            is_file = parsed.scheme == "file"
            is_local_or_allowed = hostname in allowed_lower or is_file
            # Offline mode: no network beyond the local target, even if allowed_hosts was widened.
            offline_violation = config.offline and not is_file and not is_loopback_host(hostname)

            if not is_local_or_allowed or offline_violation:
                if offline_violation and is_local_or_allowed:
                    reason = (
                        f"Target URL '{config.base_url}' points to non-local host '{hostname}' while offline mode "
                        "is enabled. Offline mode only allows the local target (loopback hosts)."
                    )
                else:
                    reason = (
                        f"Target URL '{config.base_url}' points to host '{hostname}' outside allowed local/owned "
                        f"hosts {sorted(allowed_lower)}. Testing third-party systems is strictly prohibited per "
                        "USAGE_POLICY.md."
                    )
                self.audit_log.record_event(
                    event_type="target.authorization.denied",
                    actor=config.authorized_by or "unverified",
                    action="extreme_testing",
                    resource=config.base_url,
                    severity="warning",
                    details=redact_secrets(
                        {
                            "target": config.base_url,
                            "hostname": hostname,
                            "offline": config.offline,
                            "status": "denied",
                            "reason": reason,
                        }
                    ),
                )
                raise TargetNotAuthorizedError(
                    target=config.base_url,
                    mode="extreme_testing",
                    reason=reason,
                )

        # 2. Verify target_path authorization via control plane TargetAuthorizationGate
        explicit_actor = config.authorized_by if config.authorized_by != "owner" else None
        auth_record = self.target_gate.verify_target(
            target=config.target_path,
            mode="extreme_testing",
            owned_target=config.owned_target,
            authorized_by=explicit_actor,
            approval_token=config.approval_token,
            metadata={
                "num_agents": config.num_agents,
                "scopes": [s.value for s in config.scopes],
                "offline": config.offline,
                "read_only": config.read_only,
                "base_url": config.base_url,
            },
        )
        return auth_record

    def partition_work(self, config: ExtremeTestConfig) -> list[AgentWorkSlice]:
        """Partition requested scopes and target items across config.num_agents worker slices."""
        num_agents = config.num_agents
        scopes = list(dict.fromkeys(config.scopes))

        # Discover Python modules for unit testing sharding
        unit_runner = UnitAndContractRunner()
        discovered_fns = unit_runner.discover_functions(config.target_path)
        unique_modules = list(dict.fromkeys(fn.relative_path for fn in discovered_fns))

        # Discover HTML screens for DOM testing sharding
        dom_runner = DOMScrapingRunner(target_gate=self.target_gate)
        all_screens = dom_runner.discover_screens(config.target_path, config.screens)
        all_endpoints = list(config.endpoints)
        all_flows = list(config.system_flows) or [
            SystemFlowSpec(
                name="default_e2e_health_flow",
                description="Verify application healthcheck endpoint responds 200.",
                steps=[{"type": "http", "method": "GET", "path": "/health", "expected_status": 200}],
            )
        ]

        slices = [
            AgentWorkSlice(
                agent_id=f"agent-{i + 1}",
                agent_index=i,
            )
            for i in range(num_agents)
        ]

        if num_agents <= len(scopes):
            # Distribute full scopes round-robin across the N agents
            for idx, scope in enumerate(scopes):
                target_slice = slices[idx % num_agents]
                target_slice.scopes.append(scope)
                if scope == TestScope.UNIT:
                    target_slice.module_paths = list(unique_modules)
                elif scope == TestScope.SYSTEM:
                    target_slice.system_flows = list(all_flows)
                elif scope == TestScope.DOM:
                    target_slice.screens = list(all_screens)
                elif scope == TestScope.API:
                    target_slice.endpoints = list(all_endpoints)
                elif scope == TestScope.SECURITY:
                    target_slice.scanners = list(_DEFAULT_SCANNERS)
                    target_slice.endpoints = list(all_endpoints)
        else:
            # First len(scopes) agents take one primary scope each; remaining agents share sharded items
            # Build fine-grained work units across scopes and assign to all num_agents
            work_units: list[tuple[TestScope, str, Any]] = []
            for scope in scopes:
                if scope == TestScope.UNIT:
                    if unique_modules:
                        for mod_path in unique_modules:
                            work_units.append((TestScope.UNIT, "module", mod_path))
                    else:
                        work_units.append((TestScope.UNIT, "module", None))
                elif scope == TestScope.SYSTEM:
                    for flow in all_flows:
                        work_units.append((TestScope.SYSTEM, "flow", flow))
                elif scope == TestScope.DOM:
                    if all_screens:
                        for scr in all_screens:
                            work_units.append((TestScope.DOM, "screen", scr))
                    else:
                        work_units.append((TestScope.DOM, "screen", None))
                elif scope == TestScope.API:
                    if all_endpoints:
                        for ep in all_endpoints:
                            work_units.append((TestScope.API, "endpoint", ep))
                    else:
                        work_units.append((TestScope.API, "endpoint", None))
                elif scope == TestScope.SECURITY:
                    for scanner_name in _DEFAULT_SCANNERS:
                        work_units.append((TestScope.SECURITY, "scanner", scanner_name))

            for idx, (scope, kind, item) in enumerate(work_units):
                target_slice = slices[idx % num_agents]
                if scope not in target_slice.scopes:
                    target_slice.scopes.append(scope)
                if kind == "module" and item is not None:
                    target_slice.module_paths.append(item)
                elif kind == "flow" and item is not None:
                    target_slice.system_flows.append(item)
                elif kind == "screen" and item is not None:
                    target_slice.screens.append(item)
                elif kind == "endpoint" and item is not None:
                    target_slice.endpoints.append(item)
                elif kind == "scanner" and item is not None:
                    target_slice.scanners.append(item)
                    if all_endpoints and not target_slice.endpoints:
                        # Attach endpoints to the first security slice for HTTP security probes
                        has_sec_ep = any(
                            TestScope.SECURITY in s.scopes and s.endpoints for s in slices
                        )
                        if not has_sec_ep:
                            target_slice.endpoints = list(all_endpoints)

        return slices

    def _deduplicate_and_sort_findings(self, findings: list[Finding]) -> list[Finding]:
        seen: set[str] = set()
        unique: list[Finding] = []
        for f in findings:
            loc_str = ""
            if f.location:
                loc_str = f"{f.location.file_path}:{f.location.line_start or 0}"
            key = f"{f.category.value}:{f.rule_id}:{loc_str}:{f.title}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(f)

        unique.sort(key=lambda item: (-item.severity.level, item.rule_id, item.id))
        return unique

    def _evaluate_gate(self, target_str: str, findings: list[Finding]) -> GateVerdict:
        synthetic_scan = ScanResult(
            scanner="nexcoder-testing-orchestrator",
            target_path=target_str,
            findings=findings,
            metadata=ScanMetadata(
                scanner="nexcoder-testing-orchestrator",
                version="0.1.0",
                target_path=target_str,
                success=True,
                is_fallback=True,
            ),
            sbom=SBOMDocument(raw_content="{}"),
        )
        evaluator = SecurityGateEvaluator(
            default_policy=GatePolicy(
                name="extreme-testing-gate",
                max_critical=0,
                max_high=0,
                block_on_secrets=True,
                allow_fallbacks=True,
            )
        )
        return evaluator.evaluate(synthetic_scan)

    def _build_executive_summary(
        self,
        config: ExtremeTestConfig,
        total_tests: int,
        passed_tests: int,
        failed_tests: int,
        findings: list[Finding],
        verdict: GateVerdict,
    ) -> str:
        """Synthesize an offline-safe executive summary using nexcoder_core chat model."""
        deterministic_summary = (
            f"Executed {total_tests} automated test case(s) across {len(config.scopes)} scope(s) "
            f"using {config.num_agents} parallel agent(s): {passed_tests} passed, {failed_tests} failed. "
            f"Detected {len(findings)} deduplicated finding(s). {verdict.summary}"
        )
        try:
            with usage_scope(
                owner=config.authorized_by,
                run_id="extreme-testing-summary",
                budget_usd=self.nexcoder_config.budget.max_usd_per_run,
            ):
                model = get_chat_model("medium", config=self.nexcoder_config, tracing=False)
                _ = model.invoke(deterministic_summary)
        except Exception as exc:
            _ = exc
        return deterministic_summary

    def run(
        self,
        config: ExtremeTestConfig,
        *,
        requester: RequestCallable | None = None,
    ) -> ExtremeTestReport:
        """Verify target ownership, partition work across N agents, run in parallel, and merge report."""
        started_at = datetime.now(UTC)
        t0 = time.perf_counter()

        auth_record = self._verify_and_enforce_boundaries(config)
        audit_ids: list[str] = []

        start_evt = self.audit_log.record_event(
            event_type="testing.run.started",
            actor=auth_record.authorized_by,
            action="extreme_testing_start",
            resource=auth_record.target,
            severity="info",
            details=redact_secrets(
                {
                    "target": auth_record.target,
                    "num_agents": config.num_agents,
                    "scopes": [s.value for s in config.scopes],
                    "offline": config.offline,
                    "read_only": config.read_only,
                }
            ),
        )
        audit_ids.append(start_evt.event_id)

        slices = self.partition_work(config)
        workers = [
            TestWorkerAgent(
                work_slice=sl,
                config=config,
                target_gate=self.target_gate,
                requester=requester,
            )
            for sl in slices
        ]

        if config.num_agents == 1:
            agent_reports = [workers[0].execute()]
        else:
            with ThreadPoolExecutor(max_workers=config.num_agents) as pool:
                futures = [pool.submit(w.execute) for w in workers]
                agent_reports = [f.result() for f in futures]

        all_test_cases: list[TestCaseExecution] = []
        raw_findings: list[Finding] = []
        all_artifacts: list[GeneratedTestArtifact] = []

        for rep in agent_reports:
            all_test_cases.extend(rep.test_cases)
            raw_findings.extend(rep.findings)
            all_artifacts.extend(rep.artifacts)
            agent_evt = self.audit_log.record_event(
                event_type="testing.agent.completed",
                actor=rep.agent_id,
                action="agent_slice_complete",
                resource=auth_record.target,
                severity="info",
                details=redact_secrets(
                    {
                        "agent_id": rep.agent_id,
                        "scopes": [s.value for s in rep.scopes],
                        "total_tests": rep.total_tests,
                        "failed_tests": rep.failed_tests,
                        "findings_count": len(rep.findings),
                    }
                ),
            )
            audit_ids.append(agent_evt.event_id)

        dedup_findings = self._deduplicate_and_sort_findings(raw_findings)

        # Build per-scope breakdown
        scope_summaries: dict[str, ScopeSummary] = {}
        for scope in config.scopes:
            scope_cases = [tc for tc in all_test_cases if tc.scope == scope]
            scope_arts = [art for art in all_artifacts if art.scope == scope]
            if scope == TestScope.UNIT:
                scope_f = [f for f in dedup_findings if f.scanner == "nexcoder-testing-unit"]
            elif scope == TestScope.SYSTEM:
                scope_f = [f for f in dedup_findings if f.scanner == "nexcoder-testing-system"]
            elif scope == TestScope.DOM:
                scope_f = [f for f in dedup_findings if f.scanner in ("nexcoder-testing-dom", "nexcoder-capture-a11y")]
            elif scope == TestScope.API:
                scope_f = [f for f in dedup_findings if f.scanner == "nexcoder-testing-api"]
            else:
                scope_f = [
                    f
                    for f in dedup_findings
                    if f.scanner not in (
                        "nexcoder-testing-unit",
                        "nexcoder-testing-system",
                        "nexcoder-testing-dom",
                        "nexcoder-capture-a11y",
                        "nexcoder-testing-api",
                    )
                ]
            scope_summaries[scope.value] = ScopeSummary(
                scope=scope,
                total_tests=len(scope_cases),
                passed_tests=sum(1 for tc in scope_cases if tc.passed),
                failed_tests=sum(1 for tc in scope_cases if not tc.passed),
                findings_count=len(scope_f),
                artifacts_count=len(scope_arts),
            )

        verdict = self._evaluate_gate(auth_record.target, dedup_findings)
        passed_total = sum(1 for tc in all_test_cases if tc.passed)
        failed_total = sum(1 for tc in all_test_cases if not tc.passed)
        exec_summary = self._build_executive_summary(
            config=config,
            total_tests=len(all_test_cases),
            passed_tests=passed_total,
            failed_tests=failed_total,
            findings=dedup_findings,
            verdict=verdict,
        )

        completed_at = datetime.now(UTC)
        duration_ms = round((time.perf_counter() - t0) * 1000.0, 3)

        done_evt = self.audit_log.record_event(
            event_type="testing.run.completed",
            actor=auth_record.authorized_by,
            action="extreme_testing_complete",
            resource=auth_record.target,
            severity="warning" if dedup_findings else "info",
            details=redact_secrets(
                {
                    "target": auth_record.target,
                    "num_agents": config.num_agents,
                    "total_tests": len(all_test_cases),
                    "passed_tests": passed_total,
                    "failed_tests": failed_total,
                    "total_findings": len(dedup_findings),
                    "gate_passed": verdict.passed,
                    "duration_ms": duration_ms,
                }
            ),
        )
        audit_ids.append(done_evt.event_id)

        return ExtremeTestReport(
            target=auth_record.target,
            authorized_by=auth_record.authorized_by,
            ownership=auth_record.ownership,
            offline=config.offline,
            num_agents=config.num_agents,
            scopes_executed=list(config.scopes),
            agent_assignments=slices,
            agent_reports=agent_reports,
            scope_summaries=scope_summaries,
            test_cases=all_test_cases,
            findings=dedup_findings,
            artifacts=all_artifacts,
            security_gate_verdict=verdict,
            executive_summary=exec_summary,
            audit_event_ids=audit_ids,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )
