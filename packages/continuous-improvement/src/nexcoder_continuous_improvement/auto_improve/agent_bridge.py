"""NexLink development agent bridge: branch provisioning, change application, and local verification."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from nexcoder_continuous_improvement.auto_improve.models import (
    AgentExecutionResult,
    AutoIssue,
    SafetyViolationError,
    VerificationResult,
)

FORBIDDEN_TARGET_BRANCHES = {"main", "master", "release"}
FORBIDDEN_INTERNAL_PATTERNS = [
    re.compile(r"internal-host", re.IGNORECASE),
    re.compile(r"net1/", re.IGNORECASE),
    re.compile(r"/internal-apps", re.IGNORECASE),
]

EMOJI_PATTERN = re.compile(
    "["
    "\U0001f000-\U0001faff"
    "\U00002600-\U000027bf"
    "\U00002b00-\U00002bff"
    "\U0001f1e6-\U0001f1ff"
    "\U0000fe0f"
    "\U0000200d"
    "\U000020e3"
    "]"
)


class NexLinkDevAgentBridge:
    """Dispatches a development agent over the NexLink protocol to implement automated improvements."""

    def __init__(
        self,
        repo_dir: str | Path = ".",
        test_command: list[str] | None = None,
        lint_command: list[str] | None = None,
    ) -> None:
        self.repo_dir = Path(repo_dir).resolve()
        self.test_command = test_command or ["python", "-m", "pytest", "-q"]
        self.lint_command = lint_command or ["ruff", "check", "."]

    def build_branch_name(self, issue: AutoIssue) -> str:
        """Construct sanitized feature branch name from issue."""
        clean_title = re.sub(r"[^a-zA-Z0-9]+", "-", issue.title.lower()).strip("-")
        slug = clean_title[:30].rstrip("-")
        return f"feat/auto-issue-{issue.issue_id}-{slug}"

    def run_verification(self, changed_files: list[str] | None = None) -> VerificationResult:
        """Run all verification gates locally: tests, lint, no emoji, and no internal references."""
        result = VerificationResult()

        # 1. Tests check
        try:
            p_test = subprocess.run(  # noqa: S603, S607
                self.test_command,
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            result.tests_passed = p_test.returncode == 0
            result.tests_output = p_test.stdout if p_test.returncode == 0 else (p_test.stdout + "\n" + p_test.stderr)
        except Exception as exc:  # noqa: BLE001
            result.tests_passed = False
            result.tests_output = f"Test execution error: {exc}"

        # 2. Lint check
        try:
            p_lint = subprocess.run(  # noqa: S603, S607
                self.lint_command,
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            result.lint_passed = p_lint.returncode == 0
            result.lint_output = p_lint.stdout if p_lint.returncode == 0 else (p_lint.stdout + "\n" + p_lint.stderr)
        except Exception as exc:  # noqa: BLE001
            result.lint_passed = False
            result.lint_output = f"Lint check error: {exc}"

        # 3. No emoji check
        emoji_hits = self._check_emojis(changed_files)
        if emoji_hits:
            result.no_emoji_passed = False
            result.no_emoji_output = "; ".join(emoji_hits)
        else:
            result.no_emoji_passed = True
            result.no_emoji_output = "No emojis detected"

        # 4. No internal references check
        internal_hits = self._check_internal_leak(changed_files)
        if internal_hits:
            result.no_internal_passed = False
            result.no_internal_output = "; ".join(internal_hits)
        else:
            result.no_internal_passed = True
            result.no_internal_output = "No internal references detected"

        return result

    def _check_emojis(self, changed_files: list[str] | None = None) -> list[str]:
        hits: list[str] = []
        target_files = self._resolve_files(changed_files)
        for path in target_files:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line_no, line in enumerate(content.splitlines(), start=1):
                m = EMOJI_PATTERN.search(line)
                if m:
                    hits.append(f"{path.name}:{line_no} contains emoji U+{ord(m.group()):04X}")
        return hits

    def _check_internal_leak(self, changed_files: list[str] | None = None) -> list[str]:
        hits: list[str] = []
        target_files = self._resolve_files(changed_files)
        for path in target_files:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line_no, line in enumerate(content.splitlines(), start=1):
                for pat in FORBIDDEN_INTERNAL_PATTERNS:
                    if pat.search(line):
                        hits.append(f"{path.name}:{line_no} references internal pattern '{pat.pattern}'")
        return hits

    def _resolve_files(self, changed_files: list[str] | None = None) -> list[Path]:
        if changed_files:
            resolved: list[Path] = []
            for f in changed_files:
                p = self.repo_dir / f if not Path(f).is_absolute() else Path(f)
                if p.is_file():
                    resolved.append(p)
            return resolved

        # Scan text files in repository
        text_files: list[Path] = []
        for p in self.repo_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".py", ".md", ".toml", ".txt", ".json", ".yaml", ".yml"):
                if not any(part in {".git", ".venv", "venv", "node_modules", "__pycache__"} for part in p.parts):
                    text_files.append(p)
        return text_files

    def dispatch_agent(
        self,
        issue: AutoIssue,
        base_branch: str = "develop",
        force: bool = False,
        create_repo: bool = False,
        patch_fn: Callable[[Path], list[str]] | None = None,
    ) -> AgentExecutionResult:
        """Dispatch agent on an isolated branch off develop and run verification suite."""
        # 1. Enforce safety guardrails
        if base_branch.lower() in FORBIDDEN_TARGET_BRANCHES:
            raise SafetyViolationError(f"Base branch cannot be '{base_branch}'. Merging from/to main is forbidden.")
        if force:
            raise SafetyViolationError("Force push is strictly forbidden.")
        if create_repo:
            raise SafetyViolationError("Creating repositories is strictly forbidden.")

        branch_name = self.build_branch_name(issue)
        changed_files: list[str] = []

        # 2. Apply patch if handler provided
        if patch_fn:
            try:
                changed_files = patch_fn(self.repo_dir)
            except Exception as exc:  # noqa: BLE001
                return AgentExecutionResult(
                    issue_id=issue.issue_id,
                    branch_name=branch_name,
                    success=False,
                    error_message=f"Patch handler failed: {exc}",
                )

        # 3. Run verification
        verification = self.run_verification(changed_files)
        success = verification.is_all_green

        commit_msg = f"feat(auto): resolve issue #{issue.issue_id} - {issue.title}"

        return AgentExecutionResult(
            issue_id=issue.issue_id,
            branch_name=branch_name,
            success=success,
            commits=[commit_msg] if success else [],
            files_changed=changed_files,
            diff_summary=f"Automated resolution of issue #{issue.issue_id}",
            verification=verification,
            error_message=None if success else "; ".join(verification.failure_summary()),
        )
