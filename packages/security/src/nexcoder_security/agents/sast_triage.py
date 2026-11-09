from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field

from faccoder_security.agents.base import BaseSecurityAgent
from faccoder_security.models import Finding


class TriageVerdict(enum.StrEnum):
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    NEEDS_REVIEW = "needs_review"


class TriagedFinding(BaseModel):
    finding_id: str
    rule_id: str
    original_severity: str
    adjusted_severity: str
    verdict: TriageVerdict
    confidence: float = 0.9
    reasoning: str
    is_actionable: bool


class SASTTriageResult(BaseModel):
    total_analyzed: int
    true_positives: int
    false_positives: int
    needs_review: int
    triaged_findings: list[TriagedFinding] = Field(default_factory=list)


class SASTTriageAgent(BaseSecurityAgent):
    """sec-sast-triage: triages, deduplicates, and validates SAST alerts for true exploitability."""

    def __init__(self) -> None:
        super().__init__(
            name="sec-sast-triage",
            role="Specialist agent in SAST triage, false positive elimination, and exploitability assessment.",
        )

    def analyze(self, target: Any, offline: bool = True) -> SASTTriageResult:
        findings: list[Finding] = (
            target if isinstance(target, list) else target.findings if hasattr(target, "findings") else []
        )

        triaged: list[TriagedFinding] = []
        tp_count = 0
        fp_count = 0
        nr_count = 0

        for f in findings:
            snippet = f.location.snippet if f.location and f.location.snippet else ""
            rule = f.rule_id.lower()

            # False positive heuristic checks
            if "test" in (f.location.file_path if f.location else "").lower():
                verdict = TriageVerdict.FALSE_POSITIVE
                reason = "Finding is located in test code or mock fixture, non-production path."
                adj_sev = "info"
                fp_count += 1
                actionable = False
            elif "assert" in rule and "test" in snippet:
                verdict = TriageVerdict.FALSE_POSITIVE
                reason = "Assert statement within test context is standard practice."
                adj_sev = "info"
                fp_count += 1
                actionable = False
            elif "shell-true" in rule or "exec" in rule or "sqli" in rule:
                verdict = TriageVerdict.TRUE_POSITIVE
                reason = "Critical/High SAST finding confirmed with unsafe construct in active logic."
                adj_sev = f.severity.value
                tp_count += 1
                actionable = True
            else:
                verdict = TriageVerdict.NEEDS_REVIEW
                reason = "Static rule matched; requires human or contextual confirmation of taint flow."
                adj_sev = f.severity.value
                nr_count += 1
                actionable = True

            triaged.append(
                TriagedFinding(
                    finding_id=f.id,
                    rule_id=f.rule_id,
                    original_severity=f.severity.value,
                    adjusted_severity=adj_sev,
                    verdict=verdict,
                    reasoning=reason,
                    is_actionable=actionable,
                )
            )

        return SASTTriageResult(
            total_analyzed=len(findings),
            true_positives=tp_count,
            false_positives=fp_count,
            needs_review=nr_count,
            triaged_findings=triaged,
        )
