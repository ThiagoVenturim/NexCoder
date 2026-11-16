"""Reusable high-level Git VCS operations provider."""

from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from nexcoder_planning.git_helpers import (
    ALLOWED_COMMIT_TYPES,
    strip_co_author_trailers,
    validate_no_emoji,
)
from nexcoder_planning.vcs.audit import VCSAuditLogger
from nexcoder_planning.vcs.base import RepoManagementProvider
from nexcoder_planning.vcs.models import (
    VCSCommit,
    VCSDiff,
    VCSLogEntry,
    VCSStatus,
)

logger = logging.getLogger(__name__)


class GitProvider(RepoManagementProvider):
    """Reusable high-level Git operations: branches, commits, diffs, logs, and status."""

    name: str = "git"
    capabilities: set[str] = {"vcs"}

    def __init__(
        self,
        working_dir: str | Path | None = None,
        executable: str = "git",
        cmd_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        audit_logger: VCSAuditLogger | None = None,
    ) -> None:
        super().__init__(audit_logger=audit_logger)
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.executable = executable
        self.cmd_runner = cmd_runner or subprocess.run

    def _run_cmd(
        self,
        args: list[str],
        cwd: str | Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        target_cwd = str(cwd or self.working_dir)
        cmd = [self.executable, *args]
        proc = self.cmd_runner(  # noqa: S603
            cmd,
            cwd=target_cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(f"Git command failed ({proc.returncode}): {' '.join(cmd)}: {err}")
        return proc

    def init(self, repo_path: str | Path | None = None, bare: bool = False) -> bool:
        """Initialize a new git repository."""
        target = Path(repo_path) if repo_path else self.working_dir
        target.mkdir(parents=True, exist_ok=True)
        args = ["init"]
        if bare:
            args.append("--bare")
        self._run_cmd(args, cwd=target)
        self._audit("init", "git_repo", resource_id=str(target), success=True)
        return True

    def checkout(self, ref: str, target_dir: str | None = None, create_branch: bool = False) -> bool:
        """Checkout a branch or revision."""
        self.check_capability("vcs")
        args = ["checkout"]
        if create_branch:
            args.append("-b")
        args.append(ref)
        try:
            self._run_cmd(args, cwd=target_dir or self.working_dir)
            self._audit("checkout", "vcs_ref", resource_id=ref, success=True)
            return True
        except Exception as exc:
            self._audit("checkout", "vcs_ref", resource_id=ref, success=False, error_message=str(exc))
            raise

    def create_branch(self, branch_name: str, base_branch: str = "develop") -> bool:
        """Create and checkout a new branch safely."""
        validate_no_emoji(branch_name, "Branch name")
        if not re.match(r"^[a-zA-Z0-9_\-./]+$", branch_name):
            raise ValueError(f"Invalid branch name: {branch_name}")
        self._run_cmd(["checkout", base_branch])
        self._run_cmd(["checkout", "-b", branch_name])
        self._audit("create_branch", "git_branch", resource_id=branch_name, success=True)
        return True

    def get_current_branch(self) -> str:
        """Get the name of the currently checked out branch."""
        res = self._run_cmd(["branch", "--show-current"])
        return res.stdout.strip()

    def add(self, files: list[str] | None = None) -> bool:
        """Stage files for commit."""
        target_files = files if files else ["."]
        self._run_cmd(["add", *target_files])
        self._audit("add", "vcs_files", details={"files": target_files}, success=True)
        return True

    def commit(
        self,
        message: str,
        files: list[str] | None = None,
        commit_type: str = "feat",
        scope: str = "",
    ) -> VCSCommit:
        """Create a conventional commit strictly enforcing zero emoji and no co-author trailers."""
        self.check_capability("vcs")
        validate_no_emoji(message, "Commit message")
        if commit_type not in ALLOWED_COMMIT_TYPES:
            raise ValueError(f"Invalid commit type: {commit_type}. Allowed: {sorted(ALLOWED_COMMIT_TYPES)}")

        clean_message = strip_co_author_trailers(message)
        header = f"{commit_type}({scope}): " if scope else f"{commit_type}: "
        full_msg = clean_message if clean_message.startswith(commit_type) else f"{header}{clean_message}"

        if files:
            self.add(files)

        try:
            self._run_cmd(["commit", "-m", full_msg])
            log_proc = self._run_cmd(["log", "-1", "--format=%H%x00%an%x00%ad%x00%s"])
            parts = log_proc.stdout.strip().split("\x00")
            rev = parts[0] if parts else "unknown"
            author = parts[1] if len(parts) > 1 else ""
            date = parts[2] if len(parts) > 2 else ""

            commit_obj = VCSCommit(
                revision=rev,
                author=author,
                date=date,
                message=full_msg,
                files_changed=files or [],
            )
            self._audit("commit", "vcs_commit", resource_id=rev, success=True)
            return commit_obj
        except Exception as exc:
            self._audit("commit", "vcs_commit", success=False, error_message=str(exc))
            raise

    def get_log(self, limit: int = 10) -> list[VCSLogEntry]:
        """Retrieve recent commit log entries."""
        self.check_capability("vcs")
        try:
            proc = self._run_cmd(["log", f"-{limit}", "--format=%H%x00%an%x00%ad%x00%s"])
            entries: list[VCSLogEntry] = []
            for line in proc.stdout.strip().splitlines():
                if not line.strip():
                    continue
                parts = line.split("\x00")
                entries.append(
                    VCSLogEntry(
                        revision=parts[0],
                        author=parts[1] if len(parts) > 1 else "",
                        date=parts[2] if len(parts) > 2 else "",
                        message=parts[3] if len(parts) > 3 else "",
                    )
                )
            self._audit("get_log", "vcs_log", success=True, details={"count": len(entries)})
            return entries
        except Exception as exc:
            self._audit("get_log", "vcs_log", success=False, error_message=str(exc))
            raise

    def get_diff(self, target: str | None = None) -> VCSDiff:
        """Generate diff against HEAD or specified target."""
        self.check_capability("vcs")
        args = ["diff"]
        if target:
            args.append(target)
        try:
            proc = self._run_cmd(args)
            patch = proc.stdout
            additions = sum(1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
            deletions = sum(1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---"))
            diff_obj = VCSDiff(
                target=target or "working_tree",
                patch=patch,
                additions=additions,
                deletions=deletions,
            )
            self._audit("get_diff", "vcs_diff", success=True)
            return diff_obj
        except Exception as exc:
            self._audit("get_diff", "vcs_diff", success=False, error_message=str(exc))
            raise

    def get_status(self) -> VCSStatus:
        """Inspect working copy status."""
        self.check_capability("vcs")
        try:
            proc = self._run_cmd(["status", "--porcelain=v1"])
            staged: list[str] = []
            modified: list[str] = []
            untracked: list[str] = []

            for line in proc.stdout.splitlines():
                if len(line) < 3:
                    continue
                x, y, path = line[0], line[1], line[3:].strip()
                if x in ("M", "A", "D", "R", "C"):
                    staged.append(path)
                if y in ("M", "D"):
                    modified.append(path)
                if x == "?" and y == "?":
                    untracked.append(path)

            branch = self.get_current_branch()
            status_obj = VCSStatus(
                branch_or_rev=branch,
                clean=(len(staged) == 0 and len(modified) == 0 and len(untracked) == 0),
                staged_files=staged,
                modified_files=modified,
                untracked_files=untracked,
            )
            self._audit("get_status", "vcs_status", success=True)
            return status_obj
        except Exception as exc:
            self._audit("get_status", "vcs_status", success=False, error_message=str(exc))
            raise

    def push(self, remote: str = "origin", branch: str = "") -> bool:
        """Push branch to remote (refuses force push)."""
        target_branch = branch or self.get_current_branch()
        self._run_cmd(["push", remote, target_branch])
        self._audit("push", "vcs_remote", resource_id=f"{remote}/{target_branch}", success=True)
        return True

    def pull(self, remote: str = "origin", branch: str = "") -> bool:
        """Pull branch updates from remote."""
        target_branch = branch or self.get_current_branch()
        self._run_cmd(["pull", remote, target_branch])
        self._audit("pull", "vcs_remote", resource_id=f"{remote}/{target_branch}", success=True)
        return True
