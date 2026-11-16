"""Reporting and dashboard generator for automated continuous improvement runs."""

from __future__ import annotations

from typing import Any

from nexcoder_control.metering.audit import AppendOnlyAuditLog

from nexcoder_continuous_improvement.auto_improve.models import AutoImproveCycleReport
from nexcoder_continuous_improvement.auto_improve.quota import DailyQuotaTracker


class AutoImproveReporter:
    """Formats human-readable markdown summaries and structured data for auto-improvement cycles."""

    def __init__(
        self,
        quota_tracker: DailyQuotaTracker | None = None,
        audit_log: AppendOnlyAuditLog | None = None,
    ) -> None:
        self.quota_tracker = quota_tracker or DailyQuotaTracker()
        self.audit_log = audit_log or AppendOnlyAuditLog()

    def build_markdown_report(self, report: AutoImproveCycleReport) -> str:
        """Render clean, emoji-free markdown report."""
        lines: list[str] = [
            "# Auto-Improvement Cycle Report",
            "",
            f"- **Cycle ID**: `{report.cycle_id}`",
            f"- **Status**: `{report.status}`",
            f"- **Started**: {report.started_at.isoformat()}",
            f"- **Completed**: {report.completed_at.isoformat()}",
            f"- **Findings Detected**: {report.findings_detected}",
            "",
            "## Findings by Category",
            "",
        ]

        if report.findings_by_category:
            for cat, count in sorted(report.findings_by_category.items()):
                lines.append(f"- **{cat}**: {count}")
        else:
            lines.append("No active findings detected in this cycle.")

        lines.extend([
            "",
            "## Issues Managed (Label: auto)",
            "",
        ])
        if report.issues_created:
            for iss in report.issues_created:
                lines.append(f"- Issue #{iss.issue_id}: [{iss.category.value}] {iss.title} ({iss.status})")
        else:
            lines.append("No new issues required creation.")

        lines.extend([
            "",
            "## Branches and Merges into develop",
            "",
            f"- **Branches Evaluated**: {len(report.branches_evaluated)}",
            f"- **Automated Merges Executed**: {len(report.merges_executed)}",
            f"- **Merges Blocked**: {len(report.merges_blocked)}",
            "",
        ])

        if report.merges_executed:
            lines.append("### Merged Branches")
            for br in report.merges_executed:
                lines.append(f"- `{br}` -> `develop`")
            lines.append("")

        if report.merges_blocked:
            lines.append("### Blocked Merges")
            for blk in report.merges_blocked:
                lines.append(f"- {blk}")
            lines.append("")

        lines.extend([
            "## Control Plane Quota and Budget",
            "",
            f"- **Daily Merges Used**: {report.quota_used_today}",
            f"- **Daily Merges Remaining**: {report.quota_remaining_today}",
            f"- **Budget Spent**: ${report.budget_spent_usd:.2f}",
            "",
            "## Audit Log Integrity",
            "",
            f"- **Chain Length**: {report.audit_chain_length} events",
            f"- **Head Hash**: `{report.audit_head_hash or 'N/A'}`",
            "",
        ])

        return "\n".join(lines)

    def to_dashboard_dict(self, report: AutoImproveCycleReport) -> dict[str, Any]:
        """Convert report to JSON-serializable dashboard payload."""
        return {
            "cycle_id": report.cycle_id,
            "status": report.status,
            "started_at": report.started_at.isoformat(),
            "completed_at": report.completed_at.isoformat(),
            "metrics": {
                "findings_detected": report.findings_detected,
                "findings_by_category": report.findings_by_category,
                "issues_count": len(report.issues_created),
                "merges_executed_count": len(report.merges_executed),
                "merges_blocked_count": len(report.merges_blocked),
                "daily_quota_used": report.quota_used_today,
                "daily_quota_remaining": report.quota_remaining_today,
                "budget_spent_usd": report.budget_spent_usd,
            },
            "issues": [
                {
                    "issue_id": iss.issue_id,
                    "title": iss.title,
                    "category": iss.category.value,
                    "status": iss.status,
                    "labels": iss.labels,
                }
                for iss in report.issues_created
            ],
            "merges": report.merges_executed,
            "blocked": report.merges_blocked,
            "audit": {
                "chain_length": report.audit_chain_length,
                "head_hash": report.audit_head_hash,
                "verified": self.audit_log.verify_integrity()[0],
            },
        }
