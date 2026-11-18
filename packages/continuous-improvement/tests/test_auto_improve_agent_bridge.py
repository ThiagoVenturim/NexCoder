"""Unit tests for NexLink development agent bridge, verification gates, and safety guardrails."""

from pathlib import Path

import pytest
from nexcoder_continuous_improvement.auto_improve.agent_bridge import NexLinkDevAgentBridge
from nexcoder_continuous_improvement.auto_improve.models import AutoIssue, SafetyViolationError


def test_agent_bridge_branch_naming() -> None:
    bridge = NexLinkDevAgentBridge(repo_dir=".")
    issue = AutoIssue(issue_id=78, title="Refactor connection retry handler", body="Criteria")
    branch = bridge.build_branch_name(issue)
    assert branch.startswith("feat/auto-issue-78-refactor-connection-retry-hand")


def test_agent_bridge_detects_emojis(tmp_path: Path) -> None:
    bridge = NexLinkDevAgentBridge(repo_dir=tmp_path)
    file_with_emoji = tmp_path / "emoji.py"
    # Unicode character for rocket or smile
    file_with_emoji.write_text("# rocket \U0001f680\nx = 1\n", encoding="utf-8")

    hits = bridge._check_emojis([str(file_with_emoji)])
    assert len(hits) == 1
    assert "contains emoji" in hits[0]


def test_agent_bridge_detects_internal_patterns(tmp_path: Path) -> None:
    bridge = NexLinkDevAgentBridge(repo_dir=tmp_path)
    leaked_file = tmp_path / "internal.py"
    leaked_file.write_text("HOST = 'internal-host-example'\n", encoding="utf-8")

    hits = bridge._check_internal_leak([str(leaked_file)])
    assert len(hits) == 1
    assert "references internal pattern" in hits[0]


def test_safety_guardrails_prevent_main_branching() -> None:
    bridge = NexLinkDevAgentBridge(repo_dir=".")
    issue = AutoIssue(issue_id=1, title="Test", body="Body")

    with pytest.raises(SafetyViolationError, match="Base branch cannot be 'main'"):
        bridge.dispatch_agent(issue=issue, base_branch="main")

    with pytest.raises(SafetyViolationError, match="Base branch cannot be 'master'"):
        bridge.dispatch_agent(issue=issue, base_branch="master")


def test_safety_guardrails_prevent_force_and_create_repo() -> None:
    bridge = NexLinkDevAgentBridge(repo_dir=".")
    issue = AutoIssue(issue_id=1, title="Test", body="Body")

    with pytest.raises(SafetyViolationError, match="Force push is strictly forbidden"):
        bridge.dispatch_agent(issue=issue, base_branch="develop", force=True)

    with pytest.raises(SafetyViolationError, match="Creating repositories is strictly forbidden"):
        bridge.dispatch_agent(issue=issue, base_branch="develop", create_repo=True)


def test_agent_dispatch_success_flow(tmp_path: Path) -> None:
    # Set mock test and lint commands that exit 0
    bridge = NexLinkDevAgentBridge(
        repo_dir=tmp_path,
        test_command=["python", "-c", "exit(0)"],
        lint_command=["python", "-c", "exit(0)"],
    )
    issue = AutoIssue(issue_id=5, title="Clean code debt", body="Body")

    def mock_patch(root: Path) -> list[str]:
        p = root / "clean.py"
        p.write_text("print('clean')\n", encoding="utf-8")
        return [str(p)]

    result = bridge.dispatch_agent(issue=issue, base_branch="develop", patch_fn=mock_patch)

    assert result.success is True
    assert result.verification.is_all_green is True
    assert len(result.commits) == 1
    assert "feat(auto):" in result.commits[0]
