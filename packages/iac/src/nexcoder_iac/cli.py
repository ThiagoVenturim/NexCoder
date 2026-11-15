"""Command-line interface for nexcoder-iac infrastructure engine."""

from __future__ import annotations

from pathlib import Path

import typer

from nexcoder_iac.catalog import ArchitectureCatalog
from nexcoder_iac.engine import IaCEngine
from nexcoder_iac.models import ArchitectureTier, IaCTarget, IaCTool
from nexcoder_iac.pricing import estimate_monthly_cost

app = typer.Typer(
    name="nexcoder-iac",
    help="Infrastructure as Code generator, reference catalog, and deployment planner.",
    no_args_is_help=True,
)
catalog_app = typer.Typer(help="Reference architecture catalog commands.")
app.add_typer(catalog_app, name="catalog")


@catalog_app.command("list")
def list_architectures() -> None:
    """List all available reference architectures."""
    archs = ArchitectureCatalog.list_architectures()
    typer.echo("Available Reference Architectures:")
    typer.echo("-" * 60)
    for a in archs:
        typer.echo(f"  {a['id']:<18} | {a['title']}")
        typer.echo(f"  {'':<18}   {a['description']}")
    typer.echo("-" * 60)


@catalog_app.command("show")
def show_architecture(name: str) -> None:
    """Show details and specification of a reference architecture."""
    try:
        spec = ArchitectureCatalog.get(name)
        cost = estimate_monthly_cost(spec)
        typer.echo(f"Architecture: {spec.name}")
        typer.echo(f"Description:  {spec.description}")
        typer.echo(f"Tier:         {spec.tier.value}")
        typer.echo(f"Default Target: {spec.target.value}")
        typer.echo(f"Estimated Cost: ${cost:.2f}/month")
        typer.echo(f"Services:     {', '.join(s.name for s in spec.services)}")
        if spec.database:
            typer.echo(f"Database:     {spec.database.engine.value} v{spec.database.version}")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command("generate")
def generate_iac(
    description: str = typer.Option(..., "--desc", "-d", help="High-level description of desired infrastructure"),
    target: str = typer.Option("local_compose", "--target", "-t", help="Deployment target platform"),
    tool: str | None = typer.Option(None, "--tool", help="IaC tool: terraform, opentofu, ansible, compose"),
    tier: str = typer.Option("standard", "--tier", help="Sizing tier: starter, standard, production"),
    out_dir: Path | None = typer.Option(None, "--out-dir", "-o", help="Directory to save generated IaC files"),
) -> None:
    """Generate IaC templates from a natural language or structured description."""
    engine = IaCEngine()
    try:
        iac_target = IaCTarget(target.lower())
    except ValueError as e:
        valid_targets = ", ".join(t.value for t in IaCTarget)
        typer.echo(f"Invalid target '{target}'. Valid targets: {valid_targets}", err=True)
        raise typer.Exit(code=1) from e

    iac_tool = IaCTool(tool.lower()) if tool else None

    artifacts = engine.generate(
        spec=description,
        target=iac_target,
        tool=iac_tool,
    )

    typer.echo(f"Generated IaC for {artifacts.spec.name} ({artifacts.target.value}) via {artifacts.tool.value}")
    typer.echo(f"Estimated Monthly Cost: ${artifacts.estimated_monthly_cost_usd:.2f} USD")
    typer.echo(f"Generated {len(artifacts.files)} file(s):")

    for f in artifacts.files:
        typer.echo(f"  - {f.filename:<20} ({f.file_type})")
        if out_dir:
            out_path = Path(out_dir) / f.filename
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(f.content, encoding="utf-8")

    if out_dir:
        typer.echo(f"Files written to {out_dir}")


@app.command("estimate")
def estimate_cost(
    arch: str = typer.Option("simple_app", "--arch", "-a", help="Reference architecture name"),
    target: str = typer.Option("aws", "--target", "-t", help="Target cloud provider or VM"),
    tier: str = typer.Option("standard", "--tier", help="Sizing tier: starter, standard, production"),
) -> None:
    """Estimate monthly infrastructure costs for an architecture and target."""
    try:
        iac_target = IaCTarget(target.lower())
        iac_tier = ArchitectureTier(tier.lower())
        spec = ArchitectureCatalog.get(arch, target=iac_target, tier=iac_tier)
        cost = estimate_monthly_cost(spec)
        typer.echo(f"Target:       {iac_target.value}")
        typer.echo(f"Architecture: {spec.name} ({spec.tier.value})")
        typer.echo(f"Estimated:    ${cost:.2f} USD/month")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


def main() -> None:
    app()


if __name__ == "__main__":
    main()
