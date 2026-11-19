"""End-to-end assistant: find candidates, build one proposal, prepare one draft."""

from __future__ import annotations

from nexcoder_control.metering.audit import AppendOnlyAuditLog

from nexcoder_agents.leadgen.models import (
    LeadCandidate,
    LeadGenPolicyError,
    LeadProposal,
    OutreachDraft,
    SearchQuery,
)
from nexcoder_agents.leadgen.outreach import DoNotContactList, OutreachDraftBuilder, OutreachPolicy
from nexcoder_agents.leadgen.proposal import LeadProposalGenerator
from nexcoder_agents.leadgen.signals import PassiveSiteInspector
from nexcoder_agents.leadgen.sources import BusinessSource, ensure_legitimate_source


class LeadGenAssistant:
    """Prospecting assistant. It prepares material for a human; it never sends by itself."""

    def __init__(
        self,
        sources: list[BusinessSource],
        policy: OutreachPolicy,
        *,
        inspector: PassiveSiteInspector | None = None,
        proposal_generator: LeadProposalGenerator | None = None,
        do_not_contact: DoNotContactList | None = None,
        audit_log: AppendOnlyAuditLog | None = None,
        actor: str = "leadgen-assistant",
    ) -> None:
        if not sources:
            raise LeadGenPolicyError("At least one public business source is required")
        for source in sources:
            ensure_legitimate_source(source)
        self.sources = list(sources)
        self.policy = policy
        self.inspector = inspector or PassiveSiteInspector()
        self.proposal_generator = proposal_generator or LeadProposalGenerator()
        self.do_not_contact = do_not_contact or DoNotContactList()
        self.drafts = OutreachDraftBuilder(policy, self.do_not_contact)
        self.audit_log = audit_log or AppendOnlyAuditLog()
        self.actor = actor

    def find_candidates(self, region: str, segment: str, limit: int = 20) -> list[LeadCandidate]:
        """List businesses for a region and segment, ranked by how much their web presence could improve."""
        query = SearchQuery(region=region, segment=segment, limit=limit)
        seen: set[str] = set()
        candidates: list[LeadCandidate] = []
        for source in self.sources:
            for business in source.search(query):
                key = f"{business.name.lower()}|{(business.address or '').lower()}"
                if key in seen:
                    continue
                seen.add(key)
                if business.public_email and self.do_not_contact.contains(business.public_email):
                    continue
                observation = self.inspector.inspect(business.website)
                candidates.append(LeadCandidate(business=business, observation=observation))
                if len(candidates) >= query.limit:
                    break
            if len(candidates) >= query.limit:
                break

        candidates.sort(key=lambda c: c.opportunity_score, reverse=True)
        self.audit_log.record_event(
            event_type="leadgen.search",
            actor=self.actor,
            action="find_candidates",
            resource=f"region:{region}|segment:{segment}",
            severity="info",
            details={
                "sources": [s.name for s in self.sources],
                "candidates": len(candidates),
                "requests": sum(len(c.observation.requests_made) for c in candidates),
            },
        )
        return candidates

    def build_proposal(self, candidate: LeadCandidate) -> LeadProposal:
        """Diagnosis, suggestions, mockup and cost for one business."""
        proposal = self.proposal_generator.generate(candidate)
        self.audit_log.record_event(
            event_type="leadgen.proposal",
            actor=self.actor,
            action="build_proposal",
            resource=f"business:{candidate.business.business_id}",
            severity="info",
            details={"signals": [s.code.value for s in candidate.observation.signals]},
        )
        return proposal

    def prepare_draft(self, proposal: LeadProposal, recipient: str | None = None) -> OutreachDraft:
        """Prepare, but do not send, an e-mail draft for one proposal."""
        draft = self.drafts.build(proposal, recipient=recipient)
        self.audit_log.record_event(
            event_type="leadgen.draft",
            actor=self.actor,
            action="prepare_draft",
            resource=f"draft:{draft.draft_id}",
            severity="info",
            details={"business_id": draft.business_id, "status": draft.status},
        )
        return draft
