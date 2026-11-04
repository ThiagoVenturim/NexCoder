"""Unit tests for competitor and market research diffing."""

from faccoder_continuous_improvement.research.competitor_diff import (
    CompetitorDiffer,
    CompetitorItem,
    ResearchSnapshot,
)


def test_competitor_differ_detects_additions_and_gaps() -> None:
    differ = CompetitorDiffer()

    prev = ResearchSnapshot(
        topic="code-intelligence",
        competitors=[
            CompetitorItem(name="LegacyTool", key_features=["AST search"]),
        ],
        market_gaps=["Support for Delphi parsing"],
    )

    curr = ResearchSnapshot(
        topic="code-intelligence",
        competitors=[
            CompetitorItem(name="LegacyTool", key_features=["AST search", "GraphRAG"]),
            CompetitorItem(name="NewStartup", key_features=["Cloud IDE"]),
        ],
        market_gaps=["Support for COBOL parsing", "Support for Delphi parsing"],
    )

    diff = differ.diff_snapshots(prev, curr)

    assert "NewStartup" in diff.added_competitors
    assert not diff.removed_competitors
    assert "GraphRAG" in diff.new_features_by_competitor.get("LegacyTool", [])
    assert "Support for COBOL parsing" in diff.new_market_gaps
    assert "Continuous Research Diff" in diff.summary_markdown
