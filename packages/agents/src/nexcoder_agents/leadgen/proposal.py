"""Proposal for one business: diagnosis, suggestions, mockup and cost estimate."""

from __future__ import annotations

from nexcoder_planning.cost import (
    AISpec,
    CostScope,
    Currency,
    DevelopmentMode,
    InfrastructureTier,
    ProductCostCalculator,
    ProductCostInput,
    ProviderSpec,
    ScopeComplexity,
    TeamSpec,
)
from nexcoder_planning.cost.models import LicenseBrandSpec

from nexcoder_agents.leadgen.mockup import render_mockup
from nexcoder_agents.leadgen.models import CostSummary, LeadCandidate, LeadProposal, SignalCode

_DIAGNOSIS = {
    SignalCode.NO_WEBSITE: (
        "O negocio nao tem site proprio listado; clientes que pesquisam na internet nao o encontram."
    ),
    SignalCode.NO_HTTPS: "O site e servido sem HTTPS; navegadores mostram o aviso 'nao seguro' aos visitantes.",
    SignalCode.SITE_OFFLINE: "O site nao respondeu no momento da verificacao.",
    SignalCode.OUTDATED_DESIGN: "O visual usa recursos antigos de HTML, o que passa impressao de abandono.",
    SignalCode.NOT_RESPONSIVE: "A pagina nao se adapta a celulares, onde esta a maior parte das visitas.",
    SignalCode.NO_CONTACT_INFO: "A pagina inicial nao mostra telefone, e-mail ou formulario de contato.",
    SignalCode.ROBOTS_DISALLOWED: (
        "O site pede para nao ser lido por ferramentas automaticas; a pagina nao foi analisada."
    ),
}

_SUGGESTIONS = {
    SignalCode.NO_WEBSITE: "Criar um site simples de uma pagina com servicos, localizacao e contato.",
    SignalCode.NO_HTTPS: "Ativar HTTPS com certificado gratuito e redirecionar todo o trafego para HTTPS.",
    SignalCode.SITE_OFFLINE: "Revisar hospedagem e dominio e configurar monitoramento de disponibilidade.",
    SignalCode.OUTDATED_DESIGN: "Refazer o visual com layout moderno, imagens otimizadas e tipografia legivel.",
    SignalCode.NOT_RESPONSIVE: "Adotar layout responsivo testado em celular, tablet e desktop.",
    SignalCode.NO_CONTACT_INFO: "Colocar telefone, WhatsApp, e-mail e um formulario curto no topo da pagina.",
}

_DISCLAIMER = (
    "Diagnostico feito apenas com observacao passiva da pagina publica (como um visitante comum). "
    "Nenhum teste de seguranca ou varredura foi feito no site."
)


def _scope_for(candidate: LeadCandidate) -> CostScope:
    obs = candidate.observation
    rebuild = obs.has(SignalCode.NO_WEBSITE) or obs.has(SignalCode.OUTDATED_DESIGN) or obs.has(SignalCode.SITE_OFFLINE)
    features = 4 if rebuild else 2
    if obs.has(SignalCode.NO_CONTACT_INFO):
        features += 1
    return CostScope(
        project_name=f"Site {candidate.business.name}",
        description="Site institucional responsivo com HTTPS e contato",
        complexity=ScopeComplexity.LOW,
        feature_count=features,
        estimated_screens=4 if rebuild else 2,
        estimated_endpoints=1,
        stack="static_site",
        architecture_style="static",
    )


def _base_hours(candidate: LeadCandidate) -> float:
    """Base engineering hours for a small business site, before scenario multipliers."""
    obs = candidate.observation
    rebuild = obs.has(SignalCode.NO_WEBSITE) or obs.has(SignalCode.OUTDATED_DESIGN) or obs.has(SignalCode.SITE_OFFLINE)
    hours = 24.0 if rebuild else 10.0
    if obs.has(SignalCode.NOT_RESPONSIVE) and not rebuild:
        hours += 8.0
    if obs.has(SignalCode.NO_CONTACT_INFO):
        hours += 4.0
    if obs.has(SignalCode.NO_HTTPS):
        hours += 2.0
    return hours


class LeadProposalGenerator:
    """Builds a proposal for one lead and prices it with the product cost calculator."""

    def __init__(
        self,
        calculator: ProductCostCalculator | None = None,
        *,
        currency: Currency = Currency.BRL,
        hourly_rate: float | None = None,
        scenario: str = "basic",
    ) -> None:
        self.calculator = calculator or ProductCostCalculator()
        self.currency = currency
        self.hourly_rate = hourly_rate
        self.scenario = scenario

    def estimate_cost(self, candidate: LeadCandidate) -> CostSummary:
        scope = _scope_for(candidate)
        hours = _base_hours(candidate)
        spec = ProductCostInput(
            scope=scope,
            mode=DevelopmentMode.HYBRID,
            team=TeamSpec(roles={"mid": 1}, total_hours=hours, hourly_rate=self.hourly_rate),
            ai=AISpec(estimated_tokens_input=200_000, estimated_tokens_output=60_000, estimated_runs=3),
            providers=ProviderSpec(
                hosting_tier=InfrastructureTier.STARTER,
                email_provider="none",
                monitoring="free_tier",
            ),
            license_brand=LicenseBrandSpec(trademark_jurisdiction="none", include_legal_assistance=False),
            currency=self.currency,
        )
        report = self.calculator.calculate(spec)
        chosen = report.scenarios.get(self.scenario) or report.scenarios[report.recommended_scenario]

        return CostSummary(
            currency=str(report.currency),
            scenario=chosen.scenario,
            development_cost=chosen.development_cost,
            publication_cost=chosen.publication_cost,
            monthly_recurring_cost=chosen.monthly_recurring_cost,
            year_one_total=chosen.year_one_total,
            estimated_hours=hours,
            assumptions=list(chosen.assumptions),
            report=report.model_dump(mode="json"),
        )

    def generate(self, candidate: LeadCandidate) -> LeadProposal:
        obs = candidate.observation
        codes = [s.code for s in obs.signals]
        diagnosis = [_DIAGNOSIS[c] for c in codes if c in _DIAGNOSIS]
        if not diagnosis:
            diagnosis = ["Nenhum problema visivel foi encontrado na pagina publica."]
        suggestions = [_SUGGESTIONS[c] for c in codes if c in _SUGGESTIONS]
        if not suggestions:
            suggestions = ["Revisar conteudo e conversao do site atual."]
        mockup = render_mockup(candidate.business, obs)
        cost = self.estimate_cost(candidate)
        report = self._report_markdown(candidate, diagnosis, suggestions, cost)
        return LeadProposal(
            business=candidate.business,
            observation=obs,
            diagnosis=diagnosis,
            suggestions=suggestions,
            mockup_html=mockup,
            cost=cost,
            report_markdown=report,
        )

    @staticmethod
    def _report_markdown(
        candidate: LeadCandidate, diagnosis: list[str], suggestions: list[str], cost: CostSummary
    ) -> str:
        biz = candidate.business
        lines = [
            f"# Proposta de melhoria do site - {biz.name}",
            "",
            f"Segmento: {biz.segment}. Regiao: {biz.region}.",
            f"Site analisado: {candidate.observation.url or 'nenhum site listado'}.",
            "",
            "## Diagnostico",
            *[f"- {d}" for d in diagnosis],
            "",
            "## Sugestoes",
            *[f"- {s}" for s in suggestions],
            "",
            "## Estimativa",
            f"- Cenario: {cost.scenario}",
            f"- Horas estimadas: {cost.estimated_hours:.0f}",
            f"- Desenvolvimento: {cost.currency} {cost.development_cost:,.2f}",
            f"- Publicacao: {cost.currency} {cost.publication_cost:,.2f}",
            f"- Manutencao mensal: {cost.currency} {cost.monthly_recurring_cost:,.2f}",
            f"- Total no primeiro ano: {cost.currency} {cost.year_one_total:,.2f}",
            "",
            "Valores de referencia, calculados pela calculadora de custo do NexCoder; a proposta final e combinada.",
            "",
            f"_{_DISCLAIMER}_",
            "",
        ]
        return "\n".join(lines)
