"""Command-line interface for faccoder-control plane."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from faccoder_control.approval.machines import MachineApprovalManager
from faccoder_control.approval.tokens import ApprovalTokenManager
from faccoder_control.keys.models import APIKeyCreate
from faccoder_control.keys.store import APIKeyService
from faccoder_control.metering.audit import AppendOnlyAuditLog
from faccoder_control.metering.budgets import BudgetManager
from faccoder_control.metering.cost_tracker import CostTracker
from faccoder_control.metering.mcp_middleware import MCPToolMeter
from faccoder_control.web.panel import build_overview

app = typer.Typer(
    name="faccoder-control",
    help="Control plane management CLI for faccoder.",
    no_args_is_help=True,
)
keys_app = typer.Typer(name="keys", help="Manage API keys, USD caps, and scopes.")
machines_app = typer.Typer(name="machines", help="Govern and approve CLI workstations.")
audit_app = typer.Typer(name="audit", help="Query and verify append-only audit ledger.")

app.add_typer(keys_app)
app.add_typer(machines_app)
app.add_typer(audit_app)

console = Console()

# Singleton state for CLI runs
_key_service = APIKeyService()
_cost_tracker = CostTracker()
_tool_meter = MCPToolMeter()
_budget_mgr = BudgetManager(_cost_tracker)
_machine_mgr = MachineApprovalManager()
_audit_log = AppendOnlyAuditLog()
_token_mgr = ApprovalTokenManager()


@app.command("status")
def status() -> None:
    """Display overall control plane operational status."""
    overview = build_overview(
        _key_service,
        _cost_tracker,
        _tool_meter,
        _budget_mgr,
        _machine_mgr,
        _audit_log,
    )
    table = Table(title="faccoder Control Plane Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Spend (USD)", f"${overview.total_spend_usd:.2f}")
    table.add_row("Active API Keys", str(overview.active_keys_count))
    table.add_row("Tool Invocations", str(overview.total_invocations))
    table.add_row("Pending CLI Machines", str(overview.pending_machines_count))
    table.add_row("Active Budget Alerts", str(overview.active_alerts_count))

    console.print(table)


@keys_app.command("create")
def keys_create(
    name: str = typer.Argument(..., help="Descriptive name for the API key"),
    owner: str = typer.Option("admin", help="Owner identity or team"),
    usd_cap: float | None = typer.Option(None, help="Maximum USD cumulative spend cap"),
    rpm: int | None = typer.Option(None, help="Requests per minute rate limit"),
    scopes: str = typer.Option("tools:execute,metrics:read", help="Comma-separated scopes"),
) -> None:
    """Create a new API key with scopes and optional spending/rate limits."""
    scope_list = [s.strip() for s in scopes.split(",") if s.strip()]
    spec = APIKeyCreate(
        name=name,
        owner=owner,
        usd_cap=usd_cap,
        rate_limit_rpm=rpm,
        scopes=scope_list,
    )
    result = _key_service.create_key(spec)
    _audit_log.record_event(
        event_type="key.created",
        actor=owner,
        action="create",
        resource=result.key_id,
        severity="info",
        details={"name": name, "usd_cap": usd_cap, "rpm": rpm},
    )

    console.print("[bold green]API Key Created Successfully[/bold green]")
    console.print(f"Key ID: [cyan]{result.key_id}[/cyan]")
    console.print(f"Prefix: [cyan]{result.prefix}[/cyan]")
    console.print(f"Scopes: [cyan]{', '.join(result.scopes)}[/cyan]")
    console.print(f"USD Cap: [cyan]${result.usd_cap if result.usd_cap else 'Unlimited'}[/cyan]")
    console.print(
        f"[bold yellow]Secret Key (save now, not shown again):[/bold yellow] [bold white]{result.raw_key}[/bold white]"
    )


@keys_app.command("list")
def keys_list() -> None:
    """List all configured API keys."""
    keys = _key_service.list_keys()
    table = Table(title="Configured API Keys")
    table.add_column("Key ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Owner", style="magenta")
    table.add_column("USD Cap", style="yellow")
    table.add_column("Spent (USD)", style="green")
    table.add_column("Active", style="blue")

    for k in keys:
        cap_str = f"${k.usd_cap:.2f}" if k.usd_cap is not None else "None"
        table.add_row(
            k.key_id,
            k.name,
            k.owner,
            cap_str,
            f"${k.current_spend_usd:.4f}",
            str(k.is_active and not k.is_expired()),
        )

    console.print(table)


@machines_app.command("list")
def machines_list() -> None:
    """List registered CLI workstations."""
    machines = _machine_mgr.list_machines()
    table = Table(title="CLI Workstations")
    table.add_column("Machine ID", style="cyan")
    table.add_column("Hostname", style="white")
    table.add_column("Platform", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Registered By", style="yellow")

    for m in machines:
        table.add_row(m.machine_id, m.hostname, m.platform, m.status, m.registered_by)

    console.print(table)


@machines_app.command("approve")
def machines_approve(
    machine_id: str = typer.Argument(..., help="Machine ID to approve"),
    approver: str = typer.Option("admin", help="Admin approving the machine"),
) -> None:
    """Approve a pending CLI workstation."""
    try:
        m = _machine_mgr.approve_machine(machine_id, approver=approver)
        _audit_log.record_event(
            event_type="machine.approved",
            actor=approver,
            action="approve",
            resource=machine_id,
            severity="info",
        )
        console.print(f"[green]Machine '{m.machine_id}' approved for execution access.[/green]")
    except KeyError:
        console.print(f"[red]Machine '{machine_id}' not found.[/red]")
        raise typer.Exit(code=1) from None


@audit_app.command("verify")
def audit_verify() -> None:
    """Cryptographically verify the integrity of the append-only audit log."""
    is_valid, message = _audit_log.verify_integrity()
    if is_valid:
        console.print(f"[bold green]Ledger Verified:[/bold green] {message}")
    else:
        console.print(f"[bold red]INTEGRITY BREACH:[/bold red] {message}")
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
