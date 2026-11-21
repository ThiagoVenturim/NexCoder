"""Tests for SVNProvider using a simulated local SVN test repository."""

import subprocess
from pathlib import Path

import pytest
from nexcoder_planning.vcs import SVNProvider


class LocalSVNTestRepo:
    """Simulates an offline local Subversion repository and CLI runner."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.current_revision = 1
        self.history: list[dict[str, str]] = [
            {
                "revision": "1",
                "author": "svnadmin",
                "date": "2026-11-15T09:00:00.000000Z",
                "message": "Initial import",
            }
        ]
        self.files: dict[str, str] = {"README.txt": "Project documentation"}

    def runner(self, cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        action = cmd[1] if len(cmd) > 1 else ""

        if action == "checkout":
            # Simulate checkout
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=f"Checked out revision {self.current_revision}.\n",
                stderr="",
            )

        elif action == "add":
            target = cmd[2] if len(cmd) > 2 else "file"
            return subprocess.CompletedProcess(cmd, 0, stdout=f"A         {target}\n", stderr="")

        elif action == "commit":
            # Parse -m message
            msg = ""
            if "-m" in cmd:
                idx = cmd.index("-m")
                if idx + 1 < len(cmd):
                    msg = cmd[idx + 1]
            self.current_revision += 1
            rev_str = str(self.current_revision)
            self.history.insert(
                0,
                {
                    "revision": rev_str,
                    "author": "developer",
                    "date": "2026-11-15T12:00:00.000000Z",
                    "message": msg,
                },
            )
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=f"Sending        file.txt\nTransmitting file data .\nCommitted revision {rev_str}.\n",
                stderr="",
            )

        elif action == "log":
            # Output xml matching svn log --xml
            xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<log>"]
            for h in self.history:
                xml_lines.append(f'<logentry revision="{h["revision"]}">')
                xml_lines.append(f'<author>{h["author"]}</author>')
                xml_lines.append(f'<date>{h["date"]}</date>')
                xml_lines.append(f'<msg>{h["message"]}</msg>')
                xml_lines.append("</logentry>")
            xml_lines.append("</log>")
            return subprocess.CompletedProcess(cmd, 0, stdout="\n".join(xml_lines), stderr="")

        elif action == "diff":
            patch = (
                "Index: file.txt\n"
                "===================================================================\n"
                "--- file.txt\t(revision 1)\n"
                "+++ file.txt\t(working copy)\n"
                "@@ -1 +1,2 @@\n"
                " line1\n"
                "+line2\n"
                "-line old\n"
            )
            return subprocess.CompletedProcess(cmd, 0, stdout=patch, stderr="")

        elif action == "status":
            status_text = "M       file.txt\nA       new_script.py\n?       scratch.tmp\n"
            return subprocess.CompletedProcess(cmd, 0, stdout=status_text, stderr="")

        elif action == "update":
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=f"Updating '.':\nAt revision {self.current_revision}.\n",
                stderr="",
            )

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def test_svn_local_repository_operations(tmp_path):
    local_repo = LocalSVNTestRepo(tmp_path)
    svn = SVNProvider(working_dir=tmp_path, cmd_runner=local_repo.runner)

    # 1. Checkout
    checked_out = svn.checkout("svn://localhost/repo/trunk", dest_path=tmp_path)
    assert checked_out is True

    # 2. Add
    added = svn.add("new_script.py")
    assert added is True

    # 3. Commit
    commit = svn.commit("feat: add core script")
    assert commit.revision == "2"
    assert commit.message == "feat: add core script"

    # 4. Log
    logs = svn.get_log(limit=5)
    assert len(logs) == 2
    assert logs[0].revision == "2"
    assert logs[0].message == "feat: add core script"
    assert logs[1].revision == "1"

    # 5. Diff
    diff = svn.get_diff("file.txt")
    assert diff.additions == 1
    assert diff.deletions == 1
    assert "line2" in diff.patch

    # 6. Status
    st = svn.get_status()
    assert st.clean is False
    assert "file.txt" in st.modified_files
    assert "new_script.py" in st.staged_files
    assert "scratch.tmp" in st.untracked_files

    # 7. Update
    up_res = svn.update()
    assert "At revision 2" in up_res


def test_svn_zero_emoji_rejection(tmp_path):
    local_repo = LocalSVNTestRepo(tmp_path)
    svn = SVNProvider(working_dir=tmp_path, cmd_runner=local_repo.runner)

    # Emoji in SVN commit message must raise ValueError
    with pytest.raises(ValueError, match="contains emoji characters"):
        svn.commit("feat: new feature \U0001f389")
