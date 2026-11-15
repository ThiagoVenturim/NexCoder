"""Gated quality review over a target project, plus its pipeline block.

`QualityReviewer.review` is the only entry point that reads a project from disk.
It first asks the control-plane `TargetAuthorizationGate` whether the target is
owned or explicitly authorized, and records the grant, the refusal and the
outcome in the append-only audit log.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from nexcoder_control.approval import (
    TargetAuthorizationGate,
    TargetAuthorizationRecord,
    TargetNotAuthorizedError,
)
from nexcoder_control.metering.audit import AppendOnlyAuditLog

from nexcoder_agents.engine.blocks.base import BaseBlock
from nexcoder_agents.engine.models import BlockResult, BlockStatus
from nexcoder_agents.quality.detectors import run_quality_detectors
from nexcoder_agents.quality.models import BranchInfo, QualityReport, QualityThresholds
from nexcoder_agents.quality.snapshot import ProjectSnapshot

QUALITY_REVIEW_MODE = "quality_review"
APPROVAL_TOKEN_INPUT_KEY = "approval_token_quality_review"
_DEFAULT_BRANCH_NAMES = ("main", "master", "trunk")


def collect_git_branches(repo_root: Path | str, now: float | None = None) -> list[BranchInfo]:
    """List local branches of the git repository rooted exactly at `repo_root`.

    Runs one fixed `git for-each-ref` command (no shell, no caller-supplied
    arguments). Returns an empty list when the directory is not a repository
    root or git is unavailable. Only the last-commit age is known this way.
    """
    root = Path(repo_root).resolve()
    git = shutil.which("git")
    if git is None or not (root / ".git").exists():
        return []
    try:
        proc = subprocess.run(  # noqa: S603
            [git, "for-each-ref", "--format=%(refname:short)%09%(committerdate:unix)", "refs/heads"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []

    current = now if now is not None else time.time()
    branches: list[BranchInfo] = []
    for line in proc.stdout.splitlines():
        name, _, stamp = line.partition("\t")
        if not name.strip():
            continue
        try:
            age_days: float | None = max(0.0, (current - float(stamp)) / 86400.0)
        except ValueError:
            age_days = None
        branches.append(
            BranchInfo(
                name=name.strip(),
                is_default=name.strip() in _DEFAULT_BRANCH_NAMES,
                last_commit_age_days=age_days,
            )
        )
    return branches


class QualityReviewer:
    """Runs the quality detectors against a target that passed the ownership gate."""

    def __init__(
        self,
        target_gate: TargetAuthorizationGate | None = None,
        audit_log: AppendOnlyAuditLog | None = None,
        thresholds: QualityThresholds | None = None,
    ) -> None:
        if target_gate is not None:
            self.target_gate = target_gate
            self.audit_log = audit_log if audit_log is not None else target_gate.audit_log
        else:
            self.audit_log = audit_log if audit_log is not None else AppendOnlyAuditLog()
            self.target_gate = TargetAuthorizationGate(audit_log=self.audit_log)
        self.thresholds = thresholds or QualityThresholds()

    def authorize_target(
        self,
        target: str | Path,
        authorized_by: str = "owner",
        metadata: dict[str, Any] | None = None,
    ) -> TargetAuthorizationRecord:
        """Register a target as owned or explicitly authorized for quality review."""
        return self.target_gate.mark_owned_target(
            target=target,
            authorized_by=authorized_by,
            mode=QUALITY_REVIEW_MODE,
            metadata=metadata,
        )

    def review(
        self,
        target: str | Path,
        *,
        owned_target: bool = False,
        authorized_by: str | None = None,
        approval_token: str | None = None,
        branches: list[BranchInfo] | None = None,
        direct_commits_on_default: list[str] | None = None,
        collect_branches: bool = True,
    ) -> QualityReport:
        """Review `target` and return a prioritized report.

        Raises `TargetNotAuthorizedError` (after recording the refusal in the audit
        log) when the target is neither marked as owned nor explicitly authorized.
        """
        record = self.target_gate.verify_target(
            target=target,
            mode=QUALITY_REVIEW_MODE,
            owned_target=owned_target,
            authorized_by=authorized_by,
            approval_token=approval_token,
        )

        root = Path(target).resolve()
        snapshot = ProjectSnapshot.from_directory(root)
        branch_facts = branches
        if branch_facts is None and collect_branches:
            branch_facts = collect_git_branches(root)

        findings = run_quality_detectors(
            snapshot,
            thresholds=self.thresholds,
            branches=branch_facts,
            direct_commits_on_default=direct_commits_on_default,
        )
        report = QualityReport(
            project_name=snapshot.name,
            target=record.target,
            authorized_by=record.authorized_by,
            ownership=record.ownership,
            files_analyzed=len(snapshot.files),
            symbols_analyzed=len(snapshot.symbols),
            findings=findings,
        )
        self.audit_log.record_event(
            event_type="quality.review.completed",
            actor=record.authorized_by,
            action=QUALITY_REVIEW_MODE,
            resource=record.target,
            severity="info",
            details={
                "target": record.target,
                "ownership": record.ownership,
                "files_analyzed": report.files_analyzed,
                "symbols_analyzed": report.symbols_analyzed,
                "findings": len(findings),
                "by_severity": report.severity_counts(),
                "by_category": report.category_counts(),
            },
        )
        return report


class QualityReviewBlock(BaseBlock):
    """Pipeline block that runs the gated quality review over `project_path`.

    Reads `project_path`, `owned_target` and `authorized_by` from the pipeline
    inputs. An approval token, when used, comes from the
    `approval_token_quality_review` input, which the engine keeps out of the
    pipeline data. The block fails when the gate refuses the target.
    """

    def __init__(
        self,
        name: str = "quality_review",
        target_gate: TargetAuthorizationGate | None = None,
        audit_log: AppendOnlyAuditLog | None = None,
        thresholds: QualityThresholds | None = None,
        max_findings_in_summary: int = 20,
    ) -> None:
        super().__init__(name=name, block_type="quality_review")
        self.reviewer = QualityReviewer(target_gate=target_gate, audit_log=audit_log, thresholds=thresholds)
        self.max_findings_in_summary = max_findings_in_summary

    def execute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        data = state.get("data", {})
        inputs = state.get("inputs", {})
        project_path = data.get("project_path") or inputs.get("project_path")
        if not project_path:
            return self._failure("Missing required key: 'project_path'")

        try:
            report = self.reviewer.review(
                str(project_path),
                owned_target=data.get("owned_target", inputs.get("owned_target", False)) is True,
                authorized_by=data.get("authorized_by") or inputs.get("authorized_by"),
                approval_token=inputs.get(APPROVAL_TOKEN_INPUT_KEY),
            )
        except TargetNotAuthorizedError as exc:
            return self._failure(str(exc), message="Quality review refused: target is not owned or authorized.")
        except FileNotFoundError as exc:
            return self._failure(str(exc))

        top = report.findings[: self.max_findings_in_summary]
        summary_lines = [f"{f.severity.value} {f.location} [{f.rule}] {f.message}" for f in top]
        return BlockResult(
            block_name=self.name,
            status=BlockStatus.SUCCESS,
            updates={
                "quality_report": report.model_dump(mode="json"),
                "quality_findings": [f.model_dump(mode="json") for f in report.findings],
                "quality_severity_counts": report.severity_counts(),
                "quality_findings_summary": "\n".join(summary_lines) or "No quality findings.",
                "quality_report_markdown": report.to_markdown(),
            },
            message=f"Quality review of '{report.project_name}' found {len(report.findings)} issue(s).",
        )

    def _failure(self, error: str, message: str = "Quality review failed.") -> BlockResult:
        return BlockResult(block_name=self.name, status=BlockStatus.FAILURE, error=error, message=message)


__all__ = [
    "APPROVAL_TOKEN_INPUT_KEY",
    "QUALITY_REVIEW_MODE",
    "QualityReviewBlock",
    "QualityReviewer",
    "collect_git_branches",
]
