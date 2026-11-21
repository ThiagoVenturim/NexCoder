"""Comprehensive unit tests for product cost calculation, pricing catalog, scenarios, and integrations."""

from __future__ import annotations

from nexcoder_control.metering.cost_tracker import CostTracker
from nexcoder_iac.models import ArchitectureTier, IaCTarget
from nexcoder_interfaces.cli.main import app as cli_app
from nexcoder_interfaces.tools.planning import estimate_product_cost
from nexcoder_planning.cost import (
    AISpec,
    CommercialProposalGenerator,
    CostScope,
    Currency,
    DevelopmentMode,
    InfrastructureTarget,
    InfrastructureTier,
    LicenseBrandSpec,
    PricingCatalog,
    ProductCostCalculator,
    ProductCostInput,
    ProviderSpec,
    ScopeComplexity,
    TeamSpec,
    extract_ai_spec_from_tracker,
)
from typer.testing import CliRunner


def test_pricing_catalog_loading_and_conversion() -> None:
    """Validate YAML pricing catalog loading, entries, and currency conversion."""
    catalog = PricingCatalog()

    assert "infrastructure" in catalog.categories
    assert "domains" in catalog.categories
    assert "trademark" in catalog.categories
    assert "email" in catalog.categories

    # Currency conversion checks
    usd_to_brl = catalog.to_currency(amount_usd=10.0, target_currency=Currency.BRL, exchange_rate=5.50)
    assert usd_to_brl == 55.0

    brl_to_usd = catalog.to_currency(amount_brl=55.0, target_currency=Currency.USD, exchange_rate=5.50)
    assert brl_to_usd == 10.0

    # Domain pricing
    dom_br = catalog.get_domain_pricing("com_br", Currency.BRL, 5.50)
    assert dom_br["initial_cost"] == 40.0
    assert dom_br["annual_renewal"] == 40.0
    assert "Registro.br" in dom_br["source"]

    dom_com = catalog.get_domain_pricing("com", Currency.USD, 5.50)
    assert dom_com["initial_cost"] == 14.0

    # Trademark INPI pricing
    tm_br = catalog.get_trademark_pricing("inpi_br", 1, True, Currency.BRL, 5.50)
    assert tm_br["application_fee"] == 142.0
    assert tm_br["concession_fee"] == 298.0
    assert tm_br["legal_fee"] == 600.0
    assert tm_br["initial_cost"] == 742.0
    assert "INPI" in tm_br["source"]


def test_calculator_scenarios_and_exact_sums() -> None:
    """Validate mathematical exactness of sums across basic, medium, and high scenarios."""
    scope = CostScope(
        project_name="Plataforma SaaS de Gestao",
        complexity=ScopeComplexity.MEDIUM,
        feature_count=12,
        estimated_screens=6,
        estimated_endpoints=15,
        stack="python_fastapi_react",
        architecture_style="modular_monolith",
    )
    providers = ProviderSpec(
        hosting_target=InfrastructureTarget.HETZNER,
        hosting_tier=InfrastructureTier.STANDARD,
        domain_tld="com_br",
        email_provider="google_workspace",
        cdn_security="cloudflare_free",
        storage_backup="s3_standard",
        monitoring="standard_cloud",
        commercial_licenses_monthly=50.0,
    )
    license_brand = LicenseBrandSpec(
        trademark_jurisdiction="inpi_br",
        trademark_classes_count=1,
        include_legal_assistance=True,
        software_license_initial_cost=200.0,
        software_license_annual_cost=300.0,
    )
    cost_input = ProductCostInput(
        scope=scope,
        mode=DevelopmentMode.HYBRID,
        team=TeamSpec(roles={"senior": 1, "mid": 1, "qa_engineer": 1}),
        ai=AISpec(estimated_tokens_input=600_000, estimated_tokens_output=200_000, model_tier="medium"),
        providers=providers,
        license_brand=license_brand,
        currency=Currency.BRL,
        exchange_rate_usd_to_brl=5.50,
        contingency_percentage=0.10,
    )

    calculator = ProductCostCalculator()
    report = calculator.calculate(cost_input)

    assert report.project_name == "Plataforma SaaS de Gestao"
    assert report.currency == Currency.BRL
    assert "basic" in report.scenarios
    assert "medium" in report.scenarios
    assert "high" in report.scenarios

    # Validate each scenario's arithmetic
    for key, sc in report.scenarios.items():
        # Monthly items sum check
        monthly_items_sum = sum(
            it.amount for it in sc.breakdown_items if it.billing_period == "monthly"
        )
        assert round(monthly_items_sum, 2) == round(sc.monthly_recurring_cost, 2)

        # Year One Total check: dev + pub + annual + contingency
        calculated_year_one = round(
            sc.development_cost + sc.publication_cost + sc.annual_recurring_cost + sc.contingency_cost, 2
        )
        assert round(sc.year_one_total, 2) == calculated_year_one

        # Subsequent years: annual recurring
        assert round(sc.subsequent_years_annual_total, 2) == round(sc.annual_recurring_cost, 2)

        # Assumptions exist and are non-empty
        assert len(sc.assumptions) >= 4
        assert len(sc.breakdown_items) >= 10

    # Scenario progression check (basic < medium < high)
    basic = report.scenarios["basic"]
    medium = report.scenarios["medium"]
    high = report.scenarios["high"]

    assert basic.development_cost < medium.development_cost < high.development_cost
    assert basic.monthly_recurring_cost < medium.monthly_recurring_cost < high.monthly_recurring_cost
    assert basic.year_one_total < medium.year_one_total < high.year_one_total

    # Summary table renders properly
    table = report.summary_table()
    assert "| Item / Metrica | Basico (BRL) | Medio (BRL) | Alto (BRL) |" in table
    assert "Total Ano 1" in table


def test_delivery_modes_comparison() -> None:
    """Compare cost variance between human team, pure AI, and hybrid modes."""
    scope = CostScope(project_name="API Microservice", complexity=ScopeComplexity.LOW, feature_count=5)
    calculator = ProductCostCalculator()

    # 1. Human Team
    in_human = ProductCostInput(
        scope=scope,
        mode=DevelopmentMode.HUMAN_TEAM,
        team=TeamSpec(total_hours=80.0, hourly_rate=150.0),
        currency=Currency.BRL,
    )
    rep_human = calculator.calculate(in_human)
    human_dev = rep_human.scenarios["medium"].development_cost
    assert human_dev == 12_000.0  # 80h * 150 BRL/h

    # 2. AI Only
    in_ai = ProductCostInput(
        scope=scope,
        mode=DevelopmentMode.AI_ONLY,
        ai=AISpec(
            estimated_tokens_input=1_000_000,
            estimated_tokens_output=300_000,
            model_tier="medium",
            estimated_runs=10,
        ),
        currency=Currency.BRL,
    )
    rep_ai = calculator.calculate(in_ai)
    ai_dev = rep_ai.scenarios["medium"].development_cost
    assert ai_dev < human_dev  # AI execution is vastly lower cost

    # 3. Hybrid
    in_hybrid = ProductCostInput(
        scope=scope,
        mode=DevelopmentMode.HYBRID,
        currency=Currency.BRL,
    )
    rep_hybrid = calculator.calculate(in_hybrid)
    hybrid_dev = rep_hybrid.scenarios["medium"].development_cost
    assert ai_dev < hybrid_dev < human_dev


def test_control_plane_cost_tracker_integration() -> None:
    """Validate seamless integration with nexcoder_control CostTracker metering."""
    tracker = CostTracker()
    tracker.record_usage(
        model="claude-sonnet-5-5",
        input_tokens=150_000,
        output_tokens=40_000,
        app_id="nexcoder_product",
        pipeline_id="delivery_pipeline",
    )
    tracker.record_usage(
        model="gpt-4.1-mini",
        input_tokens=300_000,
        output_tokens=80_000,
        app_id="nexcoder_product",
        pipeline_id="delivery_pipeline",
    )

    ai_spec = extract_ai_spec_from_tracker(tracker, app_id="nexcoder_product")
    assert ai_spec.estimated_tokens_input == 450_000
    assert ai_spec.estimated_tokens_output == 120_000
    assert ai_spec.control_plane_cost_usd is not None
    assert ai_spec.control_plane_cost_usd > 0.0
    assert ai_spec.control_plane_metadata["app_id"] == "nexcoder_product"

    scope = CostScope(project_name="Control Plane Metered App")
    cost_input = ProductCostInput(
        scope=scope,
        mode=DevelopmentMode.AI_ONLY,
        ai=ai_spec,
        currency=Currency.USD,
    )
    calculator = ProductCostCalculator()
    report = calculator.calculate(cost_input)

    assert report.control_plane_integration["real_cost_usd"] == ai_spec.control_plane_cost_usd
    assert "Control Plane (nexcoder_control CostTracker medicao real)" in [
        it.source for it in report.scenarios["medium"].breakdown_items
    ]


def test_iac_target_reuse_and_pricing() -> None:
    """Validate mapping with IaCTarget and ArchitectureTier from nexcoder_iac."""
    calculator = ProductCostCalculator()

    for target in [IaCTarget.HETZNER, IaCTarget.DIGITALOCEAN, IaCTarget.AWS, IaCTarget.GCP, IaCTarget.VM]:
        cost_input = ProductCostInput(
            scope=CostScope(project_name="IaC Test"),
            providers=ProviderSpec(
                hosting_target=InfrastructureTarget(target.value),
                hosting_tier=InfrastructureTier(ArchitectureTier.STANDARD.value),
            ),
            currency=Currency.USD,
            exchange_rate_usd_to_brl=1.0,
        )
        report = calculator.calculate(cost_input)
        monthly = report.scenarios["medium"].monthly_recurring_cost
        assert monthly > 0.0


def test_currency_switching_usd_brl() -> None:
    """Validate conversion rates between USD and BRL."""
    calculator = ProductCostCalculator()
    scope = CostScope(project_name="Bilingual Pricing")

    in_brl = ProductCostInput(scope=scope, currency=Currency.BRL, exchange_rate_usd_to_brl=6.0)
    rep_brl = calculator.calculate(in_brl)

    in_usd = ProductCostInput(scope=scope, currency=Currency.USD, exchange_rate_usd_to_brl=6.0)
    rep_usd = calculator.calculate(in_usd)

    brl_domain = rep_brl.scenarios["medium"].publication_cost
    usd_domain = rep_usd.scenarios["medium"].publication_cost
    assert brl_domain > usd_domain


def test_commercial_proposal_markdown_generation() -> None:
    """Validate commercial proposal text, sections, and verify zero emojis."""
    scope = CostScope(project_name="Portal Corporativo B2B", feature_count=8)
    cost_input = ProductCostInput(
        scope=scope,
        currency=Currency.BRL,
    )
    calculator = ProductCostCalculator()
    report = calculator.calculate(cost_input)

    proposal = CommercialProposalGenerator.generate(
        report=report,
        client_name="Acme Corp",
        prepared_by="NexCoder Sales Engineering",
        validity_days=15,
    )

    assert "# Proposta Comercial e Orcamento Tecnico: Portal Corporativo B2B" in proposal
    assert "Acme Corp" in proposal
    assert "1. Sumario Executivo" in proposal
    assert "2. Comparativo de Cenarios" in proposal
    assert "3. Detalhamento do Cenario Recomendado" in proposal
    assert "4. Sugestao de Cronograma de Desembolso" in proposal
    assert "5. Premissas Tecnicas e Fontes Transparentes" in proposal
    assert "**Validade da Proposta**: 15 dias" in proposal

    # Strictly assert zero emojis in proposal
    for ch in proposal:
        assert ord(ch) < 0x1F300 or ord(ch) > 0x1FAD6, f"Emoji character detected: {ch}"


def test_interfaces_tool_and_cli_execution() -> None:
    """Validate execution via nexcoder_interfaces tool handler and CLI command."""
    # 1. Tool execution
    res = estimate_product_cost(
        project_name="App Mobile & Web",
        complexity="high",
        feature_count=15,
        mode="hybrid",
        infra_target="aws",
        infra_tier="standard",
        currency="BRL",
        include_proposal=True,
        client_name="Tech Holding",
    )
    assert res["status"] == "success"
    assert res["project_name"] == "App Mobile & Web"
    assert "commercial_proposal" in res
    assert "scenarios" in res
    assert res["scenarios"]["medium"]["year_one_total"] > 0

    # 2. CLI execution
    runner = CliRunner()
    cli_result = runner.invoke(
        cli_app,
        [
            "cost",
            "--project", "Test App CLI",
            "--complexity", "medium",
            "--features", "8",
            "--currency", "BRL",
        ],
    )
    assert cli_result.exit_code == 0
    assert "Estimativa de Custo de Produto: Test App CLI" in cli_result.output
    assert "Total Ano 1" in cli_result.output
