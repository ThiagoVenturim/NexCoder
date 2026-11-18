"""Unit tests for automated issue creation, formatting, and deduplication."""

from nexcoder_continuous_improvement.auto_improve.issues import AutoIssueManager, InMemoryIssueAdapter
from nexcoder_continuous_improvement.issues.planning_bridge import FindingCategory, ImprovementFinding


def test_issue_manager_creates_and_deduplicates() -> None:
    adapter = InMemoryIssueAdapter()
    manager = AutoIssueManager(adapter=adapter)

    finding = ImprovementFinding(
        category=FindingCategory.TODO_DEBT,
        title="Clean up legacy connection logic",
        description="Legacy connection logic should use ConnectionPool instead.",
        layer="core",
        recommended_agent="code-refactorer",
        estimate_points=2,
        priority="medium",
        acceptance_given="Legacy connection logic is currently invoked",
        acceptance_when="ConnectionPool refactoring is completed",
        acceptance_then="All tests pass offline",
        file_path="packages/core/src/db.py",
        line_number=45,
    )

    # First sync should create issue
    issue1 = manager.sync_finding_to_issue(finding)
    assert issue1.issue_id == 1
    assert "auto" in issue1.labels
    assert "type:todo_debt" in issue1.labels
    assert "layer:core" in issue1.labels
    assert "[AUTO] Clean up legacy" in issue1.title
    assert "**Given** Legacy connection logic" in issue1.body
    assert "<!-- nexcoder-auto-fingerprint:" in issue1.body

    # Second sync of same finding should deduplicate and return existing issue
    issue2 = manager.sync_finding_to_issue(finding)
    assert issue2.issue_id == issue1.issue_id
    assert len(adapter.issues) == 1


def test_issue_adapter_close() -> None:
    adapter = InMemoryIssueAdapter()
    iss = adapter.create_issue("Title", "Body", ["auto"])
    assert iss.status == "open"

    adapter.close_issue(iss.issue_id, comment="Fixed in commit 123")
    assert iss.status == "closed"
    assert iss.metadata.get("close_comment") == "Fixed in commit 123"
