"""End-to-end offline round test simulating full continuous auto-improvement lifecycle.

Lifecycle:
1. Scanner detects technical debt / security smell
2. Issue is created on tracker with label 'auto' and Given/When/Then criteria
3. Development agent creates feature branch off 'develop' (never 'main')
4. Implementation is applied and verified locally (tests, lint, emoji, internal leak checks)
5. Merge engine merges into develop automatically
6. Never touches main; respects daily quota limit
7. Complete audit trail in AppendOnlyAuditLog
"""

import subprocess
from pathlib import Path

from nexcoder_continuous_improvement.auto_improve.agent_bridge import NexLinkDevAgentBridge
from nexcoder_continuous_improvement.auto_improve.issues import InMemoryIssueAdapter
from nexcoder_continuous_improvement.auto_improve.loop import AutoImproveLoop
from nexcoder_continuous_improvement.auto_improve.merger import AutoMergeEngine
from nexcoder_continuous_improvement.auto_improve.quota import DailyQuotaTracker
from nexcoder_continuous_improvement.auto_improve.scanner import RepoScanner
from nexcoder_control.metering.audit import AppendOnlyAuditLog


def init_git_repo(path: Path) -> None:
    """Initialize a git repo with develop and main branches."""
    subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "ThiagoVenturim"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "thiago@example.com"], cwd=path, capture_output=True, check=True)

    # Initial commit on main
    readme = path / "README.md"
    readme.write_text("# Project Root\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=path, capture_output=True, check=True)

    # Branch develop off main
    subprocess.run(["git", "branch", "develop"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "checkout", "develop"], cwd=path, capture_output=True, check=True)


def test_full_auto_improve_cycle_end_to_end(tmp_path: Path) -> None:
    # 1. Setup git repo with main and develop
    init_git_repo(tmp_path)

    # Record initial main commit sha
    main_sha_before = subprocess.run(
        ["git", "rev-parse", "main"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()

    # 2. Plant debt in repository on develop branch
    module_file = tmp_path / "service.py"
    module_file.write_text(
        "# TODO: refactor caching layer to use TTL cache\n"
        "def fetch_data():\n"
        "    return 42\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "service.py"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "feat: add service layer"], cwd=tmp_path, capture_output=True, check=True)

    # 3. Setup auto-improve loop components
    audit_log = AppendOnlyAuditLog()
    quota_tracker = DailyQuotaTracker(max_daily_merges=2)
    issue_adapter = InMemoryIssueAdapter()

    scanner = RepoScanner(root_path=tmp_path)
    agent_bridge = NexLinkDevAgentBridge(
        repo_dir=tmp_path,
        test_command=["python", "-c", "exit(0)"],
        lint_command=["python", "-c", "exit(0)"],
    )
    merge_engine = AutoMergeEngine(
        repo_dir=tmp_path,
        quota_tracker=quota_tracker,
        audit_log=audit_log,
    )

    loop = AutoImproveLoop(
        repo_path=tmp_path,
        max_daily_merges=2,
        quota_tracker=quota_tracker,
        audit_log=audit_log,
        issue_adapter=issue_adapter,
        scanner=scanner,
        agent_bridge=agent_bridge,
        merge_engine=merge_engine,
    )

    # Patch handler that fixes the TODO debt
    def fix_todo(repo: Path) -> list[str]:
        target = repo / "service.py"
        target.write_text(
            "# TTL cache refactored cleanly\n"
            "def fetch_data():\n"
            "    return 42\n",
            encoding="utf-8",
        )
        # Commit on the agent feature branch
        subprocess.run(["git", "add", "service.py"], cwd=repo, capture_output=True, check=True)
        commit_cmd = ["git", "commit", "-m", "feat(auto): refactor cache with TTL"]
        subprocess.run(commit_cmd, cwd=repo, capture_output=True, check=True)
        return [str(target)]

    # 4. Run cycle
    report = loop.run_cycle(
        dry_run=False,
        max_items=1,
        patch_handlers={"todo_debt": fix_todo},
    )

    # 5. Verify assertions
    assert report.status == "completed"
    assert report.findings_detected >= 1
    assert len(report.issues_created) == 1
    assert "auto" in report.issues_created[0].labels
    assert len(report.merges_executed) == 1

    # Verify develop was merged
    current_branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert current_branch == "develop"

    # Verify main branch was NEVER touched
    main_sha_after = subprocess.run(
        ["git", "rev-parse", "main"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert main_sha_before == main_sha_after

    # Verify daily quota was updated
    assert quota_tracker.get_used_today() == 1
    assert quota_tracker.get_remaining_today() == 1

    # Verify audit chain integrity
    assert audit_log.verify_integrity()[0] is True
    assert any(e.event_type == "auto_merge_develop" for e in audit_log._events)

    # Verify report is clean and informative
    assert "Auto-Improvement Cycle Report" in report.summary
    assert "feat/auto-issue-" in report.summary
