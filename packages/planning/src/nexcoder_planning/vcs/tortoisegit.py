"""TortoiseGit integration provider: Git automation combined with Windows GUI shortcuts and commands."""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from nexcoder_planning.vcs.audit import VCSAuditLogger
from nexcoder_planning.vcs.git_provider import GitProvider

logger = logging.getLogger(__name__)

TORTOISE_GIT_PATHS = [
    Path(r"C:\Program Files\TortoiseGit\bin\TortoiseGitProc.exe"),
    Path(r"C:\Program Files (x86)\TortoiseGit\bin\TortoiseGitProc.exe"),
]


class TortoiseGitProvider(GitProvider):
    """Integrates with TortoiseGit on Windows via Git engine, command line switches, and GUI launchers."""

    name: str = "tortoise_git"
    capabilities: set[str] = {"vcs", "gui_shortcuts"}

    def __init__(
        self,
        working_dir: str | Path | None = None,
        git_executable: str = "git",
        tortoise_proc_path: str | Path | None = None,
        cmd_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        audit_logger: VCSAuditLogger | None = None,
    ) -> None:
        super().__init__(
            working_dir=working_dir,
            executable=git_executable,
            cmd_runner=cmd_runner,
            audit_logger=audit_logger,
        )
        self.tortoise_proc = self._locate_tortoisegit_proc(tortoise_proc_path)

    @staticmethod
    def _locate_tortoisegit_proc(custom_path: str | Path | None = None) -> Path | None:
        if custom_path and Path(custom_path).is_file():
            return Path(custom_path)
        which_path = shutil.which("TortoiseGitProc.exe") or shutil.which("TortoiseGitProc")
        if which_path:
            return Path(which_path)
        for cand in TORTOISE_GIT_PATHS:
            if cand.is_file():
                return cand
        return None

    def is_tortoisegit_installed(self) -> bool:
        """Check if TortoiseGit executable is detected on the current host."""
        return self.tortoise_proc is not None and self.tortoise_proc.is_file()

    def build_command_args(
        self,
        command: str,
        path: str | Path | None = None,
        extra_args: dict[str, str] | None = None,
    ) -> list[str]:
        """Build command line arguments for TortoiseGitProc.exe."""
        target_path = str(path or self.working_dir)
        args = [f"/command:{command}", f"/path:{target_path}"]
        if extra_args:
            for k, v in extra_args.items():
                args.append(f"/{k}:{v}")
        return args

    def get_gui_shortcut_command(
        self,
        command: str,
        path: str | Path | None = None,
        extra_args: dict[str, str] | None = None,
    ) -> str:
        """Generate Windows CLI or shortcut command line to open TortoiseGit GUI dialog."""
        exe_str = str(self.tortoise_proc) if self.tortoise_proc else "TortoiseGitProc.exe"
        args = self.build_command_args(command, path=path, extra_args=extra_args)
        quoted_args = [f'"{a}"' if " " in a else a for a in args]
        return f'"{exe_str}" ' + " ".join(quoted_args)

    def launch_gui_command(
        self,
        command: str,
        path: str | Path | None = None,
        extra_args: dict[str, str] | None = None,
    ) -> bool:
        """Launch the requested TortoiseGit GUI dialog asynchronously on Windows."""
        if not self.is_tortoisegit_installed():
            logger.warning("TortoiseGitProc.exe not found on host; cannot launch GUI.")
            self._audit(
                "launch_gui",
                "tortoisegit_command",
                resource_id=command,
                success=False,
                error_message="Executable not found",
            )
            return False

        args = [str(self.tortoise_proc), *self.build_command_args(command, path=path, extra_args=extra_args)]
        try:
            # Launch without blocking
            subprocess.Popen(args)  # noqa: S603
            self._audit("launch_gui", "tortoisegit_command", resource_id=command, success=True)
            return True
        except Exception as exc:
            self._audit(
                "launch_gui",
                "tortoisegit_command",
                resource_id=command,
                success=False,
                error_message=str(exc),
            )
            return False

    def generate_batch_launcher(self, target_script: str | Path) -> Path:
        """Generate a Windows batch file with handy shortcuts for TortoiseGit commands."""
        dest = Path(target_script)
        exe = str(self.tortoise_proc) if self.tortoise_proc else "TortoiseGitProc.exe"
        script_content = (
            "@echo off\r\n"
            f'set TPROC="{exe}"\r\n'
            "set REPO_PATH=%~dp0\r\n"
            "if \"%1\"==\"commit\" %TPROC% /command:commit /path:\"%REPO_PATH%\"\r\n"
            "if \"%1\"==\"log\" %TPROC% /command:log /path:\"%REPO_PATH%\"\r\n"
            "if \"%1\"==\"diff\" %TPROC% /command:diff /path:\"%REPO_PATH%\"\r\n"
            "if \"%1\"==\"push\" %TPROC% /command:push /path:\"%REPO_PATH%\"\r\n"
            "if \"%1\"==\"pull\" %TPROC% /command:pull /path:\"%REPO_PATH%\"\r\n"
            "if \"%1\"==\"status\" %TPROC% /command:repostatus /path:\"%REPO_PATH%\"\r\n"
            "if \"%1\"==\"\" echo Usage: %~nx0 [commit^|log^|diff^|push^|pull^|status]\r\n"
        )
        dest.write_text(script_content, encoding="utf-8")
        self._audit("generate_batch_launcher", "script", resource_id=str(dest), success=True)
        return dest
