"""Tests for assisted prospecting (lead-gen) and its ethics and legal guardrails.

Every source and fetcher here is mocked; no test touches the network.
"""

from __future__ import annotations

import ast
import socket
import subprocess
from pathlib import Path

import pytest
from nexcoder_agents.leadgen import (
    CsvOpenDataSource,
    DailySendLimiter,
    DoNotContactList,
    FetchResult,
    LeadGenAssistant,
    LeadGenPolicyError,
    OutreachPolicy,
    OutreachSender,
    PassiveSiteInspector,
    SignalCode,
    SourceKind,
    StaticBusinessSource,
    analyze_html,
    check_draft_compliance,
    ensure_legitimate_source,
    require_authorized_security_target,
    validate_subject,
)
from nexcoder_control.approval.target_gate import TargetAuthorizationGate, TargetNotAuthorizedError
from nexcoder_control.approval.tokens import ApprovalRequiredError, ApprovalTokenManager
from nexcoder_control.email.config import EmailSettings
from nexcoder_control.email.connectors.base import BaseEmailConnector
from nexcoder_control.email.models import EmailMessage, EmailSendResult
from nexcoder_control.email.service import EmailService
from nexcoder_control.metering.audit import AppendOnlyAuditLog

LEADGEN_SRC = Path(__file__).resolve().parents[1] / "src" / "nexcoder_agents" / "leadgen"

OLD_PAGE = """<html><head><title>Padaria</title></head>
<body bgcolor="#ffffff"><center><font face="Arial">Bem-vindo</font></center>
<table bgcolor="#eeeeee" cellpadding="2"><tr><td>Paes</td></tr></table>
<p>&copy; 2009 Padaria</p></body></html>"""

MODERN_PAGE = """<!doctype html><html><head>
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body><h1>Padaria Moderna</h1><a href="tel:+551100000000">Ligue</a><p>&copy; 2026</p></body></html>"""

RECORDS = [
    {
        "business_id": "b1",
        "name": "Padaria Sem Site",
        "segment": "padaria",
        "region": "Vitoria - ES",
        "public_email": "contato@padaria-sem-site.example",
        "public_phone": "+55 27 0000-0001",
        "owner_name": "Pessoa Fisica",
        "owner_cpf": "123.456.789-09",
    },
    {
        "business_id": "b2",
        "name": "Padaria Antiga",
        "segment": "padaria",
        "region": "Vitoria - ES",
        "website": "http://padaria-antiga.example",
        "public_email": "contato@padaria-antiga.example",
        "address": "Rua Exemplo, 100",
    },
    {
        "business_id": "b3",
        "name": "Padaria Moderna",
        "segment": "padaria",
        "region": "Vitoria - ES",
        "website": "https://padaria-moderna.example",
        "public_email": "ola@padaria-moderna.example",
    },
    {
        "business_id": "b4",
        "name": "Oficina Fora do Segmento",
        "segment": "oficina mecanica",
        "region": "Vitoria - ES",
    },
    {
        "business_id": "b5",
        "name": "Padaria Outra Cidade",
        "segment": "padaria",
        "region": "Recife - PE",
    },
]


class FakeFetcher:
    """Records every request; answers from a fixed table. Never touches the network."""

    def __init__(self, pages: dict[str, FetchResult]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url: str) -> FetchResult:
        self.calls.append(url)
        if url in self.pages:
            return self.pages[url]
        if url.endswith("/robots.txt"):
            return FetchResult(url=url, status_code=404, final_url=url)
        return FetchResult(url=url, error="ConnectError")


def default_pages() -> dict[str, FetchResult]:
    return {
        "http://padaria-antiga.example/": FetchResult(
            url="http://padaria-antiga.example/",
            status_code=200,
            final_url="http://padaria-antiga.example/",
            text=OLD_PAGE,
        ),
        "https://padaria-moderna.example/": FetchResult(
            url="https://padaria-moderna.example/",
            status_code=200,
            final_url="https://padaria-moderna.example/",
            text=MODERN_PAGE,
        ),
    }


class RecordingConnector(BaseEmailConnector):
    provider_name = "smtp"

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def is_configured(self) -> bool:
        return True

    def get_sender(self) -> str:
        return "vendas@agencia.example"

    def send(self, message: EmailMessage) -> EmailSendResult:
        self.sent.append(message)
        return EmailSendResult(
            success=True,
            provider="smtp",
            message_id=f"msg_{len(self.sent)}",
            sender=self.get_sender(),
            recipients=message.normalized_recipients(),
        )


@pytest.fixture()
def policy() -> OutreachPolicy:
    return OutreachPolicy(
        sender_name="Ana Exemplo",
        sender_organization="Agencia Exemplo",
        sender_email="vendas@agencia.example",
        postal_address="Av. Exemplo, 1000, Vitoria - ES",
        unsubscribe_url="https://agencia.example/descadastro?c={code}",
    )


@pytest.fixture()
def fetcher() -> FakeFetcher:
    return FakeFetcher(default_pages())


@pytest.fixture()
def assistant(policy: OutreachPolicy, fetcher: FakeFetcher) -> LeadGenAssistant:
    inspector = PassiveSiteInspector(fetcher, sleep=lambda s: None, current_year=2026)
    return LeadGenAssistant([StaticBusinessSource(RECORDS)], policy, inspector=inspector)


@pytest.fixture()
def no_active_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any raw socket or subprocess use during lead-gen fails the test."""

    def forbidden(*args, **kwargs):
        raise AssertionError("lead-gen must not open sockets or run external tools")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


def make_email_service(connector: RecordingConnector, *, require_approval: bool = True) -> EmailService:
    return EmailService(
        settings=EmailSettings(require_human_approval=require_approval, default_provider="smtp"),
        audit_log=AppendOnlyAuditLog(auto_persist=False),
        token_manager=ApprovalTokenManager(),
        smtp_connector=connector,
    )


# Search and candidates


def test_find_candidates_by_region_and_segment(assistant: LeadGenAssistant, no_active_network: None) -> None:
    candidates = assistant.find_candidates("Vitoria", "padaria")
    names = [c.business.name for c in candidates]
    assert set(names) == {"Padaria Sem Site", "Padaria Antiga", "Padaria Moderna"}
    # Ranked by opportunity: no site and old site come before the modern one.
    assert names[-1] == "Padaria Moderna"
    by_name = {c.business.name: c for c in candidates}
    assert by_name["Padaria Sem Site"].observation.has(SignalCode.NO_WEBSITE)
    old = by_name["Padaria Antiga"].observation
    assert old.has(SignalCode.NO_HTTPS)
    assert old.has(SignalCode.OUTDATED_DESIGN)
    assert old.has(SignalCode.NOT_RESPONSIVE)
    assert old.has(SignalCode.NO_CONTACT_INFO)
    assert by_name["Padaria Moderna"].observation.signals == []


def test_records_are_minimized_to_business_fields(assistant: LeadGenAssistant) -> None:
    candidates = assistant.find_candidates("Vitoria", "padaria")
    no_site = next(c for c in candidates if c.business.business_id == "b1")
    dumped = no_site.business.model_dump_json()
    assert "Pessoa Fisica" not in dumped
    assert "123.456.789-09" not in dumped
    assert no_site.business.source_kind == SourceKind.OPEN_DATA


def test_csv_open_data_source(tmp_path: Path, policy: OutreachPolicy, fetcher: FakeFetcher) -> None:
    csv_file = tmp_path / "empresas.csv"
    csv_file.write_text(
        "name,segment,region,website,socio\nCafe Aberto,cafeteria,Serra - ES,,Nome De Socio\n",
        encoding="utf-8",
    )
    source = CsvOpenDataSource(csv_file, terms_reference="Open data license of the portal")
    inspector = PassiveSiteInspector(fetcher, sleep=lambda s: None)
    found = LeadGenAssistant([source], policy, inspector=inspector).find_candidates("Serra", "cafe")
    assert [c.business.name for c in found] == ["Cafe Aberto"]
    assert "Nome De Socio" not in found[0].business.model_dump_json()
    assert found[0].business.business_id.startswith("biz_")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": "scraped-leads"}, "scraped or purchased"),
        ({"name": "lista-comprada"}, "scraped or purchased"),
        ({"allows_automated_access": False}, "terms allow"),
        ({"terms_reference": " "}, "terms of use"),
    ],
)
def test_illegitimate_sources_are_refused(kwargs: dict, message: str, policy: OutreachPolicy) -> None:
    source = StaticBusinessSource(RECORDS, **kwargs)
    with pytest.raises(LeadGenPolicyError, match=message):
        ensure_legitimate_source(source)
    with pytest.raises(LeadGenPolicyError):
        LeadGenAssistant([source], policy)


def test_unknown_source_kind_is_refused() -> None:
    source = StaticBusinessSource(RECORDS)
    source.kind = "web_scraper"  # type: ignore[assignment]
    with pytest.raises(LeadGenPolicyError, match="not accepted"):
        ensure_legitimate_source(source)


def test_do_not_contact_businesses_are_skipped(policy: OutreachPolicy, fetcher: FakeFetcher) -> None:
    dnc = DoNotContactList()
    dnc.add("padaria-antiga.example")
    inspector = PassiveSiteInspector(fetcher, sleep=lambda s: None)
    assistant = LeadGenAssistant([StaticBusinessSource(RECORDS)], policy, inspector=inspector, do_not_contact=dnc)
    names = [c.business.name for c in assistant.find_candidates("Vitoria", "padaria")]
    assert "Padaria Antiga" not in names


# Guardrail: passive observation only, no active scan


def test_inspection_only_requests_robots_and_home_page(
    assistant: LeadGenAssistant, fetcher: FakeFetcher, no_active_network: None
) -> None:
    assistant.find_candidates("Vitoria", "padaria")
    assert sorted(fetcher.calls) == sorted(
        [
            "http://padaria-antiga.example/robots.txt",
            "http://padaria-antiga.example/",
            "https://padaria-moderna.example/robots.txt",
            "https://padaria-moderna.example/",
        ]
    )
    # Exactly one GET per URL, no extra paths, ports or parameters.
    assert len(fetcher.calls) == len(set(fetcher.calls))


def test_query_parameters_are_never_sent(fetcher: FakeFetcher, no_active_network: None) -> None:
    inspector = PassiveSiteInspector(fetcher, sleep=lambda s: None)
    obs = inspector.inspect("http://padaria-antiga.example/?id=1' OR '1'='1")
    assert all("?" not in call for call in fetcher.calls)
    assert obs.requests_made == ["GET http://padaria-antiga.example/robots.txt", "GET http://padaria-antiga.example/"]


def test_inspector_refuses_any_other_url(fetcher: FakeFetcher) -> None:
    inspector = PassiveSiteInspector(fetcher, sleep=lambda s: None)
    allowed = {"https://padaria-moderna.example/robots.txt", "https://padaria-moderna.example/"}
    with pytest.raises(LeadGenPolicyError, match="only request the home page"):
        inspector._polite_get("https://padaria-moderna.example/admin/", allowed, [])
    assert fetcher.calls == []


def test_robots_disallow_is_respected(no_active_network: None) -> None:
    fetcher = FakeFetcher(
        {
            "https://fechado.example/robots.txt": FetchResult(
                url="https://fechado.example/robots.txt", status_code=200, text="User-agent: *\nDisallow: /\n"
            )
        }
    )
    obs = PassiveSiteInspector(fetcher, sleep=lambda s: None).inspect("https://fechado.example")
    assert fetcher.calls == ["https://fechado.example/robots.txt"]
    assert obs.has(SignalCode.ROBOTS_DISALLOWED)


def test_offline_site_is_reported_without_retries(no_active_network: None) -> None:
    fetcher = FakeFetcher({})
    fetcher.pages["https://fora.example/robots.txt"] = FetchResult(url="x", error="ConnectError")
    obs = PassiveSiteInspector(fetcher, sleep=lambda s: None).inspect("https://fora.example")
    assert obs.has(SignalCode.SITE_OFFLINE)
    assert fetcher.calls == ["https://fora.example/robots.txt"]


def test_polite_delay_between_requests_to_same_host(fetcher: FakeFetcher) -> None:
    waits: list[float] = []
    inspector = PassiveSiteInspector(fetcher, sleep=waits.append, clock=lambda: 100.0, min_interval_seconds=1.5)
    inspector.inspect("https://padaria-moderna.example")
    assert waits == [1.5]


def test_security_assessment_of_third_party_site_requires_gate() -> None:
    audit = AppendOnlyAuditLog(auto_persist=False)
    gate = TargetAuthorizationGate(audit_log=audit)
    with pytest.raises(TargetNotAuthorizedError):
        require_authorized_security_target(gate, "https://padaria-antiga.example")
    denied = [e for e in audit.query() if e.event_type == "target.authorization.denied"]
    assert len(denied) == 1
    with pytest.raises(LeadGenPolicyError):
        require_authorized_security_target(None, "https://padaria-antiga.example")
    # An owner who marks the target can move on to nexcoder-security.
    record = require_authorized_security_target(
        gate, "https://meu-site.example", owned_target=True, authorized_by="owner"
    )
    assert record.ownership == "owned"


def test_leadgen_source_has_no_scanner_or_raw_network_code() -> None:
    forbidden_imports = {"socket", "subprocess", "nmap", "scapy", "nexcoder_security"}
    forbidden_names = {"nmap", "masscan", "nikto", "sqlmap", "zmap", "MultiScannerEngine", "gate_active_scan"}
    for path in LEADGEN_SRC.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not {a.name.split(".")[0] for a in node.names} & forbidden_imports, path.name
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in forbidden_imports, path.name
            elif isinstance(node, ast.Name):
                assert node.id not in forbidden_names, path.name
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"post", "put", "delete", "patch", "options", "head"}, path.name


def test_analyze_html_detects_signals() -> None:
    codes = {s.code for s in analyze_html(OLD_PAGE, current_year=2026)}
    assert codes == {SignalCode.OUTDATED_DESIGN, SignalCode.NOT_RESPONSIVE, SignalCode.NO_CONTACT_INFO}
    assert analyze_html(MODERN_PAGE, current_year=2026) == []


# Proposal with mockup and cost


def test_proposal_for_one_business_has_mockup_and_cost(assistant: LeadGenAssistant) -> None:
    candidates = assistant.find_candidates("Vitoria", "padaria")
    old = next(c for c in candidates if c.business.name == "Padaria Antiga")
    proposal = assistant.build_proposal(old)

    assert any("HTTPS" in d for d in proposal.diagnosis)
    assert any("responsivo" in s for s in proposal.suggestions)
    assert '<meta name="viewport"' in proposal.mockup_html
    assert "Padaria Antiga" in proposal.mockup_html
    assert proposal.cost.currency == "BRL"
    assert proposal.cost.year_one_total > 0
    assert proposal.cost.development_cost > 0
    assert proposal.cost.report["scenarios"]["basic"]["year_one_total"] == proposal.cost.year_one_total
    assert "Nenhum teste de seguranca" in proposal.report_markdown


def test_mockup_escapes_business_values(assistant: LeadGenAssistant) -> None:
    candidates = assistant.find_candidates("Vitoria", "padaria")
    cand = candidates[0]
    cand.business.name = "<script>alert(1)</script>"
    proposal = assistant.build_proposal(cand)
    assert "<script>" not in proposal.mockup_html


# Draft preparation (never sends)


def test_prepare_draft_is_compliant_and_sends_nothing(assistant: LeadGenAssistant, policy: OutreachPolicy) -> None:
    connector = RecordingConnector()
    make_email_service(connector)
    candidates = assistant.find_candidates("Vitoria", "padaria")
    proposal = assistant.build_proposal(candidates[0])
    draft = assistant.prepare_draft(proposal)

    assert draft.status == "draft"
    assert connector.sent == []
    check_draft_compliance(draft, policy)
    assert "Ana Exemplo" in draft.body_text
    assert "Agencia Exemplo" in draft.body_text
    assert "Av. Exemplo, 1000" in draft.body_text
    assert "mensagem comercial" in draft.body_text
    assert "LGPD" in draft.body_text
    assert "https://agencia.example/descadastro?c=" in draft.body_text
    assert draft.headers["List-Unsubscribe"].startswith("<https://agencia.example/descadastro")
    assert draft.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert draft.subject.startswith("Proposta comercial")
    assert set(draft.attachments) == {"proposta.md", "mockup.html"}


def test_draft_requires_public_business_email(assistant: LeadGenAssistant) -> None:
    candidates = assistant.find_candidates("Vitoria", "padaria")
    proposal = assistant.build_proposal(candidates[0])
    proposal.business.public_email = None
    with pytest.raises(LeadGenPolicyError, match="no public business e-mail"):
        assistant.prepare_draft(proposal)


@pytest.mark.parametrize(
    "subject",
    ["RE: nossa conversa", "Fwd: proposta", "Fatura em aberto", "URGENTE seu site", "Voce ganhou um site", "Oi!!"],
)
def test_misleading_subjects_are_refused(subject: str) -> None:
    with pytest.raises(LeadGenPolicyError):
        validate_subject(subject)


def test_policy_requires_sender_identity_and_unsubscribe() -> None:
    with pytest.raises(ValueError):
        OutreachPolicy(
            sender_name="",
            sender_organization="Agencia",
            sender_email="vendas@agencia.example",
            postal_address="Rua 1",
            unsubscribe_url="https://agencia.example/sair",
        )
    with pytest.raises(ValueError):
        OutreachPolicy(
            sender_name="Ana",
            sender_organization="Agencia",
            sender_email="vendas@agencia.example",
            postal_address="Rua 1",
            unsubscribe_url="http://agencia.example/sair",
        )


# Guardrail: no send without human approval


@pytest.fixture()
def draft_setup(assistant: LeadGenAssistant, policy: OutreachPolicy):
    connector = RecordingConnector()
    service = make_email_service(connector)
    sender = OutreachSender(service, policy)
    candidates = assistant.find_candidates("Vitoria", "padaria")
    proposal = assistant.build_proposal(candidates[0])
    draft = assistant.prepare_draft(proposal)
    return connector, service, sender, draft


def test_no_send_without_review(draft_setup) -> None:
    connector, _service, sender, draft = draft_setup
    with pytest.raises(LeadGenPolicyError, match="not submitted for human review"):
        sender.send_approved(draft, approval_code="anything", approved_by="Ana")
    assert connector.sent == []


def test_no_send_without_approval_code_or_approver(draft_setup) -> None:
    connector, _service, sender, draft = draft_setup
    sender.submit_for_review(draft, reviewer="Ana")
    with pytest.raises(LeadGenPolicyError, match="approval code"):
        sender.send_approved(draft, approval_code="", approved_by="Ana")
    with pytest.raises(LeadGenPolicyError, match="name of the human"):
        sender.send_approved(draft, approval_code="x", approved_by=" ")
    assert connector.sent == []


def test_no_send_with_invalid_approval_code(draft_setup) -> None:
    connector, _service, sender, draft = draft_setup
    sender.submit_for_review(draft, reviewer="Ana")
    with pytest.raises(ApprovalRequiredError):
        sender.send_approved(draft, approval_code="fc_apr_forged", approved_by="Ana")
    assert connector.sent == []


def test_submit_for_review_sends_nothing_and_shows_preview(draft_setup) -> None:
    connector, service, sender, draft = draft_setup
    review = sender.submit_for_review(draft, reviewer="Ana")
    assert connector.sent == []
    assert draft.status == "pending_review"
    assert review.preview["recipients"] == [draft.recipient]
    assert review.preview["subject"] == draft.subject
    events = [e.event_type for e in service.audit_log.query()]
    assert "email_approval_requested" in events
    assert "leadgen.outreach.review_requested" in events


def test_send_after_human_approval_sends_exactly_one(draft_setup) -> None:
    connector, service, sender, draft = draft_setup
    review = sender.submit_for_review(draft, reviewer="Ana")
    result = sender.send_approved(draft, approval_code=review.approval_code, approved_by="Ana")
    assert result.success is True
    assert len(connector.sent) == 1
    sent = connector.sent[0]
    assert sent.normalized_recipients() == [draft.recipient]
    assert sent.sender == "vendas@agencia.example"
    assert "List-Unsubscribe" in sent.headers
    assert draft.status == "sent"
    # The approval is single use and the draft cannot be sent twice.
    with pytest.raises(LeadGenPolicyError):
        sender.send_approved(draft, approval_code=review.approval_code, approved_by="Ana")
    assert len(connector.sent) == 1
    ok, _ = service.audit_log.verify_integrity()
    assert ok


def test_changes_after_review_block_the_send(draft_setup) -> None:
    connector, _service, sender, draft = draft_setup
    review = sender.submit_for_review(draft, reviewer="Ana")
    draft.recipient = "outra@empresa.example"
    with pytest.raises(LeadGenPolicyError, match="changed after review"):
        sender.send_approved(draft, approval_code=review.approval_code, approved_by="Ana")
    assert connector.sent == []


def test_opt_out_after_review_blocks_the_send(draft_setup) -> None:
    connector, _service, sender, draft = draft_setup
    review = sender.submit_for_review(draft, reviewer="Ana")
    sender.record_opt_out(draft.recipient)
    with pytest.raises(LeadGenPolicyError, match="opted out"):
        sender.send_approved(draft, approval_code=review.approval_code, approved_by="Ana")
    assert connector.sent == []


def test_bulk_send_is_not_available(draft_setup) -> None:
    connector, _service, sender, draft = draft_setup
    with pytest.raises(LeadGenPolicyError, match="Bulk"):
        sender.send_bulk([draft])
    assert connector.sent == []


def test_service_without_human_approval_is_refused(policy: OutreachPolicy) -> None:
    service = make_email_service(RecordingConnector(), require_approval=False)
    with pytest.raises(LeadGenPolicyError, match="require_human_approval"):
        OutreachSender(service, policy)


def test_daily_limit(assistant: LeadGenAssistant, policy: OutreachPolicy) -> None:
    connector = RecordingConnector()
    sender = OutreachSender(make_email_service(connector), policy, limiter=DailySendLimiter(1))
    candidates = [c for c in assistant.find_candidates("Vitoria", "padaria") if c.business.public_email]
    drafts = [assistant.prepare_draft(assistant.build_proposal(c)) for c in candidates[:2]]
    first = sender.submit_for_review(drafts[0], reviewer="Ana")
    sender.send_approved(drafts[0], first.approval_code, approved_by="Ana")
    second = sender.submit_for_review(drafts[1], reviewer="Ana")
    with pytest.raises(LeadGenPolicyError, match="Daily outreach limit"):
        sender.send_approved(drafts[1], second.approval_code, approved_by="Ana")
    assert len(connector.sent) == 1


def test_do_not_contact_list_stores_only_hashes(tmp_path: Path) -> None:
    path = tmp_path / "dnc.json"
    dnc = DoNotContactList(path)
    dnc.add("Contato@Padaria.example")
    assert "padaria" not in path.read_text(encoding="utf-8").lower()
    reloaded = DoNotContactList(path)
    assert reloaded.contains("contato@padaria.example")
    assert not reloaded.contains("outro@padaria.example")
    reloaded.add("@padaria.example")
    assert reloaded.contains("outro@padaria.example")
