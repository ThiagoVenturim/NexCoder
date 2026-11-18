from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from nexcoder_interfaces.testing.models import (
    AgentCard,
    CanvasConnection,
    CanvasNote,
    CanvasPosition,
    NexHubCanvasPayload,
    SecurityTestRunRecord,
)


def format_markdown_summary(record: SecurityTestRunRecord) -> str:
    """Format full test report as Markdown for NexHub canvas note card."""
    target_name = Path(record.target_path).name or record.target_path
    lines: list[str] = [
        f"# Test Report: {target_name}",
        "",
        f"- **Status**: {record.status.upper()}",
        f"- **Target**: `{record.target_path}`",
        f"- **Authorized By**: `{record.authorized_by}`",
        f"- **Suites**: {', '.join(record.config.test_types)}",
        f"- **Agents**: {len(record.agents)}",
        (
            f"- **Budget Spent**: ${record.budget_spent:.2f} / "
            f"${record.config.budget_limit:.2f} {record.config.budget_currency}"
        ),
        f"- **Total Findings**: {record.total_findings}",
        f"- **Gate Verdict**: {'PASSED' if record.passed_gate else 'BLOCKED'}",
        "",
        "## Agent Execution Summary",
        "| Agent | Role | Assigned Types | State | Findings |",
        "|---|---|---|---|---|",
    ]
    for agent in record.agents:
        types_str = ", ".join(agent.assigned_types)
        lines.append(
            f"| `{agent.id}` | {agent.role} | {types_str} | {agent.state.upper()} | {agent.findings_count} |"
        )

    lines.append("")
    lines.append("## Findings Overview")
    if not record.findings:
        lines.append("No defects or vulnerabilities detected across executed test suites.")
    else:
        lines.append("| Type | Severity | Finding | Location |")
        lines.append("|---|---|---|---|")
        for f in record.findings[:20]:
            loc = f"`{f.location}`" if f.location else "-"
            lines.append(f"| {f.test_type} | {f.severity.upper()} | {f.title} | {loc} |")

    return "\n".join(lines)


def format_remediation_note(record: SecurityTestRunRecord) -> str:
    """Format actionable remediation guidance as Markdown for NexHub note card."""
    target_name = Path(record.target_path).name or record.target_path
    lines: list[str] = [
        f"# Remediations & Action Items: {target_name}",
        "",
        "Below are recommended fixes and repro steps for identified issues.",
        "",
    ]
    if not record.findings:
        lines.append("All automated quality and security checks passed cleanly.")
        return "\n".join(lines)

    for i, finding in enumerate(record.findings, start=1):
        lines.append(f"### {i}. [{finding.severity.upper()}] {finding.title}")
        lines.append(f"- **Category**: `{finding.test_type}`")
        if finding.location:
            lines.append(f"- **Location**: `{finding.location}`")
        if finding.description:
            lines.append(f"- **Description**: {finding.description}")
        if finding.reproducer:
            lines.append(f"- **Reproducer**: `{finding.reproducer}`")
        if finding.remediation:
            lines.append(f"- **Remediation**: {finding.remediation}")
        lines.append("")

    return "\n".join(lines)


def build_nexhub_canvas_payload(
    record: SecurityTestRunRecord,
    orchestrator_logs: Sequence[str] | None = None,
) -> NexHubCanvasPayload:
    """Build infinite canvas layout with agent terminal cards, notes, and connections."""
    target_name = Path(record.target_path).name or record.target_path
    cards: list[AgentCard] = []
    connections: list[CanvasConnection] = []

    # 1. Orchestrator Terminal Card (top-left)
    orch_card_id = f"card-orchestrator-{record.run_id}"
    orch_card = AgentCard(
        id=orch_card_id,
        title="Test Run Orchestrator",
        role="Control Orchestrator",
        agent_type="orchestrator",
        assigned_types=list(record.config.test_types),
        state="completed" if record.status in ("completed", "failed") else "running",
        position=CanvasPosition(x=100, y=100),
        width=520,
        height=320,
        logs=list(orchestrator_logs or []),
        findings_count=record.total_findings,
        metrics={
            "run_id": record.run_id,
            "progress": record.progress_percent,
            "budget_spent": record.budget_spent,
        },
    )
    cards.append(orch_card)

    # 2. Worker Agent Cards (arranged below orchestrator)
    base_y = 480
    card_width = 460
    gap_x = 40
    for idx, agent in enumerate(record.agents):
        card_x = 100 + idx * (card_width + gap_x)
        agent.position = CanvasPosition(x=card_x, y=base_y)
        cards.append(agent)
        # Connection from Orchestrator to Agent
        connections.append(
            CanvasConnection(
                from_id=orch_card_id,
                to_id=agent.id,
                label=f"dispatched: {', '.join(agent.assigned_types)}",
            )
        )

    # 3. Canvas Notes (arranged on the right side)
    notes_x = 100 + max(len(record.agents), 1) * (card_width + gap_x) + 40
    notes: list[CanvasNote] = []

    summary_note_id = f"note-report-{record.run_id}"
    summary_body = format_markdown_summary(record)
    notes.append(
        CanvasNote(
            id=summary_note_id,
            title=f"Quality & Security Test Report: {target_name}",
            body=summary_body,
            category="report",
            position=CanvasPosition(x=notes_x, y=100),
            width=580,
            height=420,
        )
    )

    remediation_note_id = f"note-remediations-{record.run_id}"
    remediation_body = format_remediation_note(record)
    notes.append(
        CanvasNote(
            id=remediation_note_id,
            title=f"Remediations & Action Items: {target_name}",
            body=remediation_body,
            category="action_items",
            position=CanvasPosition(x=notes_x, y=560),
            width=580,
            height=360,
        )
    )

    # Connect all worker agents to the summary report note
    for agent in record.agents:
        connections.append(
            CanvasConnection(
                from_id=agent.id,
                to_id=summary_note_id,
                label="results",
            )
        )

    # Connect summary note to remediation note
    connections.append(
        CanvasConnection(
            from_id=summary_note_id,
            to_id=remediation_note_id,
            label="action_items",
        )
    )

    return NexHubCanvasPayload(
        cards=cards,
        notes=notes,
        connections=connections,
    )
