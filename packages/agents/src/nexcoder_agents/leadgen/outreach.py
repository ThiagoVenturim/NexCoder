"""Outreach e-mail drafts and the human-approved send path.

Rules enforced here (LGPD, CAN-SPAM and common anti-spam practice):

- The sender is identified by name, organization, e-mail and postal address.
- The subject is honest: no fake replies or forwards, no invoices, no false urgency.
- Every message states that it is a commercial proposal, the legal basis, and carries
  an unsubscribe link plus a List-Unsubscribe header.
- A draft is never sent by itself. Each send needs a review request, a human approval
  code issued by the nexcoder-control approval tokens and the name of the approver.
- One recipient per send; there is no bulk path. A daily limit and a do-not-contact
  list are checked right before each send.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nexcoder_control.email.models import EmailAttachment, EmailMessage, EmailSendResult
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from pydantic import BaseModel, Field, field_validator

from nexcoder_agents.leadgen.models import LeadGenPolicyError, LeadProposal, OutreachDraft

DEFAULT_LEGAL_BASIS = (
    "Base legal: legitimo interesse (LGPD, art. 7, IX), usando apenas dados publicos de contato da empresa. "
    "Voce pode pedir a exclusao a qualquer momento pelo link de descadastro."
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DECEPTIVE_PREFIX = re.compile(r"^\s*(?:re|res|fw|fwd|enc|tr)\s*:", re.IGNORECASE)
_DECEPTIVE_WORDS = re.compile(
    r"\b(?:urgente|urgent|fatura|invoice|boleto|cobranca|pagamento pendente|payment due|"
    r"voce ganhou|you won|winner|premio|gratis|free money|ultima chance|last chance|"
    r"conta bloqueada|account suspended)\b",
    re.IGNORECASE,
)


def _normalize_address(value: str) -> str:
    return value.strip().lower()


def _hash_entry(value: str) -> str:
    return hashlib.sha256(_normalize_address(value).encode("utf-8")).hexdigest()


def validate_subject(subject: str) -> str:
    """Return the subject or raise if it is empty or misleading."""
    clean = subject.strip()
    if not clean:
        raise LeadGenPolicyError("Subject cannot be empty")
    if _DECEPTIVE_PREFIX.search(clean):
        raise LeadGenPolicyError("Subject must not pretend to be a reply or a forward")
    if _DECEPTIVE_WORDS.search(clean):
        raise LeadGenPolicyError("Subject must not use false urgency, billing or prize wording")
    if "!!" in clean:
        raise LeadGenPolicyError("Subject must not use repeated exclamation marks")
    letters = [c for c in clean if c.isalpha()]
    if len(letters) >= 8 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.6:
        raise LeadGenPolicyError("Subject must not be written in capitals")
    return clean


class OutreachPolicy(BaseModel):
    """Sender identity and compliance settings. All identity fields are required."""

    sender_name: str
    sender_organization: str
    sender_email: str
    postal_address: str
    unsubscribe_url: str
    legal_basis: str = DEFAULT_LEGAL_BASIS
    max_sends_per_day: int = Field(default=20, ge=1, le=200)

    @field_validator("sender_name", "sender_organization", "postal_address", "legal_basis")
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Sender identity, postal address and legal basis are required")
        return value.strip()

    @field_validator("sender_email")
    @classmethod
    def _valid_sender(cls, value: str) -> str:
        if not _EMAIL_RE.match(value.strip()):
            raise ValueError("sender_email must be a valid address")
        return value.strip()

    @field_validator("unsubscribe_url")
    @classmethod
    def _valid_unsubscribe(cls, value: str) -> str:
        clean = value.strip()
        if not (clean.startswith("https://") or clean.startswith("mailto:")):
            raise ValueError("unsubscribe_url must be an https:// or mailto: address")
        return clean

    def unsubscribe_link(self, opt_out_code: str) -> str:
        if "{code}" in self.unsubscribe_url:
            return self.unsubscribe_url.replace("{code}", opt_out_code)
        if self.unsubscribe_url.startswith("mailto:"):
            joiner = "&" if "?" in self.unsubscribe_url else "?"
            return f"{self.unsubscribe_url}{joiner}subject=descadastrar%20{opt_out_code}"
        joiner = "&" if "?" in self.unsubscribe_url else "?"
        return f"{self.unsubscribe_url}{joiner}code={opt_out_code}"


class DoNotContactList:
    """Opt-out list of addresses and domains. Stores only SHA-256 hashes, never plain addresses."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path).resolve() if path else None
        self._hashes: set[str] = set()
        self._lock = threading.Lock()
        if self._path and self._path.is_file():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._hashes = set(data.get("hashes", []))

    def add(self, address_or_domain: str) -> None:
        clean = _normalize_address(address_or_domain).lstrip("@")
        if not clean:
            raise ValueError("Empty do-not-contact entry")
        with self._lock:
            self._hashes.add(_hash_entry(clean))
            self._save()

    def contains(self, email: str) -> bool:
        clean = _normalize_address(email)
        domain = clean.rsplit("@", 1)[-1] if "@" in clean else clean
        with self._lock:
            return _hash_entry(clean) in self._hashes or _hash_entry(domain) in self._hashes

    def __len__(self) -> int:
        return len(self._hashes)

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"hashes": sorted(self._hashes)}, indent=2), encoding="utf-8")


class OutreachDraftBuilder:
    """Prepares an e-mail draft for one proposal. Never sends anything."""

    def __init__(self, policy: OutreachPolicy, do_not_contact: DoNotContactList | None = None) -> None:
        self.policy = policy
        self.do_not_contact = do_not_contact or DoNotContactList()

    def build(self, proposal: LeadProposal, recipient: str | None = None) -> OutreachDraft:
        biz = proposal.business
        to = (recipient or biz.public_email or "").strip()
        if not to or not _EMAIL_RE.match(to):
            raise LeadGenPolicyError(
                f"'{biz.name}' has no public business e-mail; contact must happen through its public channels"
            )
        if self.do_not_contact.contains(to):
            raise LeadGenPolicyError("Recipient is on the do-not-contact list")

        draft_id = f"drf_{uuid.uuid4().hex[:12]}"
        opt_out_code = hashlib.sha256(f"{draft_id}:{_normalize_address(to)}".encode()).hexdigest()[:16]
        unsubscribe = self.policy.unsubscribe_link(opt_out_code)
        subject = validate_subject(f"Proposta comercial: melhoria do site de {biz.name}")
        body_text = self._body_text(proposal, unsubscribe)
        body_html = self._body_html(body_text)

        headers = {"List-Unsubscribe": f"<{unsubscribe}>"}
        if unsubscribe.startswith("https://"):
            headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        return OutreachDraft(
            draft_id=draft_id,
            business_id=biz.business_id,
            recipient=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            headers=headers,
            attachments={
                "proposta.md": proposal.report_markdown,
                "mockup.html": proposal.mockup_html,
            },
            legal_basis=self.policy.legal_basis,
        )

    def _body_text(self, proposal: LeadProposal, unsubscribe: str) -> str:
        p = self.policy
        biz = proposal.business
        cost = proposal.cost
        lines = [
            f"Ola, equipe {biz.name}.",
            "",
            f"Sou {p.sender_name}, da {p.sender_organization}. Esta e uma mensagem comercial: "
            "preparamos uma proposta de melhoria do site de voces a partir de uma observacao da pagina publica.",
            "",
            "O que observamos:",
            *[f"- {d}" for d in proposal.diagnosis],
            "",
            "O que sugerimos:",
            *[f"- {s}" for s in proposal.suggestions],
            "",
            f"Estimativa de referencia: {cost.currency} {cost.year_one_total:,.2f} no primeiro ano "
            f"(cenario {cost.scenario}). Em anexo seguem o relatorio e um mockup de como o site poderia ficar.",
            "",
            "Se nao tiver interesse, basta ignorar esta mensagem ou usar o link de descadastro abaixo; "
            "nao enviaremos novos contatos.",
            "",
            "--",
            f"{p.sender_name} - {p.sender_organization}",
            f"{p.sender_email}",
            f"{p.postal_address}",
            "",
            p.legal_basis,
            f"Descadastrar: {unsubscribe}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _body_html(body_text: str) -> str:
        from html import escape

        paragraphs = body_text.split("\n\n")
        html_parts = ["<p>" + escape(par).replace("\n", "<br>") + "</p>" for par in paragraphs]
        return "\n".join(html_parts)


def check_draft_compliance(draft: OutreachDraft, policy: OutreachPolicy) -> None:
    """Raise if a draft is missing any mandatory compliance element."""
    validate_subject(draft.subject)
    body = draft.body_text
    required = {
        "sender name": policy.sender_name,
        "sender organization": policy.sender_organization,
        "sender e-mail": policy.sender_email,
        "postal address": policy.postal_address,
        "legal basis": policy.legal_basis,
        "commercial notice": "mensagem comercial",
        "unsubscribe link": "Descadastrar:",
    }
    missing = [label for label, needle in required.items() if needle not in body]
    if missing:
        raise LeadGenPolicyError(f"Draft is missing required compliance elements: {', '.join(missing)}")
    if "List-Unsubscribe" not in draft.headers:
        raise LeadGenPolicyError("Draft is missing the List-Unsubscribe header")


class ReviewRequest(BaseModel):
    """What the human reviewer receives: the preview and a single-use approval code."""

    draft_id: str
    token_id: str
    approval_code: str
    preview: dict[str, Any]


class DailySendLimiter:
    """Rolling 24 hour limit on outreach sends."""

    def __init__(self, max_per_day: int, clock: Callable[[], float] = time.time) -> None:
        self.max_per_day = max_per_day
        self._clock = clock
        self._sent: deque[float] = deque()
        self._lock = threading.Lock()

    def remaining(self) -> int:
        with self._lock:
            self._expire()
            return self.max_per_day - len(self._sent)

    def acquire(self) -> None:
        with self._lock:
            self._expire()
            if len(self._sent) >= self.max_per_day:
                raise LeadGenPolicyError(f"Daily outreach limit of {self.max_per_day} messages reached")
            self._sent.append(self._clock())

    def _expire(self) -> None:
        cutoff = self._clock() - 86_400
        while self._sent and self._sent[0] <= cutoff:
            self._sent.popleft()


def draft_to_message(draft: OutreachDraft, policy: OutreachPolicy) -> EmailMessage:
    return EmailMessage(
        subject=draft.subject,
        recipients=[draft.recipient],
        sender=policy.sender_email,
        body_text=draft.body_text,
        body_html=draft.body_html,
        headers=dict(draft.headers),
        attachments=[
            EmailAttachment(
                filename=name,
                content=content.encode("utf-8"),
                content_type="text/html" if name.endswith(".html") else "text/markdown",
            )
            for name, content in draft.attachments.items()
        ],
    )


def _fingerprint(draft: OutreachDraft) -> str:
    payload = json.dumps(
        {
            "recipient": draft.recipient,
            "subject": draft.subject,
            "body_text": draft.body_text,
            "body_html": draft.body_html,
            "headers": draft.headers,
            "attachments": draft.attachments,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class OutreachSender:
    """Sends one reviewed and approved draft at a time through the nexcoder-control EmailService."""

    def __init__(
        self,
        email_service: Any,
        policy: OutreachPolicy,
        do_not_contact: DoNotContactList | None = None,
        audit_log: AppendOnlyAuditLog | None = None,
        limiter: DailySendLimiter | None = None,
    ) -> None:
        settings = getattr(email_service, "settings", None)
        if settings is None or not getattr(settings, "require_human_approval", False):
            raise LeadGenPolicyError("Outreach requires an EmailService with require_human_approval=True")
        self.email_service = email_service
        self.policy = policy
        self.do_not_contact = do_not_contact or DoNotContactList()
        self.audit_log = audit_log or getattr(email_service, "audit_log", None) or AppendOnlyAuditLog()
        self.limiter = limiter or DailySendLimiter(policy.max_sends_per_day)
        self._pending: dict[str, str] = {}

    def submit_for_review(self, draft: OutreachDraft, reviewer: str) -> ReviewRequest:
        """Ask a human to review the draft. Returns the preview and the approval code for that human."""
        if not reviewer or not reviewer.strip():
            raise LeadGenPolicyError("A named human reviewer is required")
        if draft.status != "draft":
            raise LeadGenPolicyError(f"Draft {draft.draft_id} is '{draft.status}', not a fresh draft")
        check_draft_compliance(draft, self.policy)
        if self.do_not_contact.contains(draft.recipient):
            raise LeadGenPolicyError("Recipient is on the do-not-contact list")

        message = draft_to_message(draft, self.policy)
        token_id, approval_code, preview = self.email_service.request_approval(message, approver=reviewer.strip())
        draft.status = "pending_review"
        draft.review_token_id = token_id
        self._pending[draft.draft_id] = _fingerprint(draft)
        self._audit("leadgen.outreach.review_requested", reviewer, draft, {"token_id": token_id})
        return ReviewRequest(draft_id=draft.draft_id, token_id=token_id, approval_code=approval_code, preview=preview)

    def send_approved(self, draft: OutreachDraft, approval_code: str, approved_by: str) -> EmailSendResult:
        """Send one draft after a human approved it with the code from submit_for_review."""
        actor = (approved_by or "").strip()
        if not actor:
            raise LeadGenPolicyError("Sending requires the name of the human who approved the message")
        if not approval_code or not approval_code.strip():
            self._audit("leadgen.outreach.blocked", actor, draft, {"reason": "missing_approval"})
            raise LeadGenPolicyError("Sending requires the human approval code for this draft")
        expected = self._pending.get(draft.draft_id)
        if draft.status != "pending_review" or expected is None:
            self._audit("leadgen.outreach.blocked", actor, draft, {"reason": "not_reviewed"})
            raise LeadGenPolicyError("Draft was not submitted for human review")
        if _fingerprint(draft) != expected:
            self._audit("leadgen.outreach.blocked", actor, draft, {"reason": "changed_after_review"})
            raise LeadGenPolicyError("Draft changed after review; submit it for review again")
        check_draft_compliance(draft, self.policy)
        if self.do_not_contact.contains(draft.recipient):
            draft.status = "rejected"
            self._pending.pop(draft.draft_id, None)
            self._audit("leadgen.outreach.blocked", actor, draft, {"reason": "do_not_contact"})
            raise LeadGenPolicyError("Recipient opted out after review; message not sent")

        self.limiter.acquire()
        message = draft_to_message(draft, self.policy)
        result = self.email_service.send_email(message, approval_token=approval_code.strip(), actor=actor)
        if result.success:
            draft.status = "sent"
            self._pending.pop(draft.draft_id, None)
        self._audit("leadgen.outreach.sent", actor, draft, {"status": result.status, "success": result.success})
        return result

    def reject(self, draft: OutreachDraft, reviewer: str) -> None:
        draft.status = "rejected"
        self._pending.pop(draft.draft_id, None)
        self._audit("leadgen.outreach.rejected", reviewer or "reviewer", draft, {})

    def send_bulk(self, *args: Any, **kwargs: Any) -> None:
        """Bulk or automatic sending is not supported, by design."""
        raise LeadGenPolicyError("Bulk or automatic outreach is not allowed; each message needs its own approval")

    def record_opt_out(self, email: str) -> None:
        """Handle an unsubscribe request: the address is never contacted again."""
        self.do_not_contact.add(email)
        self.audit_log.record_event(
            event_type="leadgen.outreach.opt_out",
            actor="recipient",
            action="opt_out",
            resource=f"recipient:{_hash_entry(email)[:16]}",
            severity="info",
            details={},
        )

    def _audit(self, event_type: str, actor: str, draft: OutreachDraft, details: dict[str, Any]) -> None:
        self.audit_log.record_event(
            event_type=event_type,
            actor=actor,
            action=event_type.rsplit(".", 1)[-1],
            resource=f"draft:{draft.draft_id}",
            severity="warning" if event_type.endswith("blocked") else "info",
            details={"business_id": draft.business_id, **details},
        )
