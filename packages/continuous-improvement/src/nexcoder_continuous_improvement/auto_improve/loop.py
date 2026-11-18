"""Master orchestrator for continuous auto-improvement: scan -> issue -> branch -> verify -> merge -> report."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_control.metering.budgets import BudgetPolicy

from nexcoder_continuous_improvement.auto_improve.agent_bridge import NexLinkDevAgentBridge
from nexcoder_continuous_improvement.auto_improve.issues import (
    AutoIssueManager,
    InMemoryIssueAdapter,
    IssuePlatformAdapter,
)
from nexcoder_continuous_improvement.auto_improve.merger import AutoMergeEngine
from nexcoder_continuous_improvement.auto_improve.models import (
    AutoImproveCycleReport,
    AutoIssue,
    MergeDecision,
)
from nexcoder_continuous_improvement.auto_improve.quota import DailyQuotaTracker
from nexcoder_continuous_improvement.auto_improve.reporter import AutoImproveReporter
from nexcoder_continuous_improvement.auto_improve.scanner import RepoScanner


class AutoImproveLoop:
    """End-to-end continuous improvement loop with automated issue, branch, test, and merge orchestration."""

    def __init__(
        self,
        repo_path: str | Path = ".",
        max_daily_merges: int = 5,
        budget_policy: BudgetPolicy | None = None,
        quota_tracker: DailyQuotaTracker | None = None,
        audit_log: AppendOnlyAuditLog | None = None,
        issue_adapter: IssuePlatformAdapter | None = None,
        scanner: RepoScanner | None = None,
        agent_bridge: NexLinkDevAgentBridge | None = None,
        merge_engine: AutoMergeEngine | None = None,
        reporter: AutoImproveReporter | None = None,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.quota_tracker = quota_tracker or DailyQuotaTracker(max_daily_merges=max_daily_merges)
        self.audit_log = audit_log or AppendOnlyAuditLog()
        self.budget_policy = budget_policy

        self.scanner = scanner or RepoScanner(root_path=self.repo_path)
        self.issue_manager = AutoIssueManager(adapter=issue_adapter or InMemoryIssueAdapter())
        self.agent_bridge = agent_bridge or NexLinkDevAgentBridge(repo_dir=self.repo_path)
        self.merge_engine = merge_engine or AutoMergeEngine(
            repo_dir=self.repo_path,
            quota_tracker=self.quota_tracker,
            audit_log=self.audit_log,
            budget_policy=self.budget_policy,
        )
        self.reporter = reporter or AutoImproveReporter(quota_tracker=self.quota_tracker, audit_log=self.audit_log)

    def run_cycle(
        self,
        dry_run: bool = False,
        max_items: int | None = None,
        patch_handlers: dict[str, Callable[[Path], list[str]]] | None = None,
    ) -> AutoImproveCycleReport:
        """Execute one complete automated cycle: scan, issue creation, branch development,
        test verification, and merge into develop.
        """
        cycle_id = f"cycle-{uuid.uuid4().hex[:8]}"
        started_at = datetime.now(UTC)

        self.audit_log.record_event(
            event_type="cycle_started",
            actor="nexcoder-autoimprove",
            action="start_auto_improvement_cycle",
            resource=f"cycle:{cycle_id}",
            severity="info",
            details={"repo_path": str(self.repo_path), "dry_run": dry_run},
        )

        # 1. Scan repository
        findings = self.scanner.scan_all()
        findings_by_category: dict[str, int] = {}
        for f in findings:
            cat_name = f.category.value
            findings_by_category[cat_name] = findings_by_category.get(cat_name, 0) + 1

        selected_findings = findings[:max_items] if max_items else findings

        issues_created: list[AutoIssue] = []
        branches_evaluated: list[str] = []
        merges_executed: list[str] = []
        merges_blocked: list[str] = []
        cycle_status = "completed"

        # 2. Process findings
        for finding in selected_findings:
            # Check daily quota before proceeding with changes
            if not self.quota_tracker.can_merge():
                cycle_status = "quota_reached"
                merges_blocked.append(f"Quota exhausted: {finding.title}")
                break

            # Open / deduplicate issue with label "auto"
            issue = self.issue_manager.sync_finding_to_issue(finding)
            issues_created.append(issue)

            if dry_run:
                continue

            # Resolve patch handler for this category or finding if available
            patch_fn = None
            if patch_handlers:
                patch_fn = patch_handlers.get(finding.category.value) or patch_handlers.get("default")

            # Dispatch development agent to create branch and run verification
            agent_result = self.agent_bridge.dispatch_agent(
                issue=issue,
                base_branch="develop",
                force=False,
                create_repo=False,
                patch_fn=patch_fn,
            )
            branches_evaluated.append(agent_result.branch_name)

            if not agent_result.success:
                merges_blocked.append(
                    f"Branch {agent_result.branch_name} blocked by verification: {agent_result.error_message}"
                )
                continue

            # Evaluate gates and merge into develop
            decision: MergeDecision = self.merge_engine.evaluate_and_merge(
                agent_result=agent_result,
                target_branch="develop",
                force=False,
                create_repo=False,
            )

            if decision.allowed:
                merges_executed.append(agent_result.branch_name)
                self.issue_manager.adapter.close_issue(
                    issue.issue_id, comment=f"Resolved automatically via merge commit {decision.merge_commit_sha}"
                )
            else:
                merges_blocked.append(f"Branch {agent_result.branch_name} blocked: {decision.reason}")

        completed_at = datetime.now(UTC)

        self.audit_log.record_event(
            event_type="cycle_completed",
            actor="nexcoder-autoimprove",
            action="complete_auto_improvement_cycle",
            resource=f"cycle:{cycle_id}",
            severity="info",
            details={
                "status": cycle_status,
                "findings_count": len(findings),
                "merges_count": len(merges_executed),
                "blocked_count": len(merges_blocked),
            },
        )

        audit_events = self.audit_log._events
        chain_length = len(audit_events)
        head_hash = audit_events[-1].event_hash if audit_events else self.audit_log.GENESIS_HASH

        report = AutoImproveCycleReport(
            cycle_id=cycle_id,
            started_at=started_at,
            completed_at=completed_at,
            findings_detected=len(findings),
            findings_by_category=findings_by_category,
            issues_created=issues_created,
            branches_evaluated=branches_evaluated,
            merges_executed=merges_executed,
            merges_blocked=merges_blocked,
            quota_used_today=self.quota_tracker.get_used_today(),
            quota_remaining_today=self.quota_tracker.get_remaining_today(),
            budget_spent_usd=self.merge_engine.current_spend_usd,
            audit_chain_length=chain_length,
            audit_head_hash=head_hash,
            status=cycle_status,
        )
        report.summary = self.reporter.build_markdown_report(report)
        return report
