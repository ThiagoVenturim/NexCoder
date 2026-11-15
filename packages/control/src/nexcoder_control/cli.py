"""Command-line interface for nexcoder-control plane."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from nexcoder_control.approval.machines import MachineApprovalManager
from nexcoder_control.approval.tokens import ApprovalTokenManager
from nexcoder_control.email import EmailAttachment, EmailMessage, EmailService
from nexcoder_control.keys.models import APIKeyCreate
from nexcoder_control.keys.store import APIKeyService
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_control.metering.budgets import BudgetManager
from nexcoder_control.metering.cost_tracker import CostTracker
from nexcoder_control.metering.mcp_middleware import MCPToolMeter
from nexcoder_control.web.panel import build_overview

app = typer.Typer(
    name="nexcoder-control",
    help="Control plane management CLI for nexcoder.",
    no_args_is_help=True,
)
keys_app = typer.Typer(name="keys", help="Manage API keys, USD caps, and scopes.")
machines_app = typer.Typer(name="machines", help="Govern and approve CLI workstations.")
audit_app = typer.Typer(name="audit", help="Query and verify append-only audit ledger.")
email_app = typer.Typer(name="email", help="Manage email connectors, send messages, and view templates.")

app.add_typer(keys_app)
app.add_typer(machines_app)
app.add_typer(audit_app)
app.add_typer(email_app)

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
    table = Table(title="nexcoder Control Plane Status")
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


_email_service = EmailService(
    audit_log=_audit_log,
    token_manager=_token_mgr,
)


@email_app.command("status")
def email_status() -> None:
    """Display configured email providers and policy settings."""
    configured_providers = _email_service.get_available_providers()
    pref = _email_service.settings.get_preferred_provider()

    table = Table(title="Email Dispatcher Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Operational", "Yes" if _email_service.is_configured() else "No (unconfigured)")
    table.add_row("Configured Providers", ", ".join(configured_providers) if configured_providers else "None")
    table.add_row("Preferred Provider", pref)
    table.add_row("Require Approval", str(_email_service.settings.require_human_approval))
    table.add_row("Max Recipients", str(_email_service.settings.max_recipients_per_send))
    table.add_row("Gmail RPM Limit", str(_email_service.settings.rate_limits_rpm.get("gmail", 60)))
    table.add_row("Outlook RPM Limit", str(_email_service.settings.rate_limits_rpm.get("outlook", 30)))
    table.add_row("SMTP RPM Limit", str(_email_service.settings.rate_limits_rpm.get("smtp", 30)))

    console.print(table)


@email_app.command("templates")
def email_templates() -> None:
    """List available reusable email templates."""
    templates = _email_service.template_manager.list_templates()
    table = Table(title="Reusable Email Templates")
    table.add_column("Template Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Subject Pattern", style="yellow")

    for tpl in templates:
        table.add_row(tpl.name, tpl.description, tpl.subject_template)

    console.print(table)


@email_app.command("send")
def email_send(
    to: str = typer.Option(..., "--to", "-t", help="Recipient email address"),
    subject: str = typer.Option("Notification", "--subject", "-s", help="Email subject"),
    body: str | None = typer.Option(None, "--body", "-b", help="Plain text message body"),
    html: str | None = typer.Option(None, "--html", help="HTML message body"),
    attachment: str | None = typer.Option(None, "--attachment", "-a", help="Path to attachment file"),
    template: str | None = typer.Option(None, "--template", help="Name of template to render"),
    provider: str | None = typer.Option(None, "--provider", "-p", help="Provider (gmail, outlook, smtp)"),
    token: str | None = typer.Option(None, "--token", help="Human approval token"),
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Confirm send without approval token"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate send without actual network dispatch"),
) -> None:
    """Send an email from user account with human approval and audit tracking."""
    attachments = []
    if attachment:
        attachments.append(EmailAttachment(filename=attachment, file_path=attachment))

    msg = EmailMessage(
        subject=subject,
        recipients=[to],
        body_text=body,
        body_html=html,
        attachments=attachments,
        template_name=template,
    )

    try:
        res = _email_service.send_email(
            message=msg,
            provider=provider,
            approval_token=token,
            confirmed=confirm,
            dry_run=dry_run,
        )
        if res.success:
            console.print(
                f"[green]Email dispatched successfully via {res.provider} (ID: {res.message_id}). "
                f"Audit ID: {res.audit_event_id}[/green]"
            )
        else:
            console.print(f"[yellow]Email not sent (status: {res.status}): {res.error_message}[/yellow]")
    except Exception as exc:
        console.print(f"[red]Email delivery failed: {exc}[/red]")
        raise typer.Exit(code=1) from None


@email_app.command("test")
def email_test(
    to: str = typer.Option(..., "--to", "-t", help="Recipient for test message"),
    provider: str = typer.Option("gmail", "--provider", "-p", help="Provider to test (gmail, outlook, smtp)"),
) -> None:
    """Dispatch automated test email with an attachment."""
    try:
        res = _email_service.send_test_email(recipient=to, provider=provider, confirmed=True)
        if res.success:
            console.print(f"[green]Test email sent via {res.provider} (ID: {res.message_id})[/green]")
        else:
            console.print(f"[yellow]Test email failed (status: {res.status}): {res.error_message}[/yellow]")
    except Exception as exc:
        console.print(f"[red]Test failed: {exc}[/red]")
        raise typer.Exit(code=1) from None


def main() -> None:
    app()


if __name__ == "__main__":
    main()
