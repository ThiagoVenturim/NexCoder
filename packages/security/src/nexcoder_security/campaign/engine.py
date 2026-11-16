"""Control plane engine for security and quality test campaign orchestration."""

from __future__ import annotations

import concurrent.futures
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nexcoder_control.approval import (
    AuthorizationDocument,
    TargetAuthorizationGate,
    TargetAuthorizationRecord,
    TargetNotAuthorizedError,
    is_local_or_owned_target,
    verify_signed_document,
)
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_control.metering.budgets import BudgetPolicy
from nexcoder_control.metering.cost_tracker import CostTracker

from nexcoder_security.campaign.agents import build_test_agent
from nexcoder_security.campaign.models import (
    AgentExecutionResult,
    CampaignConfig,
    CampaignReport,
    CampaignStatus,
    TestFinding,
)
from nexcoder_security.campaign.registry import CampaignRegistry, get_global_registry


class SecurityTestCampaignEngine:
    """Orchestrates multi-agent test campaigns with target authorization and budget controls."""

    def __init__(
        self,
        audit_log: AppendOnlyAuditLog | None = None,
        target_gate: TargetAuthorizationGate | None = None,
        cost_tracker: CostTracker | None = None,
        registry: CampaignRegistry | None = None,
        trusted_public_keys: list[str] | set[str] | None = None,
    ) -> None:
        self.audit_log = audit_log if audit_log is not None else AppendOnlyAuditLog()
        self.target_gate = (
            target_gate
            if target_gate is not None
            else TargetAuthorizationGate(
                audit_log=self.audit_log,
                trusted_public_keys=trusted_public_keys,
            )
        )
        self.cost_tracker = cost_tracker if cost_tracker is not None else CostTracker()
        self.registry = registry if registry is not None else get_global_registry()
        self.trusted_public_keys = set(trusted_public_keys or [])

    def add_trusted_public_key(self, public_key: str) -> None:
        """Register a trusted Ed25519 public key for signed authorization verification."""
        clean = public_key.strip()
        if clean:
            self.trusted_public_keys.add(clean)
            self.target_gate.add_trusted_public_key(clean)

    def _verify_authorization(self, config: CampaignConfig) -> TargetAuthorizationRecord:
        """Verify that the target is owned or authorized via cryptographic document (#106)."""
        target = config.target.strip()
        is_local = is_local_or_owned_target(target)
        requires_doc = config.require_signed_document or (
            not is_local and not config.owned_target and not self.target_gate.is_target_authorized(target)
        )

        doc = config.authorization_document
        if doc is not None and not isinstance(doc, AuthorizationDocument):
            if isinstance(doc, dict):
                doc = AuthorizationDocument(**doc)
            elif isinstance(doc, (str, Path)):
                from nexcoder_control.approval import load_authorization_document

                doc = load_authorization_document(doc)

        if doc is not None:
            # Cryptographic signed doc verification (#106)
            verify_signed_document(
                doc,
                trusted_public_keys=self.trusted_public_keys,
                target=target,
                action="security_test_campaign",
            )

        return self.target_gate.verify_target(
            target=target,
            mode="security_test_campaign",
            owned_target=config.owned_target,
            authorized_by=config.authorized_by,
            authorization_document=doc,
            require_signed_document=requires_doc,
            metadata={
                "campaign_id": config.campaign_id,
                "agent_count": config.agent_count,
                "test_types": [t.value for t in config.test_types],
                "budget_max_usd": config.budget.max_cost_usd,
            },
        )

    def run_campaign(
        self,
        config: CampaignConfig,
        *,
        raise_on_auth_failure: bool = True,
    ) -> CampaignReport:
        """Execute a full test campaign with gate verification, budget tracking, and consolidation."""
        start_wall_time = time.monotonic()
        now_dt = datetime.now(UTC)

        # 1. Portao de autorizacao (Mandatory Target Authorization Gate)
        try:
            auth_record = self._verify_authorization(config)
        except TargetNotAuthorizedError as exc:
            self.audit_log.record_event(
                event_type="test_campaign.rejected",
                actor=config.authorized_by or "unknown",
                action="run_campaign",
                resource=config.target,
                severity="warning",
                details={
                    "campaign_id": config.campaign_id,
                    "target": config.target,
                    "reason": str(exc),
                },
            )
            if raise_on_auth_failure:
                raise

            report = CampaignReport(
                campaign_id=config.campaign_id,
                target=config.target,
                status=CampaignStatus.REJECTED,
                authorized_by=config.authorized_by or "unauthorized",
                authorized_at=now_dt,
                ownership="unauthorized",
                scope=config.allowed_scope,
                agent_count=config.agent_count,
                test_types=config.test_types,
                budget_limit_usd=config.budget.max_cost_usd,
                actual_cost_usd=0.0,
                duration_seconds=time.monotonic() - start_wall_time,
                metadata={"rejection_reason": str(exc)},
            )
            self.registry.register(report)
            return report

        # 2. Control plane: Record campaign start in Audit Log
        self.audit_log.record_event(
            event_type="test_campaign.started",
            actor=auth_record.authorized_by,
            action="run_campaign",
            resource=auth_record.target,
            severity="info",
            details={
                "campaign_id": config.campaign_id,
                "target": auth_record.target,
                "ownership": auth_record.ownership,
                "scope": config.allowed_scope,
                "agent_count": config.agent_count,
                "test_types": [t.value for t in config.test_types],
                "budget_limit_usd": config.budget.max_cost_usd,
                "budget_timeout_sec": config.budget.max_duration_seconds,
            },
        )

        # 3. Budget policy initialization
        _budget_policy = BudgetPolicy(
            entity_id=config.campaign_id,
            dimension="app",
            limit_usd=config.budget.max_cost_usd,
            enforce_hard_limit=True,
        )

        # 4. Agent allocation and orchestration
        agent_results: list[AgentExecutionResult] = []
        all_findings: list[TestFinding] = []
        total_cost = 0.0
        status = CampaignStatus.COMPLETED

        # Create worker tasks for requested test types
        agent_workers = []
        for idx, t_type in enumerate(config.test_types, start=1):
            worker = build_test_agent(t_type, agent_index=idx)
            agent_workers.append(worker)

        max_workers = min(config.agent_count, len(agent_workers)) or 1

        # Execute tests within budget
        def _run_worker(worker: Any) -> AgentExecutionResult:
            return worker.execute(config, config.target)

        timed_out = False
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_worker = {executor.submit(_run_worker, w): w for w in agent_workers}
            try:
                for future in concurrent.futures.as_completed(
                    future_to_worker,
                    timeout=config.budget.max_duration_seconds,
                ):
                    elapsed = time.monotonic() - start_wall_time
                    if elapsed > config.budget.max_duration_seconds:
                        timed_out = True
                        break

                    res = future.result()
                    agent_results.append(res)
                    all_findings.extend(res.findings)
                    total_cost += res.cost_usd

                    # Budget tracking check
                    if total_cost > config.budget.max_cost_usd:
                        status = CampaignStatus.BUDGET_EXCEEDED
                        self.audit_log.record_event(
                            event_type="test_campaign.budget_exceeded",
                            actor=auth_record.authorized_by,
                            action="budget_check",
                            resource=config.campaign_id,
                            severity="error",
                            details={
                                "limit_usd": config.budget.max_cost_usd,
                                "current_spend_usd": total_cost,
                            },
                        )
                        break
            except TimeoutError:
                timed_out = True

        if timed_out:
            status = CampaignStatus.BUDGET_EXCEEDED
            self.audit_log.record_event(
                event_type="test_campaign.timeout",
                actor=auth_record.authorized_by,
                action="timeout_check",
                resource=config.campaign_id,
                severity="warning",
                details={
                    "max_duration_seconds": config.budget.max_duration_seconds,
                    "elapsed_seconds": time.monotonic() - start_wall_time,
                },
            )

        duration = time.monotonic() - start_wall_time

        # 5. Severity aggregation
        sev_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in all_findings:
            sev_key = f.severity.value
            sev_counts[sev_key] = sev_counts.get(sev_key, 0) + 1

        total_run = sum(r.tests_run for r in agent_results)
        total_passed = sum(r.tests_passed for r in agent_results)
        total_failed = sum(r.tests_failed for r in agent_results)

        # 6. Build consolidated report
        report = CampaignReport(
            campaign_id=config.campaign_id,
            target=auth_record.target,
            status=status,
            authorized_by=auth_record.authorized_by,
            authorized_at=now_dt,
            ownership=auth_record.ownership,
            scope=config.allowed_scope,
            agent_count=config.agent_count,
            test_types=config.test_types,
            budget_limit_usd=config.budget.max_cost_usd,
            actual_cost_usd=round(total_cost, 4),
            duration_seconds=round(duration, 3),
            total_tests_run=total_run,
            total_passed=total_passed,
            total_failed=total_failed,
            severity_counts=sev_counts,
            findings=all_findings,
            agent_results=agent_results,
            metadata={"dry_run": config.dry_run},
        )

        # 7. Audit Log - Campaign Completed
        self.audit_log.record_event(
            event_type="test_campaign.completed",
            actor=auth_record.authorized_by,
            action="run_campaign",
            resource=auth_record.target,
            severity="info",
            details={
                "campaign_id": config.campaign_id,
                "status": status.value,
                "duration_seconds": report.duration_seconds,
                "actual_cost_usd": report.actual_cost_usd,
                "total_findings": len(all_findings),
                "severity_counts": sev_counts,
            },
        )

        # 8. Register in global registry for retrieval/reporting
        self.registry.register(report)
        return report
