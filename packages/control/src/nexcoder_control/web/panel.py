"""Control plane status, metrics data model, and self-contained HTML panel."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from nexcoder_control.approval.machines import MachineApprovalManager
from nexcoder_control.keys.store import APIKeyService
from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_control.metering.budgets import BudgetManager
from nexcoder_control.metering.cost_tracker import CostTracker
from nexcoder_control.metering.mcp_middleware import MCPToolMeter


class TopToolStat(BaseModel):
    tool_name: str
    invocations: int
    error_rate_pct: float
    avg_latency_ms: float
    total_cost_usd: float


class ControlPlaneOverview(BaseModel):
    """Aggregated status and metrics view for the control plane dashboard."""

    active_keys_count: int = 0
    total_spend_usd: float = 0.0
    total_invocations: int = 0
    total_errors: int = 0
    pending_machines_count: int = 0
    active_alerts_count: int = 0
    top_tools: list[TopToolStat] = Field(default_factory=list)
    spend_by_app: dict[str, float] = Field(default_factory=dict)
    spend_by_agent: dict[str, float] = Field(default_factory=dict)
    recent_audit: list[dict[str, Any]] = Field(default_factory=list)


def build_overview(
    key_service: APIKeyService,
    cost_tracker: CostTracker,
    tool_meter: MCPToolMeter,
    budget_mgr: BudgetManager,
    machine_mgr: MachineApprovalManager,
    audit_log: AppendOnlyAuditLog,
) -> ControlPlaneOverview:
    """Build unified control plane summary from subsystems."""
    keys = key_service.list_keys()
    active_keys = sum(1 for k in keys if k.is_active and not k.is_expired())

    spend_usd = cost_tracker.total_spend()
    app_summary = cost_tracker.aggregate_by("app")
    agent_summary = cost_tracker.aggregate_by("agent")

    tools_metrics = tool_meter.get_tool_metrics()
    total_inv = sum(m.invocations for m in tools_metrics)
    total_err = sum(m.errors for m in tools_metrics)

    sorted_tools = sorted(tools_metrics, key=lambda m: m.invocations, reverse=True)[:5]
    top_tool_stats = [
        TopToolStat(
            tool_name=m.tool_name,
            invocations=m.invocations,
            error_rate_pct=round(m.error_rate * 100, 2),
            avg_latency_ms=round(m.avg_duration_ms, 2),
            total_cost_usd=round(m.total_cost_usd, 4),
        )
        for m in sorted_tools
    ]

    pending_machines = len(machine_mgr.list_machines(status="pending"))
    alerts = budget_mgr.get_alerts()

    audit_events = audit_log.query(limit=10)
    audit_rows = [
        {
            "sequence_no": e.sequence_no,
            "timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "event_type": e.event_type,
            "actor": e.actor,
            "severity": e.severity,
            "resource": e.resource,
        }
        for e in audit_events
    ]

    return ControlPlaneOverview(
        active_keys_count=active_keys,
        total_spend_usd=round(spend_usd, 4),
        total_invocations=total_inv,
        total_errors=total_err,
        pending_machines_count=pending_machines,
        active_alerts_count=len(alerts),
        top_tools=top_tool_stats,
        spend_by_app={k: round(v.total_cost_usd, 4) for k, v in app_summary.items()},
        spend_by_agent={k: round(v.total_cost_usd, 4) for k, v in agent_summary.items()},
        recent_audit=audit_rows,
    )


def render_html_panel(overview: ControlPlaneOverview) -> str:
    """Render self-contained, zero-external-dependency, zero-emoji HTML dashboard."""
    tool_rows = (
        "".join(
            f"""
        <tr>
            <td><code>{t.tool_name}</code></td>
            <td>{t.invocations}</td>
            <td>{t.error_rate_pct}%</td>
            <td>{t.avg_latency_ms} ms</td>
            <td>${t.total_cost_usd:.4f}</td>
        </tr>
        """
            for t in overview.top_tools
        )
        or "<tr><td colspan='5' class='empty'>No tools invoked yet</td></tr>"
    )

    audit_rows = (
        "".join(
            f"""
        <tr>
            <td>#{e["sequence_no"]}</td>
            <td>{e["timestamp"]}</td>
            <td><span class='badge badge-{e["severity"]}'>{e["event_type"]}</span></td>
            <td>{e["actor"]}</td>
            <td>{e["resource"]}</td>
        </tr>
        """
            for e in overview.recent_audit
        )
        or "<tr><td colspan='5' class='empty'>Audit log empty</td></tr>"
    )

    app_rows = (
        "".join(f"<li><strong>{app}:</strong> ${cost:.4f}</li>" for app, cost in overview.spend_by_app.items())
        or "<li class='empty'>No app spend recorded</li>"
    )

    agent_rows = (
        "".join(f"<li><strong>{agent}:</strong> ${cost:.4f}</li>" for agent, cost in overview.spend_by_agent.items())
        or "<li class='empty'>No agent spend recorded</li>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>nexcoder Control Plane</title>
    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-hover: #334155;
            --border: #475569;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #38bdf8;
            --accent: #818cf8;
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f87171;
            --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--bg);
            color: var(--text);
            font-family: var(--font-family);
            line-height: 1.5;
            padding: 24px;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        h1 {{ font-size: 1.5rem; font-weight: 700; color: var(--primary); letter-spacing: -0.025em; }}
        .subtitle {{ font-size: 0.875rem; color: var(--text-muted); }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
        }}
        .card-title {{ font-size: 0.75rem; text-transform: uppercase; color: var(--text-muted); font-weight: 600; }}
        .card-value {{ font-size: 1.75rem; font-weight: 700; color: var(--text); margin-top: 4px; }}
        .section-title {{ font-size: 1.125rem; font-weight: 600; margin-bottom: 12px; color: var(--text); }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
            text-align: left;
        }}
        th {{
            background: var(--surface);
            color: var(--text-muted);
            padding: 10px 12px;
            border-bottom: 1px solid var(--border);
            font-weight: 600;
        }}
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid var(--border);
        }}
        tr:hover td {{ background: var(--surface-hover); }}
        code {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            background: #0f172a;
            padding: 2px 6px;
            border-radius: 4px;
            color: var(--primary);
        }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .badge-info {{ background: #0284c7; color: #fff; }}
        .badge-warning {{ background: #d97706; color: #fff; }}
        .badge-error {{ background: #dc2626; color: #fff; }}
        .badge-critical {{ background: #7f1d1d; color: #fca5a5; }}
        .split-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 24px;
        }}
        ul.list {{ list-style: none; }}
        ul.list li {{
            padding: 8px 12px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            font-size: 0.875rem;
        }}
        .empty {{ text-align: center; color: var(--text-muted); font-style: italic; }}
    </style>
</head>
<body>
    <header>
        <div>
            <h1>nexcoder Control Plane</h1>
            <div class="subtitle">Operational security, access keys, metering, and budgets</div>
        </div>
        <div>
            <span class="badge badge-info">Status: Nominal</span>
        </div>
    </header>

    <div class="grid">
        <div class="card">
            <div class="card-title">Total Spend</div>
            <div class="card-value">${overview.total_spend_usd:.2f}</div>
        </div>
        <div class="card">
            <div class="card-title">Active API Keys</div>
            <div class="card-value">{overview.active_keys_count}</div>
        </div>
        <div class="card">
            <div class="card-title">Tool Invocations</div>
            <div class="card-value">{overview.total_invocations}</div>
        </div>
        <div class="card">
            <div class="card-title">Pending Machines</div>
            <div class="card-value">{overview.pending_machines_count}</div>
        </div>
        <div class="card">
            <div class="card-title">Budget Alerts</div>
            <div class="card-value">{overview.active_alerts_count}</div>
        </div>
    </div>

    <div class="card" style="margin-bottom: 24px;">
        <div class="section-title">Top Tools Activity</div>
        <table>
            <thead>
                <tr>
                    <th>Tool Name</th>
                    <th>Invocations</th>
                    <th>Error Rate</th>
                    <th>Avg Latency</th>
                    <th>Total Cost</th>
                </tr>
            </thead>
            <tbody>
                {tool_rows}
            </tbody>
        </table>
    </div>

    <div class="split-grid">
        <div class="card">
            <div class="section-title">Spend by Application</div>
            <ul class="list">
                {app_rows}
            </ul>
        </div>
        <div class="card">
            <div class="section-title">Spend by Agent</div>
            <ul class="list">
                {agent_rows}
            </ul>
        </div>
    </div>

    <div class="card">
        <div class="section-title">Audit Ledger (Latest Events)</div>
        <table>
            <thead>
                <tr>
                    <th>Seq</th>
                    <th>Timestamp</th>
                    <th>Event Type</th>
                    <th>Actor</th>
                    <th>Resource</th>
                </tr>
            </thead>
            <tbody>
                {audit_rows}
            </tbody>
        </table>
    </div>
</body>
</html>
"""
