"""Commercial proposal generator synthesizing executive quotes and disbursement schedules."""

from __future__ import annotations

from nexcoder_planning.cost.models import ProductCostReport


class CommercialProposalGenerator:
    """Formats product cost calculations into client-facing commercial proposals."""

    @staticmethod
    def generate(
        report: ProductCostReport,
        client_name: str = "Cliente",
        prepared_by: str = "NexCoder Commercial Squad",
        validity_days: int = 30,
    ) -> str:
        """Render a full commercial proposal in human-written markdown without emojis."""
        curr = report.currency.value
        rec_scenario_key = report.recommended_scenario
        rec_scenario = report.scenarios.get(rec_scenario_key) or list(report.scenarios.values())[0]

        lines: list[str] = [
            f"# Proposta Comercial e Orcamento Tecnico: {report.project_name}",
            "",
            f"**Destinatario**: {client_name}  ",
            f"**Elaborado por**: {prepared_by}  ",
            f"**Data de Emissao**: {report.created_at or '15/11/2026'}  ",
            f"**Validade da Proposta**: {validity_days} dias  ",
            f"**Moeda Base**: {curr} (Cambio referencial: 1 USD = {report.exchange_rate_usd_to_brl:.2f} BRL)  ",
            "",
            "---",
            "",
            "## 1. Sumario Executivo",
            "",
            "Esta proposta detalha a estimativa integral de custos para construcao, publicacao,",
            "sustentacao recorrente (mensal e anual), alem da protecao de marca e ativos de propriedade",
            f"intelectual do projeto **{report.project_name}**.",
            "",
            f"O modelo de execucao adotado e **{report.development_mode.value.replace('_', ' ').title()}**,",
            f"com o cenario **{rec_scenario_key.title()}** indicado como a melhor relacao custo-beneficio",
            "entre velocidade de entrega, robustez operacional e governanca orcamentaria.",
            "",
            "## 2. Comparativo de Cenarios (Ano 1 e Recorrencia)",
            "",
            report.summary_table(),
            "",
            "> Nota: O Cenario Medio equilibra custo e resiliencia de infraestrutura, com observabilidade",
            "> completa de processos e protecao juridica de marca. O Cenario Basico atende MVPs",
            "> e o Cenario Alto comporta demandas de alta volumetria e conformidade enterprise.",
            "",
            f"## 3. Detalhamento do Cenario Recomendado ({rec_scenario_key.title()})",
            "",
            f"| Categoria | Descricao do Item | Periodicidade | Valor ({curr}) | Fonte / Premissa |",
            "|---|---|---|---|---|",
        ]

        for it in rec_scenario.breakdown_items:
            lines.append(
                f"| {it.category.title()} | {it.name} | {it.billing_period.title()} | {it.amount:,.2f} | {it.source} |"
            )

        lines.extend([
            "",
            "### Resumo Financeiro Consolidado",
            f"- **Desenvolvimento Inicial**: {curr} {rec_scenario.development_cost:,.2f}",
            f"- **Publicacao e Setup**: {curr} {rec_scenario.publication_cost:,.2f}",
            f"- **Licenca e Marca (Inicial)**: {curr} {rec_scenario.license_and_brand_initial_cost:,.2f}",
            f"- **Custo Recorrente Mensal**: {curr} {rec_scenario.monthly_recurring_cost:,.2f} / mes",
            f"- **Custo Recorrente Anual (12m + renovacoes)**: {curr} {rec_scenario.annual_recurring_cost:,.2f} / ano",
            f"- **Reserva de Contingencia**: {curr} {rec_scenario.contingency_cost:,.2f}",
            f"- **Investimento Total Ano 1**: **{curr} {rec_scenario.year_one_total:,.2f}**",
            f"- **Recorrente Anos Seguintes**: **{curr} {rec_scenario.subsequent_years_annual_total:,.2f} / ano**",
            "",
            "## 4. Sugestao de Cronograma de Desembolso (Desenvolvimento)",
            "",
            "Para assegurar alinhamento e fluxo previsivel, sugere-se a divisao do valor de desenvolvimento:",
            f"1. **Entrada (40%)**: {curr} {rec_scenario.development_cost * 0.40:,.2f} na assinatura.",
            f"2. **Entrega MVP (35%)**: {curr} {rec_scenario.development_cost * 0.35:,.2f} apos validacao.",
            f"3. **Go-Live (25%)**: {curr} {rec_scenario.development_cost * 0.25:,.2f} na entrega tecnica.",
            "",
            "## 5. Premissas Tecnicas e Fontes Transparentes",
            "",
            "Todas as projecoes financeiras apoiam-se em tabelas atualizadas e fontes verificaveis:",
        ])

        for source in report.pricing_sources:
            lines.append(f"- {source}")

        lines.extend([
            "",
            "### Premissas Especificas Adotadas",
        ])
        for assumption in rec_scenario.assumptions:
            lines.append(f"- {assumption}")

        lines.extend([
            "",
            "---",
            f"*Proposta valida por {validity_days} dias a partir da data de emissao.*",
        ])

        return "\n".join(lines)
