"""Competitor and market research snapshot diffing engine."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class CompetitorItem(BaseModel):
    name: str
    url: str | None = None
    key_features: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    pricing_tier: str | None = None


class ResearchSnapshot(BaseModel):
    topic: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    competitors: list[CompetitorItem] = Field(default_factory=list)
    market_gaps: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompetitorDiff(BaseModel):
    topic: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    added_competitors: list[str] = Field(default_factory=list)
    removed_competitors: list[str] = Field(default_factory=list)
    new_market_gaps: list[str] = Field(default_factory=list)
    closed_market_gaps: list[str] = Field(default_factory=list)
    new_features_by_competitor: dict[str, list[str]] = Field(default_factory=dict)
    summary_markdown: str = ""


class CompetitorDiffer:
    """Computes semantic and structural differences between successive research snapshots."""

    def diff_snapshots(self, previous: ResearchSnapshot, current: ResearchSnapshot) -> CompetitorDiff:
        """Compare two research runs and compute delta for planning."""
        prev_comp_map = {c.name.lower().strip(): c for c in previous.competitors}
        curr_comp_map = {c.name.lower().strip(): c for c in current.competitors}

        prev_names = set(prev_comp_map.keys())
        curr_names = set(curr_comp_map.keys())

        added = [curr_comp_map[k].name for k in curr_names - prev_names]
        removed = [prev_comp_map[k].name for k in prev_names - curr_names]

        # Compare features of surviving competitors
        new_features: dict[str, list[str]] = {}
        for name in curr_names.intersection(prev_names):
            old_feats = set(f.lower().strip() for f in prev_comp_map[name].key_features)
            recent_feats = [f for f in curr_comp_map[name].key_features if f.lower().strip() not in old_feats]
            if recent_feats:
                new_features[curr_comp_map[name].name] = recent_feats

        # Market gaps
        old_gaps = set(g.lower().strip() for g in previous.market_gaps)
        recent_gaps = set(g.lower().strip() for g in current.market_gaps)

        new_gaps = [g for g in current.market_gaps if g.lower().strip() not in old_gaps]
        closed_gaps = [g for g in previous.market_gaps if g.lower().strip() not in recent_gaps]

        # Markdown summary
        md_lines = [
            f"### Continuous Research Diff: {current.topic}",
            f"- **Added Competitors**: {', '.join(added) if added else 'None'}",
            f"- **Removed Competitors**: {', '.join(removed) if removed else 'None'}",
            f"- **New Market Gaps**: {', '.join(new_gaps) if new_gaps else 'None'}",
        ]
        if new_features:
            md_lines.append("- **New Features Detected**:")
            for comp, feats in new_features.items():
                md_lines.append(f"  - {comp}: {', '.join(feats)}")

        return CompetitorDiff(
            topic=current.topic,
            added_competitors=added,
            removed_competitors=removed,
            new_market_gaps=new_gaps,
            closed_market_gaps=closed_gaps,
            new_features_by_competitor=new_features,
            summary_markdown="\n".join(md_lines),
        )
