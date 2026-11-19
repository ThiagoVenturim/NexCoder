"""Assisted prospecting and proposals (lead-gen) with ethics and legal guardrails.

Public sources only, passive observation of public pages only, and every e-mail goes
through human review and approval. See docs/leadgen.md.
"""

from __future__ import annotations

from nexcoder_agents.leadgen.assistant import LeadGenAssistant
from nexcoder_agents.leadgen.mockup import render_mockup
from nexcoder_agents.leadgen.models import (
    BusinessCandidate,
    CostSummary,
    LeadCandidate,
    LeadGenPolicyError,
    LeadProposal,
    OutreachDraft,
    PassiveSignal,
    SearchQuery,
    SignalCode,
    SiteObservation,
    SourceKind,
)
from nexcoder_agents.leadgen.outreach import (
    DailySendLimiter,
    DoNotContactList,
    OutreachDraftBuilder,
    OutreachPolicy,
    OutreachSender,
    ReviewRequest,
    check_draft_compliance,
    validate_subject,
)
from nexcoder_agents.leadgen.proposal import LeadProposalGenerator
from nexcoder_agents.leadgen.signals import (
    FetchResult,
    HttpxPageFetcher,
    PageFetcher,
    PassiveSiteInspector,
    analyze_html,
    require_authorized_security_target,
)
from nexcoder_agents.leadgen.sources import (
    BusinessSource,
    CsvOpenDataSource,
    StaticBusinessSource,
    ensure_legitimate_source,
    minimize_record,
)

__all__ = [
    "BusinessCandidate",
    "BusinessSource",
    "CostSummary",
    "CsvOpenDataSource",
    "DailySendLimiter",
    "DoNotContactList",
    "FetchResult",
    "HttpxPageFetcher",
    "LeadCandidate",
    "LeadGenAssistant",
    "LeadGenPolicyError",
    "LeadProposal",
    "LeadProposalGenerator",
    "OutreachDraft",
    "OutreachDraftBuilder",
    "OutreachPolicy",
    "OutreachSender",
    "PageFetcher",
    "PassiveSignal",
    "PassiveSiteInspector",
    "ReviewRequest",
    "SearchQuery",
    "SignalCode",
    "SiteObservation",
    "SourceKind",
    "StaticBusinessSource",
    "analyze_html",
    "check_draft_compliance",
    "ensure_legitimate_source",
    "minimize_record",
    "render_mockup",
    "require_authorized_security_target",
    "validate_subject",
]
