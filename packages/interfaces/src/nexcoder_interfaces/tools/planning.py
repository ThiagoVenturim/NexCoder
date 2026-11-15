from __future__ import annotations

from typing import Any


def plan_sprints(
    prd_text: str,
    sprint_name: str = "Sprint 1",
    reserve_percentage: float = 0.20,
    team: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Parse a PRD into epics, stories, and tasks, then schedule into sprints with capacity calculation."""
    try:
        from nexcoder_planning.capacity import (
            CapacityCalculator,
            SprintCapacityConfig,
            TeamMember,
        )
        from nexcoder_planning.prd import PRDConverter
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Planning package not available: {exc}",
        }

    converter = PRDConverter()
    plan = converter.parse_markdown(prd_text)

    team_members: list[TeamMember] = []
    if team:
        for member_dict in team:
            team_members.append(TeamMember(**member_dict))
    else:
        team_members = [
            TeamMember(name="Lead Engineer", daily_hours=8.0, working_days=10),
            TeamMember(name="Fullstack Developer", daily_hours=8.0, working_days=10),
        ]

    config = SprintCapacityConfig(
        sprint_name=sprint_name,
        team=team_members,
        reserve_percentage=reserve_percentage,
    )

    all_tasks = plan.all_tasks()
    calculator = CapacityCalculator()
    sprint_result = calculator.plan_sprint(all_tasks, config)

    return {
        "status": "success",
        "title": plan.title,
        "epics_count": len(plan.epics),
        "stories_count": len(plan.all_stories()),
        "tasks_count": len(all_tasks),
        "scheduled_tasks": [t.model_dump() for t in sprint_result.scheduled_tasks],
        "overflow_tasks": [t.model_dump() for t in sprint_result.overflow_tasks],
        "capacity_report": {
            "sprint_name": sprint_result.capacity_report.sprint_name,
            "gross_hours": sprint_result.capacity_report.gross_hours,
            "reserve_hours": sprint_result.capacity_report.reserve_hours,
            "net_available_hours": sprint_result.capacity_report.net_available_hours,
            "effective_capacity_hours": sprint_result.capacity_report.effective_capacity_hours,
            "planned_hours": sprint_result.capacity_report.planned_hours,
            "is_over_capacity": sprint_result.capacity_report.is_over_capacity,
            "overflow_hours": sprint_result.capacity_report.overflow_hours,
        },
    }


def sync_board(
    platform: str = "github",
    repo: str = "local/repo",
    dry_run: bool = True,
    prd_text: str | None = None,
) -> dict[str, Any]:
    """Synchronize planned tasks with a Git platform issue tracker / Kanban board."""
    try:
        from nexcoder_planning.adapters.azure_devops import AzureDevOpsAdapter
        from nexcoder_planning.adapters.github import GitHubAdapter
        from nexcoder_planning.adapters.gitlab import GitLabAdapter
        from nexcoder_planning.models import Plan
        from nexcoder_planning.prd import PRDConverter
        from nexcoder_planning.sync import BoardSynchronizer
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Planning package not available: {exc}",
        }

    platform_lower = platform.lower()
    if "gitlab" in platform_lower:
        adapter = GitLabAdapter(repo=repo, dry_run=dry_run)
    elif "azure" in platform_lower or "ado" in platform_lower:
        adapter = AzureDevOpsAdapter(repo=repo, dry_run=dry_run)
    else:
        adapter = GitHubAdapter(repo=repo, dry_run=dry_run)

    if prd_text:
        plan = PRDConverter().parse_markdown(prd_text)
    else:
        plan = Plan(title="Backlog Sync Plan", epics=[])

    synchronizer = BoardSynchronizer(adapter=adapter)
    summary = synchronizer.sync_board_and_sprint(
        plan=plan,
        dry_run=dry_run,
    )

    return {
        "status": "success",
        "platform": platform,
        "repo": repo,
        "dry_run": dry_run,
        "total_tasks": summary.total_tasks,
        "moved_count": summary.moved_count,
        "has_slippage": summary.replan_result is not None and summary.replan_result.alert is not None,
    }


def productivity_report(
    project: str = "nexcoder-platform",
    team: str = "core-engineering",
    period: str = "2026-Q4",
    platforms: list[str] | None = None,
    transport: str = "offline",
    nexdash_url: str = "http://127.0.0.1:8080",
    output_html_path: str | None = None,
) -> dict[str, Any]:
    """Pull dev productivity metrics (GitHub, Azure DevOps, Redmine) and build a NexDash dashboard."""
    try:
        from pathlib import Path

        from nexcoder_core.reports import NexDashValidationError
        from nexcoder_planning.reports import generate_productivity_dashboard
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Planning or reporting module not available: {exc}",
        }

    try:
        metrics, bundle = generate_productivity_dashboard(
            project=project,
            team=team,
            period=period,
            platforms=platforms,
            transport=transport,  # type: ignore[arg-type]
            nexdash_url=nexdash_url,
        )
    except NexDashValidationError as exc:
        return {
            "status": "error",
            "message": str(exc),
        }

    if output_html_path:
        out_path = Path(output_html_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(bundle.html, encoding="utf-8")

    return {
        "status": "success",
        "model_id": bundle.model_id,
        "transport": bundle.transport,
        "dashboard_id": bundle.dashboard_id,
        "title": bundle.title,
        "subtitle": bundle.subtitle,
        "metrics": metrics.model_dump(),
        "kpis": [k.model_dump() for k in bundle.kpis],
        "charts": [c.model_dump() for c in bundle.charts],
        "csp_header": bundle.csp_header,
        "html": bundle.html,
    }


def estimate_product_cost(
    project_name: str,
    complexity: str = "medium",
    feature_count: int = 10,
    estimated_screens: int = 5,
    estimated_endpoints: int = 12,
    mode: str = "hybrid",
    infra_target: str = "hetzner",
    infra_tier: str = "standard",
    domain_tld: str = "com_br",
    trademark_jurisdiction: str = "inpi_br",
    currency: str = "BRL",
    exchange_rate: float = 5.50,
    include_proposal: bool = False,
    client_name: str = "Cliente",
) -> dict[str, Any]:
    """Estimate full product life-cycle costs (build, publish, maintain, license, and brand)."""
    try:
        from nexcoder_planning.cost import (
            AISpec,
            CommercialProposalGenerator,
            CostScope,
            Currency,
            DevelopmentMode,
            InfrastructureTarget,
            InfrastructureTier,
            LicenseBrandSpec,
            ProductCostCalculator,
            ProductCostInput,
            ProviderSpec,
            ScopeComplexity,
            TeamSpec,
        )
    except ImportError as exc:
        return {
            "status": "error",
            "message": f"Cost calculation module not available: {exc}",
        }

    scope = CostScope(
        project_name=project_name,
        complexity=ScopeComplexity(complexity),
        feature_count=feature_count,
        estimated_screens=estimated_screens,
        estimated_endpoints=estimated_endpoints,
    )
    providers = ProviderSpec(
        hosting_target=InfrastructureTarget(infra_target),
        hosting_tier=InfrastructureTier(infra_tier),
        domain_tld=domain_tld,
    )
    license_brand = LicenseBrandSpec(
        trademark_jurisdiction=trademark_jurisdiction,
    )
    cost_input = ProductCostInput(
        scope=scope,
        mode=DevelopmentMode(mode),
        team=TeamSpec(),
        ai=AISpec(),
        providers=providers,
        license_brand=license_brand,
        currency=Currency(currency),
        exchange_rate_usd_to_brl=exchange_rate,
    )

    calculator = ProductCostCalculator()
    report = calculator.calculate(cost_input)

    resp: dict[str, Any] = {
        "status": "success",
        "project_name": report.project_name,
        "currency": report.currency.value,
        "exchange_rate_usd_to_brl": report.exchange_rate_usd_to_brl,
        "development_mode": report.development_mode.value,
        "recommended_scenario": report.recommended_scenario,
        "scenarios": {k: v.model_dump() for k, v in report.scenarios.items()},
        "pricing_sources": report.pricing_sources,
        "summary_table": report.summary_table(),
    }

    if include_proposal:
        resp["commercial_proposal"] = CommercialProposalGenerator.generate(
            report=report,
            client_name=client_name,
        )

    return resp

