"""Subversion (SVN) command line interface provider."""

from __future__ import annotations

import logging
import re
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

from nexcoder_planning.git_helpers import strip_co_author_trailers, validate_no_emoji
from nexcoder_planning.vcs.audit import VCSAuditLogger
from nexcoder_planning.vcs.base import RepoManagementProvider
from nexcoder_planning.vcs.models import (
    VCSCommit,
    VCSDiff,
    VCSLogEntry,
    VCSStatus,
)

logger = logging.getLogger(__name__)


class SVNProvider(RepoManagementProvider):
    """Integrates with Subversion repositories via the svn CLI for checkout, commit, log, and diff."""

    name: str = "svn"
    capabilities: set[str] = {"vcs"}

    def __init__(
        self,
        working_dir: str | Path | None = None,
        executable: str = "svn",
        username: str | None = None,
        password: str | None = None,
        cmd_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        audit_logger: VCSAuditLogger | None = None,
    ) -> None:
        super().__init__(audit_logger=audit_logger)
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.executable = executable
        self.username = username or self.load_secret_from_env("SVN_USERNAME", "SVN_USER")
        self.password = password or self.load_secret_from_env("SVN_PASSWORD", "SVN_PASS")
        self.cmd_runner = cmd_runner or subprocess.run

    def _run_cmd(
        self,
        args: list[str],
        cwd: str | Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        target_cwd = str(cwd or self.working_dir)
        full_args = [self.executable, *args, "--non-interactive"]
        if self.username:
            full_args.extend(["--username", self.username])
        if self.password:
            full_args.extend(["--password", self.password, "--no-auth-cache"])

        proc = self.cmd_runner(  # noqa: S603
            full_args,
            cwd=target_cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(f"SVN command failed ({proc.returncode}): {' '.join(args)}: {err}")
        return proc

    def checkout(
        self,
        repo_url: str,
        dest_path: str | Path | None = None,
        revision: str = "HEAD",
    ) -> bool:
        """Checkout a working copy from an SVN repository URL."""
        self.check_capability("vcs")
        target_dest = str(dest_path or self.working_dir)
        args = ["checkout", "-r", revision, repo_url, target_dest]
        try:
            self._run_cmd(args)
            self._audit(
                "checkout",
                "svn_repo",
                resource_id=repo_url,
                details={"dest": target_dest, "revision": revision},
                success=True,
            )
            return True
        except Exception as exc:
            self._audit("checkout", "svn_repo", resource_id=repo_url, success=False, error_message=str(exc))
            raise

    def add(self, file_path: str | Path, cwd: str | Path | None = None) -> bool:
        """Schedule a file or directory for addition to SVN."""
        target_cwd = cwd or self.working_dir
        args = ["add", str(file_path)]
        try:
            self._run_cmd(args, cwd=target_cwd)
            self._audit("add", "svn_file", resource_id=str(file_path), success=True)
            return True
        except Exception as exc:
            self._audit("add", "svn_file", resource_id=str(file_path), success=False, error_message=str(exc))
            raise

    def commit(
        self,
        message: str,
        files: list[str] | None = None,
        cwd: str | Path | None = None,
    ) -> VCSCommit:
        """Commit changes to the SVN repository with conventional format and no emojis."""
        self.check_capability("vcs")
        validate_no_emoji(message, "SVN commit message")
        clean_msg = strip_co_author_trailers(message)

        target_cwd = cwd or self.working_dir
        args = ["commit", "-m", clean_msg]
        if files:
            args.extend(files)

        try:
            proc = self._run_cmd(args, cwd=target_cwd)
            out = proc.stdout
            # Example stdout: "Committed revision 4."
            rev_match = re.search(r"[Cc]ommitted revision (\d+)\.?", out)
            revision = rev_match.group(1) if rev_match else "HEAD"

            commit_obj = VCSCommit(
                revision=revision,
                author=self.username or "",
                message=clean_msg,
                files_changed=files or [],
            )
            self._audit("commit", "svn_commit", resource_id=revision, success=True)
            return commit_obj
        except Exception as exc:
            self._audit("commit", "svn_commit", success=False, error_message=str(exc))
            raise

    def get_log(
        self,
        limit: int = 10,
        cwd: str | Path | None = None,
    ) -> list[VCSLogEntry]:
        """Retrieve recent commit log history via svn log --xml."""
        self.check_capability("vcs")
        target_cwd = cwd or self.working_dir
        args = ["log", "-l", str(limit), "--xml"]
        try:
            proc = self._run_cmd(args, cwd=target_cwd)
            entries: list[VCSLogEntry] = []
            if proc.stdout.strip():
                try:
                    root = ET.fromstring(proc.stdout)  # noqa: S314
                    for logentry in root.findall("logentry"):
                        rev = logentry.get("revision", "")
                        author = logentry.findtext("author") or ""
                        date = logentry.findtext("date") or ""
                        msg = logentry.findtext("msg") or ""
                        entries.append(
                            VCSLogEntry(
                                revision=rev,
                                author=author,
                                date=date,
                                message=msg,
                            )
                        )
                except ET.ParseError:
                    # Fallback to plain line parsing
                    for line in proc.stdout.splitlines():
                        if line.startswith("r") and " | " in line:
                            parts = line.split(" | ")
                            entries.append(
                                VCSLogEntry(
                                    revision=parts[0].lstrip("r"),
                                    author=parts[1] if len(parts) > 1 else "",
                                    date=parts[2] if len(parts) > 2 else "",
                                    message="",
                                )
                            )
            self._audit("get_log", "svn_log", success=True, details={"count": len(entries)})
            return entries
        except Exception as exc:
            self._audit("get_log", "svn_log", success=False, error_message=str(exc))
            raise

    def get_diff(
        self,
        target: str | None = None,
        cwd: str | Path | None = None,
    ) -> VCSDiff:
        """Retrieve diff of the working copy or target file."""
        self.check_capability("vcs")
        target_cwd = cwd or self.working_dir
        args = ["diff"]
        if target:
            args.append(target)
        try:
            proc = self._run_cmd(args, cwd=target_cwd)
            patch = proc.stdout
            additions = sum(1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
            deletions = sum(1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---"))
            diff_obj = VCSDiff(
                target=target or "working_copy",
                patch=patch,
                additions=additions,
                deletions=deletions,
            )
            self._audit("get_diff", "svn_diff", success=True)
            return diff_obj
        except Exception as exc:
            self._audit("get_diff", "svn_diff", success=False, error_message=str(exc))
            raise

    def get_status(self, cwd: str | Path | None = None) -> VCSStatus:
        """Inspect SVN working copy status."""
        self.check_capability("vcs")
        target_cwd = cwd or self.working_dir
        args = ["status"]
        try:
            proc = self._run_cmd(args, cwd=target_cwd)
            staged: list[str] = []
            modified: list[str] = []
            untracked: list[str] = []

            for line in proc.stdout.splitlines():
                if len(line) < 2:
                    continue
                code, path = line[0], line[1:].strip()
                if code == "A":
                    staged.append(path)
                elif code in ("M", "D"):
                    modified.append(path)
                elif code == "?":
                    untracked.append(path)

            status_obj = VCSStatus(
                branch_or_rev="trunk",
                clean=(len(staged) == 0 and len(modified) == 0 and len(untracked) == 0),
                staged_files=staged,
                modified_files=modified,
                untracked_files=untracked,
            )
            self._audit("get_status", "svn_status", success=True)
            return status_obj
        except Exception as exc:
            self._audit("get_status", "svn_status", success=False, error_message=str(exc))
            raise

    def update(
        self,
        revision: str = "HEAD",
        cwd: str | Path | None = None,
    ) -> str:
        """Update working copy to latest or specified revision."""
        target_cwd = cwd or self.working_dir
        args = ["update", "-r", revision]
        try:
            proc = self._run_cmd(args, cwd=target_cwd)
            self._audit("update", "svn_wc", details={"revision": revision}, success=True)
            return proc.stdout.strip()
        except Exception as exc:
            self._audit("update", "svn_wc", success=False, error_message=str(exc))
            raise
