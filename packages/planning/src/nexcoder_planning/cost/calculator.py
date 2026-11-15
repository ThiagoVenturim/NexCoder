"""Core product cost calculator for build, publish, maintenance, license, and brand."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nexcoder_planning.cost.catalog import PricingCatalog
from nexcoder_planning.cost.models import (
    CostItemBreakdown,
    CostScenarioDetail,
    CostScope,
    Currency,
    DevelopmentMode,
    InfrastructureTier,
    ProductCostInput,
    ProductCostReport,
    ScopeComplexity,
    TeamSpec,
)


class ProductCostCalculator:
    """Calculates granular product costs across development, publication, recurring, and IP."""

    def __init__(self, catalog: PricingCatalog | None = None) -> None:
        self.catalog = catalog or PricingCatalog()

    def calculate(self, input_spec: ProductCostInput) -> ProductCostReport:
        """Execute cost computation across basic, medium, and high scenarios."""
        curr = input_spec.currency
        rate = input_spec.exchange_rate_usd_to_brl

        scenarios: dict[str, CostScenarioDetail] = {
            "basic": self._compute_scenario("basic", input_spec, curr, rate),
            "medium": self._compute_scenario("medium", input_spec, curr, rate),
            "high": self._compute_scenario("high", input_spec, curr, rate),
        }

        sources = self.catalog.get_registered_sources()

        control_plane_meta: dict[str, Any] = {}
        if input_spec.ai.control_plane_cost_usd is not None:
            control_plane_meta = {
                "real_cost_usd": input_spec.ai.control_plane_cost_usd,
                "input_tokens": input_spec.ai.estimated_tokens_input,
                "output_tokens": input_spec.ai.estimated_tokens_output,
                "runs": input_spec.ai.estimated_runs,
                "metadata": input_spec.ai.control_plane_metadata,
            }

        return ProductCostReport(
            project_name=input_spec.scope.project_name,
            currency=curr,
            exchange_rate_usd_to_brl=rate,
            development_mode=input_spec.mode,
            scenarios=scenarios,
            recommended_scenario="medium",
            pricing_sources=sources,
            control_plane_integration=control_plane_meta,
            created_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

    def _compute_scenario(
        self,
        scenario_key: str,
        input_spec: ProductCostInput,
        curr: Currency,
        rate: float,
    ) -> CostScenarioDetail:
        items: list[CostItemBreakdown] = []
        assumptions: list[str] = []

        # Determine scenario parameters
        if scenario_key == "basic":
            scope_mult = 0.85
            infra_tier = InfrastructureTier.STARTER
            cdn_choice = "cloudflare_free"
            monitoring_choice = "free_tier"
            storage_choice = "local"
            contingency_rate = 0.05
            include_legal = False
            desc = "Cenario enxuto (MVP): infraestrutura starter, monitoramento gratuito e escopo essencial."
        elif scenario_key == "high":
            scope_mult = 1.25
            infra_tier = InfrastructureTier.PRODUCTION
            cdn_choice = "cloudflare_pro"
            monitoring_choice = "datadog_pro"
            storage_choice = "s3_redundant"
            contingency_rate = max(0.15, input_spec.contingency_percentage * 1.5)
            include_legal = True
            desc = "Cenario robusto (Enterprise): infraestrutura redundante HA, monitoramento pro e suporte juridico."
        else:  # medium (default / recommended)
            scope_mult = 1.0
            infra_tier = input_spec.providers.hosting_tier
            cdn_choice = input_spec.providers.cdn_security
            monitoring_choice = input_spec.providers.monitoring
            storage_choice = input_spec.providers.storage_backup
            contingency_rate = input_spec.contingency_percentage
            include_legal = input_spec.license_brand.include_legal_assistance
            desc = (
                "Cenario equilibrado (Recomendado): infraestrutura balanceada com observabilidade e seguranca."
            )

        assumptions.append(f"Cenario: {desc}")
        assumptions.append(f"Taxa de cambio adotada: 1 USD = {rate:.2f} BRL.")

        # 1. Development Cost
        dev_cost, dev_items, dev_assumptions = self._compute_development_cost(
            input_spec, scope_mult, curr, rate
        )
        items.extend(dev_items)
        assumptions.extend(dev_assumptions)

        # 2. Publication / Setup Cost (one-time)
        pub_cost, pub_items, pub_assumptions = self._compute_publication_cost(
            input_spec, scenario_key, include_legal, curr, rate
        )
        items.extend(pub_items)
        assumptions.extend(pub_assumptions)

        # 3. Monthly Recurring Cost
        monthly_cost, m_items, m_assumptions = self._compute_monthly_cost(
            input_spec, infra_tier, cdn_choice, monitoring_choice, storage_choice, curr, rate
        )
        items.extend(m_items)
        assumptions.extend(m_assumptions)

        # 4. Annual Recurring Cost
        annual_cost, a_items, a_assumptions = self._compute_annual_cost(
            input_spec, monthly_cost, curr, rate
        )
        items.extend(a_items)
        assumptions.extend(a_assumptions)

        # 5. License & Brand Subtotals
        license_brand_initial = sum(
            it.amount for it in pub_items if it.category in ("trademark", "domain", "license")
        )
        license_brand_annual = sum(
            it.amount for it in a_items if it.category in ("trademark", "domain", "license")
        )

        # 6. Contingency and Totals
        base_year_one = dev_cost + pub_cost + annual_cost
        contingency_val = round(base_year_one * contingency_rate, 2)
        items.append(
            CostItemBreakdown(
                item_id=f"contingency_{scenario_key}",
                name=f"Reserva de Contingencia ({int(contingency_rate * 100)}%)",
                category="contingency",
                amount=contingency_val,
                currency=curr,
                billing_period="one_time",
                source="Planejamento de Risco e Gestao Financeira",
                notes=f"Provisao percentual de {contingency_rate * 100:.1f}% sobre os custos do primeiro ano.",
            )
        )
        assumptions.append(f"Reserva de contingencia de {contingency_rate * 100:.1f}% aplicada ao Ano 1.")

        year_one_total = round(base_year_one + contingency_val, 2)
        subsequent_annual = round(annual_cost, 2)

        return CostScenarioDetail(
            scenario=scenario_key,  # type: ignore[arg-type]
            description=desc,
            development_cost=round(dev_cost, 2),
            publication_cost=round(pub_cost, 2),
            monthly_recurring_cost=round(monthly_cost, 2),
            annual_recurring_cost=round(annual_cost, 2),
            license_and_brand_initial_cost=round(license_brand_initial, 2),
            license_and_brand_annual_cost=round(license_brand_annual, 2),
            contingency_cost=contingency_val,
            year_one_total=year_one_total,
            subsequent_years_annual_total=subsequent_annual,
            breakdown_items=items,
            assumptions=assumptions,
        )

    def _compute_development_cost(
        self,
        input_spec: ProductCostInput,
        scope_mult: float,
        curr: Currency,
        rate: float,
    ) -> tuple[float, list[CostItemBreakdown], list[str]]:
        items: list[CostItemBreakdown] = []
        assumptions: list[str] = []
        mode = input_spec.mode

        # Estimate base engineering hours
        if input_spec.team.total_hours is not None and input_spec.team.total_hours > 0:
            base_hours = input_spec.team.total_hours
        else:
            base_hours = self._estimate_hours_from_scope(input_spec.scope)

        adjusted_hours = round(base_hours * scope_mult, 1)

        # Average labor rate
        if input_spec.team.hourly_rate is not None and input_spec.team.hourly_rate > 0:
            effective_hourly_rate = input_spec.team.hourly_rate
        else:
            effective_hourly_rate = self._compute_weighted_hourly_rate(input_spec.team, curr, rate)

        # AI token costs
        ai_spec = input_spec.ai
        if ai_spec.control_plane_cost_usd is not None and ai_spec.control_plane_cost_usd > 0:
            real_usd = ai_spec.control_plane_cost_usd * scope_mult
            ai_cost = self.catalog.to_currency(amount_usd=real_usd, target_currency=curr, exchange_rate=rate)
            ai_source = "Control Plane (nexcoder_control CostTracker medicao real)"
        else:
            pricing = self.catalog.get_ai_tier_pricing(ai_spec.model_tier)
            inp_cost_usd = (ai_spec.estimated_tokens_input / 1_000_000.0) * pricing["input_per_million_usd"]
            out_cost_usd = (ai_spec.estimated_tokens_output / 1_000_000.0) * pricing["output_per_million_usd"]
            run_cost_usd = (inp_cost_usd + out_cost_usd) * max(1, ai_spec.estimated_runs) * scope_mult
            ai_cost = self.catalog.to_currency(amount_usd=run_cost_usd, target_currency=curr, exchange_rate=rate)
            ai_source = f"Modelo tier {ai_spec.model_tier} ({ai_spec.estimated_runs} execucoes projetadas)"

        if mode == DevelopmentMode.HUMAN_TEAM:
            total_dev = adjusted_hours * effective_hourly_rate
            items.append(
                CostItemBreakdown(
                    item_id="dev_human_hours",
                    name=f"Desenvolvimento por Equipe ({adjusted_hours:.0f}h a {effective_hourly_rate:.2f}/h)",
                    category="development",
                    amount=round(total_dev, 2),
                    currency=curr,
                    billing_period="one_time",
                    source="Benchmark salarial de mercado e composicao da equipe",
                    notes=f"Total de {adjusted_hours:.0f} horas alocadas entre perfis senior, pleno e QA.",
                )
            )
            assumptions.append(
                f"Desenvolvimento 100% humano estimado em {adjusted_hours:.0f}h "
                f"a {curr.value} {effective_hourly_rate:.2f}/hora."
            )

        elif mode == DevelopmentMode.AI_ONLY:
            # AI only mode: full agentic generation with minimal oversight validation
            oversight_hours = round(adjusted_hours * 0.10, 1)  # 10% human audit
            oversight_cost = oversight_hours * effective_hourly_rate
            total_dev = ai_cost + oversight_cost

            items.append(
                CostItemBreakdown(
                    item_id="dev_ai_tokens",
                    name=f"Execucao de Agentes e Consumo de Tokens ({ai_spec.model_tier})",
                    category="development",
                    amount=round(ai_cost, 2),
                    currency=curr,
                    billing_period="one_time",
                    source=ai_source,
                    notes=f"Tokens: {ai_spec.estimated_tokens_input:,} in / {ai_spec.estimated_tokens_output:,} out.",
                )
            )
            items.append(
                CostItemBreakdown(
                    item_id="dev_ai_oversight",
                    name=f"Supervisao e Validacao Humana de PRs ({oversight_hours:.0f}h)",
                    category="development",
                    amount=round(oversight_cost, 2),
                    currency=curr,
                    billing_period="one_time",
                    source="Auditoria tecnica de seguranca e conformidade",
                    notes="Acompanhamento humano de revisao e homologacao final.",
                )
            )
            assumptions.append(
                f"Modo So IA: agentes autonomos ({curr.value} {ai_cost:.2f}) com supervisao de {oversight_hours:.0f}h."
            )

        else:  # HYBRID (default)
            # Hybrid: AI generates 65%, human builds 35%
            human_hours = round(adjusted_hours * 0.35, 1)
            human_dev_cost = human_hours * effective_hourly_rate
            total_dev = human_dev_cost + ai_cost

            items.append(
                CostItemBreakdown(
                    item_id="dev_hybrid_human",
                    name=f"Engenharia Humana Guiada ({human_hours:.0f}h)",
                    category="development",
                    amount=round(human_dev_cost, 2),
                    currency=curr,
                    billing_period="one_time",
                    source="Benchmark salarial de mercado e equipe hibrida",
                    notes=f"Arquitetura, revisao e refinamento de requisitos ({human_hours:.0f}h).",
                )
            )
            items.append(
                CostItemBreakdown(
                    item_id="dev_hybrid_ai",
                    name=f"Aceleracao por Agentes de IA ({ai_spec.model_tier})",
                    category="development",
                    amount=round(ai_cost, 2),
                    currency=curr,
                    billing_period="one_time",
                    source=ai_source,
                    notes="Geracao de codigo, testes automatizados e sintese de documentacao.",
                )
            )
            assumptions.append(f"Modo Hibrido: {human_hours:.0f}h humanas combinadas com pipeline de IA.")

        return total_dev, items, assumptions

    def _compute_publication_cost(
        self,
        input_spec: ProductCostInput,
        scenario_key: str,
        include_legal: bool,
        curr: Currency,
        rate: float,
    ) -> tuple[float, list[CostItemBreakdown], list[str]]:
        items: list[CostItemBreakdown] = []
        assumptions: list[str] = []
        total_pub = 0.0

        # Domain initial registration
        domain_pricing = self.catalog.get_domain_pricing(input_spec.providers.domain_tld, curr, rate)
        dom_initial = domain_pricing["initial_cost"]
        total_pub += dom_initial
        items.append(
            CostItemBreakdown(
                item_id="pub_domain_initial",
                name=f"Registro Inicial de Dominio ({input_spec.providers.domain_tld})",
                category="domain",
                amount=round(dom_initial, 2),
                currency=curr,
                billing_period="one_time",
                source=domain_pricing["source"],
                notes=domain_pricing.get("notes", ""),
            )
        )
        assumptions.append(f"Dominio inicial registrado com base no provedor oficial: {domain_pricing['source']}.")

        # Initial DevOps Deploy / CI/CD Setup
        deploy_hours = 8.0 if scenario_key == "basic" else (16.0 if scenario_key == "medium" else 28.0)
        hourly_rate = self.catalog.get_labor_rate("devops_engineer", curr, rate)
        deploy_setup_cost = deploy_hours * hourly_rate
        total_pub += deploy_setup_cost
        items.append(
            CostItemBreakdown(
                item_id="pub_infra_setup",
                name=f"Configuracao Inicial de Infra e CI/CD ({deploy_hours:.0f}h DevOps)",
                category="publication",
                amount=round(deploy_setup_cost, 2),
                currency=curr,
                billing_period="one_time",
                source="Benchmark DevOps Engineer",
                notes="Provisionamento de servidores, pipelines GitHub Actions e configuracao de seguranca.",
            )
        )
        assumptions.append(f"Setup de infraestrutura e pipelines: {deploy_hours:.0f}h de especialista DevOps.")

        # SSL Certificates
        items.append(
            CostItemBreakdown(
                item_id="pub_ssl",
                name="Certificado SSL/TLS Automatizado",
                category="publication",
                amount=0.0,
                currency=curr,
                billing_period="one_time",
                source="Let's Encrypt / Cloudflare Universal SSL",
                notes="Renovacao automatica sem custos de licenciamento comercial.",
            )
        )

        # Trademark initial application
        tm_spec = input_spec.license_brand
        if tm_spec.trademark_jurisdiction != "none":
            tm_pricing = self.catalog.get_trademark_pricing(
                tm_spec.trademark_jurisdiction,
                tm_spec.trademark_classes_count,
                include_legal,
                curr,
                rate,
            )
            tm_initial = tm_pricing["initial_cost"]
            total_pub += tm_initial
            app_f = tm_pricing['application_fee']
            leg_f = tm_pricing['legal_fee']
            items.append(
                CostItemBreakdown(
                    item_id="pub_trademark_application",
                    name=f"Registro de Marca - Protocolo Inicial ({tm_spec.trademark_jurisdiction.upper()})",
                    category="trademark",
                    amount=round(tm_initial, 2),
                    currency=curr,
                    billing_period="one_time",
                    source=tm_pricing["source"],
                    notes=f"Taxa oficial ({app_f:.2f}) + Assessoria ({leg_f:.2f}).",
                )
            )
            assumptions.append(
                f"Protecao de marca sob a jurisdicao {tm_spec.trademark_jurisdiction.upper()}."
            )

        # Initial Software Licenses
        if tm_spec.software_license_initial_cost > 0:
            lic_init = tm_spec.software_license_initial_cost
            total_pub += lic_init
            items.append(
                CostItemBreakdown(
                    item_id="pub_software_license_initial",
                    name="Licencas Comerciais de Software (Setup Inicial)",
                    category="license",
                    amount=round(lic_init, 2),
                    currency=curr,
                    billing_period="one_time",
                    source="Licenciamento de terceiros informado pelo solicitante",
                    notes="Softwares comerciais, bibliotecas ou plugins com taxa de adesao.",
                )
            )

        return total_pub, items, assumptions

    def _compute_monthly_cost(
        self,
        input_spec: ProductCostInput,
        infra_tier: InfrastructureTier,
        cdn_choice: str,
        monitoring_choice: str,
        storage_choice: str,
        curr: Currency,
        rate: float,
    ) -> tuple[float, list[CostItemBreakdown], list[str]]:
        items: list[CostItemBreakdown] = []
        assumptions: list[str] = []
        total_monthly = 0.0

        # Hosting & Infrastructure
        infra = self.catalog.get_infra_pricing(
            input_spec.providers.hosting_target,
            infra_tier,
            curr,
            rate,
        )

        # Compute
        comp_cost = infra["compute_monthly"]
        total_monthly += comp_cost
        target_label = input_spec.providers.hosting_target.value.upper()
        tier_label = infra_tier.value.upper()
        items.append(
            CostItemBreakdown(
                item_id="rec_infra_compute",
                name=f"Hospedagem Compute ({target_label} - {tier_label})",
                category="hosting",
                amount=round(comp_cost, 2),
                currency=curr,
                billing_period="monthly",
                source=infra["source"],
                notes=f"Instancia de computacao dimensionada para {infra_tier.value}.",
            )
        )

        # Database
        db_cost = infra["database_monthly"]
        total_monthly += db_cost
        items.append(
            CostItemBreakdown(
                item_id="rec_infra_database",
                name=f"Banco de Dados ({input_spec.providers.hosting_target.value.upper()})",
                category="database",
                amount=round(db_cost, 2),
                currency=curr,
                billing_period="monthly",
                source=infra["source"],
                notes="Instancia ou volume persistente dedicado para banco relacional.",
            )
        )

        # Networking / Load Balancer
        net_cost = infra["networking_monthly"]
        total_monthly += net_cost
        items.append(
            CostItemBreakdown(
                item_id="rec_infra_networking",
                name=f"Rede e Roteamento ({input_spec.providers.hosting_target.value.upper()})",
                category="hosting",
                amount=round(net_cost, 2),
                currency=curr,
                billing_period="monthly",
                source=infra["source"],
                notes="Trafego de saida e balanceador de carga se aplicavel.",
            )
        )
        assumptions.append(f"Infraestrutura baseada no catalogo IaC: {infra['source']}.")

        # Email
        email = self.catalog.get_email_pricing(input_spec.providers.email_provider, curr, rate)
        email_cost = email["monthly_cost"]
        total_monthly += email_cost
        items.append(
            CostItemBreakdown(
                item_id="rec_email",
                name=f"Servico de E-mail ({input_spec.providers.email_provider})",
                category="email",
                amount=round(email_cost, 2),
                currency=curr,
                billing_period="monthly",
                source=email["source"],
                notes=email.get("notes", ""),
            )
        )

        # CDN & Security
        cdn = self.catalog.get_cdn_pricing(cdn_choice, curr, rate)
        cdn_cost = cdn["monthly_cost"]
        total_monthly += cdn_cost
        items.append(
            CostItemBreakdown(
                item_id="rec_cdn_security",
                name=f"CDN, DNS e Seguranca WAF ({cdn_choice})",
                category="cdn",
                amount=round(cdn_cost, 2),
                currency=curr,
                billing_period="monthly",
                source=cdn["source"],
                notes=cdn.get("notes", ""),
            )
        )

        # Storage & Backup
        storage = self.catalog.get_storage_pricing(storage_choice, curr, rate)
        storage_cost = storage["monthly_cost"]
        total_monthly += storage_cost
        items.append(
            CostItemBreakdown(
                item_id="rec_storage_backup",
                name=f"Armazenamento de Objetos e Backups ({storage_choice})",
                category="storage",
                amount=round(storage_cost, 2),
                currency=curr,
                billing_period="monthly",
                source=storage["source"],
                notes=storage.get("notes", ""),
            )
        )

        # Monitoring & APM
        monitoring = self.catalog.get_monitoring_pricing(monitoring_choice, curr, rate)
        mon_cost = monitoring["monthly_cost"]
        total_monthly += mon_cost
        items.append(
            CostItemBreakdown(
                item_id="rec_monitoring",
                name=f"Monitoramento, Logs e Observabilidade ({monitoring_choice})",
                category="monitoring",
                amount=round(mon_cost, 2),
                currency=curr,
                billing_period="monthly",
                source=monitoring["source"],
                notes=monitoring.get("notes", ""),
            )
        )

        # Monthly Commercial Licenses
        if input_spec.providers.commercial_licenses_monthly > 0:
            lic_m = input_spec.providers.commercial_licenses_monthly
            total_monthly += lic_m
            items.append(
                CostItemBreakdown(
                    item_id="rec_software_licenses_monthly",
                    name="Licencas Comerciais Recorrentes (Mensal)",
                    category="license",
                    amount=round(lic_m, 2),
                    currency=curr,
                    billing_period="monthly",
                    source="Licenciamento SaaS recorrente",
                    notes="Assinaturas de ferramentas de terceiros.",
                )
            )

        return total_monthly, items, assumptions

    def _compute_annual_cost(
        self,
        input_spec: ProductCostInput,
        monthly_cost: float,
        curr: Currency,
        rate: float,
    ) -> tuple[float, list[CostItemBreakdown], list[str]]:
        items: list[CostItemBreakdown] = []
        assumptions: list[str] = []

        # 12 months recurring baseline
        annual_from_monthly = round(monthly_cost * 12.0, 2)
        total_annual = annual_from_monthly

        items.append(
            CostItemBreakdown(
                item_id="rec_annual_subtotal_monthly",
                name="Custos Recorrentes Mensais Consolidados (12 meses)",
                category="hosting",
                amount=annual_from_monthly,
                currency=curr,
                billing_period="annual",
                source="Consolidacao de 12 mensalidades de infraestrutura e servicos",
                notes=f"Calculado como {monthly_cost:.2f} x 12 meses.",
            )
        )

        # Domain annual renewal
        domain_pricing = self.catalog.get_domain_pricing(input_spec.providers.domain_tld, curr, rate)
        dom_renewal = domain_pricing["annual_renewal"]
        total_annual += dom_renewal
        items.append(
            CostItemBreakdown(
                item_id="rec_annual_domain_renewal",
                name=f"Renovacao Anual de Dominio ({input_spec.providers.domain_tld})",
                category="domain",
                amount=round(dom_renewal, 2),
                currency=curr,
                billing_period="annual",
                source=domain_pricing["source"],
                notes="Renovacao periodica para manutencao da titularidade do dominio.",
            )
        )

        # Trademark annual provision (e.g. decennial fee amortized over 10 years)
        tm_spec = input_spec.license_brand
        if tm_spec.trademark_jurisdiction != "none":
            tm_pricing = self.catalog.get_trademark_pricing(
                tm_spec.trademark_jurisdiction,
                tm_spec.trademark_classes_count,
                False,
                curr,
                rate,
            )
            # Concession / renewal is paid every 10 years for INPI; amortized annual provision:
            annual_tm_provision = round(tm_pricing["concession_fee"] / 10.0, 2)
            if annual_tm_provision > 0:
                total_annual += annual_tm_provision
                items.append(
                    CostItemBreakdown(
                        item_id="rec_annual_trademark_provision",
                        name=f"Provisao Anual de Concessao de Marca ({tm_spec.trademark_jurisdiction.upper()})",
                        category="trademark",
                        amount=annual_tm_provision,
                        currency=curr,
                        billing_period="annual",
                        source=tm_pricing["source"],
                        notes="Amortizacao anual para a taxa decenal de concessao da marca.",
                    )
                )

        # Annual Software Licenses
        if tm_spec.software_license_annual_cost > 0:
            lic_annual = tm_spec.software_license_annual_cost
            total_annual += lic_annual
            items.append(
                CostItemBreakdown(
                    item_id="rec_annual_software_license",
                    name="Licencas Comerciais de Software (Renovacao Anual)",
                    category="license",
                    amount=round(lic_annual, 2),
                    currency=curr,
                    billing_period="annual",
                    source="Licenciamento anual de terceiros",
                    notes="Renovacao de licencas de ferramentas corporativas.",
                )
            )

        assumptions.append("Custo recorrente anual inclui 12 meses de servicos + renovacao de dominio e concessoes.")
        return total_annual, items, assumptions

    def _estimate_hours_from_scope(self, scope: CostScope) -> float:
        """Derive standard development hours from complexity, screens, and endpoints."""
        complexity_factors = {
            ScopeComplexity.LOW: 8.0,
            ScopeComplexity.MEDIUM: 16.0,
            ScopeComplexity.HIGH: 28.0,
            ScopeComplexity.ENTERPRISE: 44.0,
        }
        hours_per_feature = complexity_factors.get(scope.complexity, 16.0)
        feature_hours = scope.feature_count * hours_per_feature
        screen_hours = scope.estimated_screens * 6.0
        endpoint_hours = scope.estimated_endpoints * 4.0
        arch_overhead = 20.0 if scope.architecture_style == "microservices" else 10.0

        return feature_hours + screen_hours + endpoint_hours + arch_overhead

    def _compute_weighted_hourly_rate(self, team: TeamSpec, curr: Currency, rate: float) -> float:
        """Calculate the blended team hourly rate based on role allocation."""
        if team.role_rates:
            total_weight = sum(team.roles.values()) or 1
            weighted_sum = sum(team.role_rates.get(role, 160.0) * count for role, count in team.roles.items())
            return weighted_sum / float(total_weight)

        rates: list[float] = []
        weights: list[int] = []
        for role, count in team.roles.items():
            if count <= 0:
                continue
            role_rate = self.catalog.get_labor_rate(role, curr, rate)
            rates.append(role_rate)
            weights.append(count)

        if not rates:
            return self.catalog.get_labor_rate("average_developer", curr, rate)

        weighted_avg = sum(r * w for r, w in zip(rates, weights, strict=False)) / float(sum(weights))
        return round(weighted_avg, 2)
