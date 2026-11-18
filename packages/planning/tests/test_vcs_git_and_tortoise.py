"""Tests for GitProvider and TortoiseGitProvider."""

import subprocess

import pytest
from nexcoder_planning.vcs import GitProvider, TortoiseGitProvider


def test_git_provider_with_runner(tmp_path):
    commands_executed = []
    repo_dir = tmp_path / "repo"

    def mock_runner(cmd, **kwargs):
        commands_executed.append(cmd)
        if "log" in cmd:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="abcdef123456\x00Lead Engineer\x002026-11-15\x00feat: initial commit\n",
                stderr="",
            )
        if "status" in cmd:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="M  src/app.py\n?? new_file.txt\n",
                stderr="",
            )
        if "branch" in cmd:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="feat/vcs\n",
                stderr="",
            )
        if "diff" in cmd:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="--- a/src/app.py\n+++ b/src/app.py\n+new line\n-old line\n",
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    provider = GitProvider(working_dir=repo_dir, cmd_runner=mock_runner)

    # Init
    assert provider.init(repo_dir) is True

    # Checkout
    assert provider.checkout("main") is True

    # Commit
    commit = provider.commit("add vcs provider", commit_type="feat", scope="vcs")
    assert commit.revision == "abcdef123456"
    assert "feat(vcs): add vcs provider" in commit.message

    # Log
    entries = provider.get_log(limit=5)
    assert len(entries) == 1
    assert entries[0].author == "Lead Engineer"

    # Status
    st = provider.get_status()
    assert st.clean is False
    assert "src/app.py" in st.staged_files
    assert "new_file.txt" in st.untracked_files

    # Diff
    diff = provider.get_diff()
    assert diff.additions == 1
    assert diff.deletions == 1


def test_git_provider_rejections(tmp_path):
    provider = GitProvider(working_dir=tmp_path)

    # Rejection of emojis in commit message
    with pytest.raises(ValueError, match="contains emoji characters"):
        provider.commit("feat: initial commit \U0001f680")

    # Rejection of invalid commit types
    with pytest.raises(ValueError, match="Invalid commit type"):
        provider.commit("random commit", commit_type="random")

    # Rejection of emojis in branch name
    with pytest.raises(ValueError, match="contains emoji characters"):
        provider.create_branch("feat/\U0001f680-branch")


def test_tortoise_git_provider(tmp_path):
    provider = TortoiseGitProvider(working_dir=tmp_path)

    # Command line args construction
    args = provider.build_command_args("commit", path=tmp_path, extra_args={"logmsg": "feat: test"})
    assert "/command:commit" in args
    assert f"/path:{tmp_path}" in args
    assert "/logmsg:feat: test" in args

    # GUI shortcut command string
    shortcut = provider.get_gui_shortcut_command("diff", path=tmp_path)
    assert "TortoiseGitProc" in shortcut
    assert "/command:diff" in shortcut

    # Batch script generator
    bat_path = tmp_path / "tgit.bat"
    generated = provider.generate_batch_launcher(bat_path)
    assert generated.is_file()
    content = generated.read_text(encoding="utf-8")
    assert "/command:commit" in content
    assert "/command:log" in content
    assert "/command:diff" in content
