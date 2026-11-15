"""Data models for the code quality and architecture review."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class QualitySeverity(StrEnum):
    """Priority tiers of a quality finding. P1 is fixed first."""

    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class QualityCategory(StrEnum):
    """Families of problems the review looks for."""

    OVER_ENGINEERING = "over_engineering"
    DUPLICATION = "duplication"
    USELESS_WRAPPER = "useless_wrapper"
    TEMPORARY_SOLUTION = "temporary_solution"
    READABILITY = "readability"
    PERFORMANCE = "performance"
    DATA_MODELING = "data_modeling"
    STRUCTURE = "structure"
    BRANCHING = "branching"


_SEVERITY_ORDER = {QualitySeverity.P1: 0, QualitySeverity.P2: 1, QualitySeverity.P3: 2}


class QualityFinding(BaseModel):
    """One problem found by a detector, anchored at a file and line."""

    rule: str
    category: QualityCategory
    severity: QualitySeverity
    file_path: str
    line: int = Field(default=0, ge=0)  # 1-based; 0 means the finding is about the path itself
    end_line: int | None = None
    symbol: str = ""
    message: str
    suggestion: str
    related_locations: list[str] = Field(default_factory=list)

    @property
    def location(self) -> str:
        """Render the anchor as `file:line` (or only the path for path-level findings)."""
        return f"{self.file_path}:{self.line}" if self.line else self.file_path

    def sort_key(self) -> tuple[int, str, int, str]:
        return (_SEVERITY_ORDER[self.severity], self.file_path, self.line, self.rule)


class BranchInfo(BaseModel):
    """Branch facts supplied by the caller or collected from a local git repository."""

    name: str
    is_default: bool = False
    # Days since the branch diverged from the default branch, when the caller knows it.
    age_days: float | None = None
    # Days since the last commit on the branch tip.
    last_commit_age_days: float | None = None


class QualityThresholds(BaseModel):
    """Tunable limits used by the detectors."""

    max_function_lines: int = 50
    critical_function_lines: int = 100
    max_complexity: int = 10
    critical_complexity: int = 20
    max_parameters: int = 6
    max_nesting: int = 4
    duplicate_min_tokens: int = 40
    duplicate_similarity: float = Field(default=0.85, gt=0.0, le=1.0)
    duplicate_max_candidates: int = 1500
    max_files_per_dir: int = 25
    max_dir_depth: int = 6
    catch_all_module_symbols: int = 15
    long_lived_branch_days: int = 30


class QualityReport(BaseModel):
    """Prioritized result of a quality review over one target."""

    project_name: str
    target: str
    authorized_by: str = ""
    ownership: str = ""
    files_analyzed: int = 0
    symbols_analyzed: int = 0
    findings: list[QualityFinding] = Field(default_factory=list)

    def by_severity(self, severity: QualitySeverity | str) -> list[QualityFinding]:
        wanted = QualitySeverity(severity)
        return [f for f in self.findings if f.severity == wanted]

    def by_category(self, category: QualityCategory | str) -> list[QualityFinding]:
        wanted = QualityCategory(category)
        return [f for f in self.findings if f.category == wanted]

    def severity_counts(self) -> dict[str, int]:
        return {sev.value: len(self.by_severity(sev)) for sev in QualitySeverity}

    def category_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.category.value] = counts.get(finding.category.value, 0) + 1
        return dict(sorted(counts.items()))

    def to_markdown(self) -> str:
        """Render the prioritized report as Markdown."""
        counts = self.severity_counts()
        lines = [
            f"# Code Quality Review: {self.project_name}",
            "",
            f"- Files analyzed: {self.files_analyzed}",
            f"- Symbols analyzed: {self.symbols_analyzed}",
            f"- Findings: {len(self.findings)} "
            f"(P1: {counts['P1']}, P2: {counts['P2']}, P3: {counts['P3']})",
        ]
        if self.authorized_by:
            lines.append(f"- Target authorization: {self.ownership or 'owned'} (by {self.authorized_by})")

        titles = {
            QualitySeverity.P1: "P1 - fix first",
            QualitySeverity.P2: "P2 - plan next",
            QualitySeverity.P3: "P3 - clean up when touching the code",
        }
        for severity in QualitySeverity:
            group = self.by_severity(severity)
            if not group:
                continue
            lines.extend(["", f"## {titles[severity]}", ""])
            for finding in group:
                symbol = f" `{finding.symbol}`" if finding.symbol else ""
                tag = f"{finding.category.value}/{finding.rule}"
                lines.append(f"- `{finding.location}`{symbol} [{tag}] {finding.message}")
                lines.append(f"  - Suggestion: {finding.suggestion}")
                if finding.related_locations:
                    related = ", ".join(f"`{loc}`" for loc in finding.related_locations)
                    lines.append(f"  - Related: {related}")

        if not self.findings:
            lines.extend(["", "No quality findings."])
        return "\n".join(lines).strip() + "\n"


def sort_findings(findings: list[QualityFinding]) -> list[QualityFinding]:
    """Order findings by priority, then by file and line, so reports are deterministic."""
    return sorted(findings, key=QualityFinding.sort_key)


__all__ = [
    "BranchInfo",
    "QualityCategory",
    "QualityFinding",
    "QualityReport",
    "QualitySeverity",
    "QualityThresholds",
    "sort_findings",
]
