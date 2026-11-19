"""Data models for assisted prospecting and proposal generation (lead-gen)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class LeadGenPolicyError(RuntimeError):
    """Raised when an operation would break the lead-gen ethics and legal guardrails."""


class SourceKind(StrEnum):
    """Kinds of business data sources that are acceptable for prospecting."""

    OFFICIAL_API = "official_api"
    OPEN_DATA = "open_data"
    LICENSED_DIRECTORY = "licensed_directory"


class SignalCode(StrEnum):
    """Passive, publicly observable signals about a business web presence."""

    NO_WEBSITE = "no_website"
    NO_HTTPS = "no_https"
    SITE_OFFLINE = "site_offline"
    OUTDATED_DESIGN = "outdated_design"
    NOT_RESPONSIVE = "not_responsive"
    NO_CONTACT_INFO = "no_contact_info"
    ROBOTS_DISALLOWED = "robots_disallowed"


class SearchQuery(BaseModel):
    """Region and segment to prospect."""

    region: str
    segment: str
    limit: int = Field(default=20, ge=1, le=100)


class BusinessCandidate(BaseModel):
    """Business-level public record. Never holds data about private individuals."""

    business_id: str
    name: str
    segment: str
    region: str
    website: str | None = None
    public_email: str | None = None
    public_phone: str | None = None
    address: str | None = None
    source: str
    source_kind: SourceKind
    source_reference: str = ""


class PassiveSignal(BaseModel):
    """One observation taken from the public home page only."""

    code: SignalCode
    detail: str
    weight: int = 1


class SiteObservation(BaseModel):
    """Result of a passive look at a business site (home page and robots.txt only)."""

    url: str | None
    reachable: bool = False
    status_code: int | None = None
    final_url: str | None = None
    signals: list[PassiveSignal] = Field(default_factory=list)
    requests_made: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def has(self, code: SignalCode) -> bool:
        return any(s.code == code for s in self.signals)

    @property
    def opportunity_score(self) -> int:
        return sum(s.weight for s in self.signals)


class LeadCandidate(BaseModel):
    """Business candidate together with its passive observation."""

    business: BusinessCandidate
    observation: SiteObservation

    @property
    def opportunity_score(self) -> int:
        return self.observation.opportunity_score


class CostSummary(BaseModel):
    """Short view of the product cost calculator report used in the proposal."""

    currency: str
    scenario: str
    development_cost: float
    publication_cost: float
    monthly_recurring_cost: float
    year_one_total: float
    estimated_hours: float
    assumptions: list[str] = Field(default_factory=list)
    report: dict[str, Any] = Field(default_factory=dict)


class LeadProposal(BaseModel):
    """Proposal for one business: diagnosis, suggestions, mockup and cost."""

    business: BusinessCandidate
    observation: SiteObservation
    diagnosis: list[str]
    suggestions: list[str]
    mockup_html: str
    cost: CostSummary
    report_markdown: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OutreachDraft(BaseModel):
    """Email draft for one business. A draft is never sent by itself."""

    draft_id: str
    business_id: str
    recipient: str
    subject: str
    body_text: str
    body_html: str
    headers: dict[str, str] = Field(default_factory=dict)
    attachments: dict[str, str] = Field(default_factory=dict)
    legal_basis: str
    status: Literal["draft", "pending_review", "sent", "rejected"] = "draft"
    review_token_id: str | None = None
