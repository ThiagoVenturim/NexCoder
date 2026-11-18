from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from nexcoder_interfaces.mcp.server import MCPServer
from nexcoder_interfaces.plugin.claude import export_claude_plugin, write_mcp_json
from nexcoder_interfaces.tools.agents import run_agent, run_pipeline
from nexcoder_interfaces.tools.code import generate_docs, search_code
from nexcoder_interfaces.tools.email import send_email
from nexcoder_interfaces.tools.ideation import judge_idea, research_idea
from nexcoder_interfaces.tools.planning import estimate_product_cost, plan_sprints, productivity_report
from nexcoder_interfaces.tools.security import (
    export_security_test_report,
    get_security_test_campaign,
    run_security_test_campaign,
    security_report,
)
from nexcoder_interfaces.tools.unavailable import capture_page, generate_tests

app = typer.Typer(
    name="nexcoder",
    help="Unified CLI for the nexcoder platform.",
    no_args_is_help=True,
)

export_app = typer.Typer(
    name="export",
    help="Export Claude Code plugin configs, agents, and skills.",
    no_args_is_help=True,
)
app.add_typer(export_app, name="export")

report_app = typer.Typer(
    name="report",
    help="Generate developer productivity and security posture dashboards via NexDash.",
    no_args_is_help=True,
)
app.add_typer(report_app, name="report")

email_app = typer.Typer(
    name="email",
    help="Dispatch emails and reports via Gmail, Outlook, or SMTP with human confirmation.",
    no_args_is_help=True,
)
app.add_typer(email_app, name="email")

campaign_app = typer.Typer(
    name="campaign",
    help="Multi-agent security and quality testing campaigns with authorization and budget controls (Issue #71).",
    no_args_is_help=True,
)
app.add_typer(campaign_app, name="campaign")


vcs_app = typer.Typer(
    name="vcs",
    help="VCS and repository management operations (Azure DevOps, GitLab, Git, SVN, TortoiseGit).",
    no_args_is_help=True,
)
app.add_typer(vcs_app, name="vcs")


@app.command(name="init")
def cmd_init(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Target project directory."),
    preset: str = typer.Option("hybrid", "--preset", help="Configuration preset (offline, hybrid, all-paid)."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing configuration file."),
) -> None:
    """Initialize a new nexcoder project with nexcoder.yaml configuration."""
    target_dir = path.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    config_file = target_dir / "nexcoder.yaml"

    if config_file.exists() and not force:
        print(f"Configuration file already exists at {config_file}. Use --force to overwrite.")
        return

    content = f"""# nexcoder project configuration
preset: {preset}
tiers:
  small: {{provider: local, model: mock}}
  medium: {{provider: local, model: mock}}
  large: {{provider: local, model: mock}}
embeddings:
  provider: sentence-transformers
  model: BAAI/bge-m3
langfuse:
  enabled: false
budget:
  max_usd_per_run: 5.0
  max_delegation_depth: 2
"""
    config_file.write_text(content, encoding="utf-8")
    print(f"Successfully initialized nexcoder project at {config_file}")


@app.command(name="idea")
def cmd_idea(
    idea_text: str = typer.Argument(..., help="Idea title or problem statement."),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Offline dry-run mode."),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Domain tags, comma-separated."),
) -> None:
    """Research a software idea with the specialist squad."""
    tags = [t.strip() for t in domain.split(",")] if domain else None
    result = research_idea(idea=idea_text, dry_run=dry_run, domain_tags=tags)
    print(json.dumps(result, indent=2))


@app.command(name="judge")
def cmd_judge(
    idea_text: str = typer.Argument(..., help="Idea title or summary to deliberate."),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Offline dry-run mode."),
) -> None:
    """Deliberate on an idea through the 6-member jury committee."""
    result = judge_idea(idea=idea_text, dry_run=dry_run)
    print(json.dumps(result, indent=2))


@app.command(name="plan")
def cmd_plan(
    prd_path_or_text: str = typer.Argument(..., help="Path to markdown PRD file or raw text."),
    sprint_name: str = typer.Option("Sprint 1", "--sprint", help="Sprint name."),
    reserve: float = typer.Option(0.20, "--reserve", help="Reserve buffer percentage."),
) -> None:
    """Decompose a PRD into epics, stories, and tasks, then plan sprint capacity."""
    candidate = Path(prd_path_or_text)
    if candidate.is_file():
        text = candidate.read_text(encoding="utf-8")
    else:
        text = prd_path_or_text

    result = plan_sprints(prd_text=text, sprint_name=sprint_name, reserve_percentage=reserve)
    print(json.dumps(result, indent=2))


@app.command(name="index")
def cmd_index(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Directory path to index."),
    query: str = typer.Option("*", "--query", "-q", help="Optional search query to verify index."),
) -> None:
    """Index symbols and search code in target path."""
    result = search_code(query=query, path=str(path), limit=10)
    print(json.dumps(result, indent=2))


@app.command(name="docs")
def cmd_docs(
    path: Path = typer.Option(Path("."), "--path", "-p", help="Directory path to document."),
    level: str = typer.Option("module", "--level", "-l", help="Doc hierarchy level (routine, class, module, system)."),
) -> None:
    """Synthesize bottom-up documentation from source code symbols."""
    result = generate_docs(path=str(path), level=level)
    print(json.dumps(result, indent=2))


@app.command(name="capture")
def cmd_capture(
    url_or_spec: str = typer.Argument(..., help="URL or target spec for capture."),
    generate_test: bool = typer.Option(False, "--tests", help="Generate tests from capture."),
) -> None:
    """Capture page DOM and generate automated test suite (nexcoder-capture)."""
    if generate_test:
        result = generate_tests(page_or_spec=url_or_spec)
    else:
        result = capture_page(url=url_or_spec)
    print(json.dumps(result, indent=2))


@app.command(name="run")
def cmd_run(
    name: str = typer.Argument(..., help="Agent slug or pipeline name to execute."),
    task: str = typer.Option("Execute default task", "--task", "-t", help="Task description."),
    is_pipeline: bool = typer.Option(False, "--pipeline", help="Treat target name as a pipeline rather than agent."),
) -> None:
    """Execute an agent or pipeline by name."""
    if is_pipeline:
        result = run_pipeline(pipeline_name=name, inputs={"task": task})
    else:
        result = run_agent(agent_name=name, task=task)
    print(json.dumps(result, indent=2))


@export_app.command(name="mcp")
def cmd_export_mcp(
    output_dir: Path = typer.Option(Path("."), "--out", "-o", help="Output directory for .mcp.json."),
    transport: str = typer.Option("stdio", "--transport", help="Transport mode (stdio or sse)."),
) -> None:
    """Generate .mcp.json file for Claude Code."""
    out_file = write_mcp_json(output_dir=output_dir, transport=transport)
    print(f"Wrote MCP configuration to {out_file}")


@export_app.command(name="claude")
def cmd_export_claude(
    output_dir: Path = typer.Option(Path(".claude"), "--out", "-o", help="Output directory."),
    transport: str = typer.Option("stdio", "--transport", help="Transport mode for .mcp.json."),
    zip_pkg: bool = typer.Option(False, "--zip", help="Bundle export into a zip file."),
) -> None:
    """Export complete Claude Code workspace package (.mcp.json, agents, skills)."""
    result = export_claude_plugin(output_dir=output_dir, transport=transport, zip_output=zip_pkg)
    print(json.dumps(result, indent=2))


@report_app.command(name="productivity")
def cmd_report_productivity(
    project: str = typer.Option("nexcoder-platform", "--project", "-p", help="Target project name."),
    team: str = typer.Option("core-engineering", "--team", "-t", help="Team identifier."),
    period: str = typer.Option("2026-Q4", "--period", help="Reporting period."),
    platforms: str = typer.Option("github,azure_devops,redmine", "--platforms", help="Comma-separated platforms."),
    transport: str = typer.Option("offline", "--transport", help="NexDash transport (offline, mcp, rest)."),
    out_html: Path | None = typer.Option(None, "--out", "-o", help="Optional path to save rendered HTML dashboard."),
) -> None:
    """Generate a developer productivity dashboard via NexDash."""
    plat_list = [p.strip() for p in platforms.split(",") if p.strip()]
    result = productivity_report(
        project=project,
        team=team,
        period=period,
        platforms=plat_list,
        transport=transport,
        output_html_path=str(out_html) if out_html else None,
    )
    print(json.dumps(result, indent=2))


@app.command(name="cost")
def cmd_cost(
    project: str = typer.Option("Novo Produto", "--project", "-p", help="Project name to estimate."),
    complexity: str = typer.Option("medium", "--complexity", "-c", help="Complexity (low, medium, high, enterprise)."),
    features: int = typer.Option(10, "--features", "-f", help="Estimated number of features."),
    mode: str = typer.Option("hybrid", "--mode", "-m", help="Delivery mode: human_team, hybrid, or ai_only."),
    infra: str = typer.Option("hetzner", "--infra", help="Infra target (hetzner, aws, digitalocean, vm, gcp)."),
    tier: str = typer.Option("standard", "--tier", help="Infra tier (starter, standard, production)."),
    domain: str = typer.Option("com_br", "--domain", help="Domain TLD (com_br, com, io, ai)."),
    currency: str = typer.Option("BRL", "--currency", help="Valuation currency (BRL or USD)."),
    proposal: bool = typer.Option(False, "--proposal", help="Generate client commercial proposal markdown."),
    client: str = typer.Option("Cliente", "--client", help="Client name for commercial proposal."),
    as_json: bool = typer.Option(False, "--json", help="Output raw JSON instead of formatted markdown table."),
    out_file: Path | None = typer.Option(None, "--out", "-o", help="Optional file path to write results."),
) -> None:
    """Calculate comprehensive product lifecycle costs (build, publish, maintain mes/ano, licenca e marca)."""
    result = estimate_product_cost(
        project_name=project,
        complexity=complexity,
        feature_count=features,
        mode=mode,
        infra_target=infra,
        infra_tier=tier,
        domain_tld=domain,
        currency=currency,
        include_proposal=proposal,
        client_name=client,
    )

    if as_json:
        output_text = json.dumps(result, indent=2)
    elif proposal and "commercial_proposal" in result:
        output_text = result["commercial_proposal"]
    else:
        rec_sc = result.get("recommended_scenario", "medium")
        output_text = (
            f"# Estimativa de Custo de Produto: {project}\n\n"
            f"**Modo**: {mode} | **Moeda**: {currency} | **Cenario Recomendado**: {rec_sc}\n\n"
            f"{result.get('summary_table', '')}\n\n"
            f"Fontes de Preco:\n" + "\n".join(f"- {s}" for s in result.get("pricing_sources", []))
        )

    if out_file:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(output_text, encoding="utf-8")
        print(f"Cost estimate written to {out_file}")
    else:
        print(output_text)


@report_app.command(name="security")
def cmd_report_security(
    project: str = typer.Option("nexcoder-platform", "--project", "-p", help="Target project name."),
    period: str = typer.Option("2026-Q4", "--period", help="Reporting period."),
    policy: str = typer.Option("default", "--policy", help="Gate policy preset (default or strict)."),
    transport: str = typer.Option("offline", "--transport", help="NexDash transport (offline, mcp, rest)."),
    out_html: Path | None = typer.Option(None, "--out", "-o", help="Optional path to save rendered HTML dashboard."),
) -> None:
    """Generate a security posture and gate coverage dashboard via NexDash."""
    result = security_report(
        project=project,
        period=period,
        policy=policy,
        transport=transport,
        output_html_path=str(out_html) if out_html else None,
    )
    print(json.dumps(result, indent=2))


@email_app.command(name="send")
def cmd_email_send(
    to: str = typer.Option(..., "--to", "-t", help="Recipient email address."),
    subject: str = typer.Option("Notification", "--subject", "-s", help="Email subject line."),
    body: str | None = typer.Option(None, "--body", "-b", help="Plain text message body."),
    html: str | None = typer.Option(None, "--html", help="HTML message body."),
    attachment: str | None = typer.Option(None, "--attachment", "-a", help="Path to file attachment."),
    template: str | None = typer.Option(None, "--template", help="Reusable template name."),
    provider: str | None = typer.Option(None, "--provider", "-p", help="Provider (gmail, outlook, smtp)."),
    token: str | None = typer.Option(None, "--token", help="Human approval token."),
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Explicit human confirmation."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Dry run simulation mode."),
) -> None:
    """Send an email from user account with human approval and audit logging."""
    att_list = None
    if attachment:
        att_list = [{"filename": Path(attachment).name, "file_path": attachment}]

    res = send_email(
        recipients=[to],
        subject=subject,
        body_text=body,
        body_html=html,
        attachments=att_list,
        template_name=template,
        provider=provider,
        approval_token=token,
        confirmed=confirm,
        dry_run=dry_run,
    )
    print(json.dumps(res, indent=2))


@email_app.command(name="test")
def cmd_email_test(
    to: str = typer.Option(..., "--to", "-t", help="Recipient email address."),
    provider: str = typer.Option("gmail", "--provider", "-p", help="Provider to test (gmail, outlook, smtp)."),
) -> None:
    """Send an automated test email with an attachment."""
    from nexcoder_control.email import EmailService

    service = EmailService()
    res = service.send_test_email(recipient=to, provider=provider, confirmed=True)
    print(json.dumps(res.model_dump(), indent=2, default=str))


@email_app.command(name="templates")
def cmd_email_templates() -> None:
    """List available reusable email templates."""
    from nexcoder_control.email import EmailTemplateManager

    mgr = EmailTemplateManager()
    templates = [
        {
            "name": t.name,
            "description": t.description,
            "subject": t.subject_template,
        }
        for t in mgr.list_templates()
    ]
    print(json.dumps(templates, indent=2))


@app.command(name="serve")
def cmd_serve(
    transport: str = typer.Option("stdio", "--transport", help="Transport mode: stdio or sse."),
    host: str = typer.Option("127.0.0.1", "--host", help="Server host when running SSE or REST API."),
    port: int = typer.Option(8000, "--port", help="Server port when running SSE or REST API."),
    api: bool = typer.Option(False, "--api", help="Serve full REST API in addition to MCP SSE."),
    insecure_local: bool = typer.Option(
        False, "--insecure-local", help="Allow unauthenticated requests on 127.0.0.1 only."
    ),
    cors_origins: str | None = typer.Option(
        None, "--cors-origins", help="Comma-separated allowed CORS origins (never * with credentials)."
    ),
    api_key: str | None = typer.Option(None, "--api-key", help="API key required for authenticating requests."),
) -> None:
    """Start MCP server (stdio or SSE) or REST API."""
    if transport == "stdio":
        server = MCPServer()
        server.process_stdio_sync(sys.stdin, sys.stdout)
    else:
        if insecure_local and host not in ("127.0.0.1", "localhost", "::1"):
            typer.echo("Error: --insecure-local is only permitted on 127.0.0.1 / localhost", err=True)
            raise typer.Exit(code=1)

        origins = [o.strip() for o in cors_origins.split(",") if o.strip()] if cors_origins else None

        import uvicorn

        from nexcoder_interfaces.api.app import create_app

        fastapi_app = create_app(
            api_key=api_key,
            insecure_local=insecure_local,
            host=host,
            cors_origins=origins,
        )
        uvicorn.run(fastapi_app, host=host, port=port)


@campaign_app.command(name="run")
def cmd_campaign_run(
    target: Path = typer.Option(Path("."), "--target", "-t", help="Target repository or app directory."),
    test_types: str = typer.Option(
        "unit,system,process,dom,api,security",
        "--test-types",
        help="Comma-separated test types (unit, system, process, dom, api, security).",
    ),
    agents: int = typer.Option(3, "--agents", "-a", help="Number of parallel testing agents."),
    budget_cost: float = typer.Option(5.0, "--budget-cost", help="Maximum budget in USD."),
    budget_time: float = typer.Option(120.0, "--budget-time", help="Execution timeout in seconds."),
    owned_target: bool = typer.Option(False, "--owned-target", help="Confirm target is owned by operator."),
    authorized_by: str = typer.Option("owner", "--authorized-by", help="Operator or approver identity."),
    auth_doc: Path | None = typer.Option(None, "--auth-doc", help="Path to signed authorization YAML/JSON."),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Offline deterministic mode."),
    json_output: bool = typer.Option(False, "--json", help="Output full JSON result."),
) -> None:
    """Run an orchestrated security and quality test campaign against an authorized target."""
    types_list = [t.strip() for t in test_types.split(",") if t.strip()]
    doc_path = str(auth_doc.resolve()) if auth_doc else None

    result = run_security_test_campaign(
        target=str(target.resolve()),
        test_types=types_list,
        agent_count=agents,
        max_cost_usd=budget_cost,
        max_duration_seconds=budget_time,
        owned_target=owned_target,
        authorized_by=authorized_by,
        authorization_document=doc_path,
        dry_run=dry_run,
    )

    if json_output:
        print(json.dumps(result, indent=2))
        return

    if result.get("status") in ("rejected", "error"):
        print(f"Campaign refused or failed: {result.get('reason') or result.get('message')}")
        raise typer.Exit(code=1)

    print(f"Campaign {result.get('campaign_id')} completed successfully.")
    print(f"Target: {result.get('target')} | Status: {result.get('status')}")
    passed = result.get('total_passed')
    failed = result.get('total_failed')
    total = result.get('total_tests_run')
    print(f"Tests run: {total} (Passed: {passed}, Failed: {failed})")
    findings = result.get('findings_count')
    duration = result.get('duration_seconds')
    cost = result.get('actual_cost_usd')
    print(f"Findings: {findings} | Duration: {duration}s | Cost: ${cost}")


@campaign_app.command(name="get")
def cmd_campaign_get(
    campaign_id: str = typer.Argument(..., help="Campaign ID to inspect."),
    json_output: bool = typer.Option(True, "--json", help="Output JSON details."),
) -> None:
    """Retrieve details and findings of a test campaign."""
    res = get_security_test_campaign(campaign_id)
    if res.get("status") == "not_found":
        print(f"Campaign '{campaign_id}' not found.")
        raise typer.Exit(code=1)
    print(json.dumps(res, indent=2))


@campaign_app.command(name="export")
def cmd_campaign_export(
    campaign_id: str = typer.Argument(..., help="Campaign ID to export."),
    format: str = typer.Option("markdown", "--format", "-f", help="Format: json, markdown, html."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Destination file path."),
) -> None:
    """Export campaign report to markdown, HTML, or JSON."""
    out_str = str(output.resolve()) if output else None
    res = export_security_test_report(campaign_id, format=format, output_path=out_str)
    if res.get("status") != "success":
        print(f"Export failed: {res.get('message')}")
        raise typer.Exit(code=1)
    if out_str:
        print(f"Report exported to: {res.get('output_path')}")
    else:
        print(res.get("content"))


@vcs_app.command(name="repos")
def cmd_vcs_repos(
    provider: str = typer.Option("gitlab", "--provider", "-p", help="Provider (azure_devops, gitlab, git)."),
    project_or_org: str = typer.Option("", "--org", help="Organization or Project ID."),
    project: str = typer.Option("", "--project", help="Project name (for Azure DevOps)."),
) -> None:
    """List remote or local repositories."""
    from nexcoder_interfaces.tools.vcs import vcs_list_repositories

    result = vcs_list_repositories(provider=provider, project_or_org=project_or_org, project=project)
    if result.get("status") == "success":
        typer.echo(f"Repositories ({result.get('count', 0)}):")
        for repo in result.get("repositories", []):
            typer.echo(f"  - {repo.get('name')} ({repo.get('id')}) -> {repo.get('web_url')}")
    else:
        typer.echo(f"Error: {result.get('message')}", err=True)
        raise typer.Exit(code=1)


@vcs_app.command(name="issues")
def cmd_vcs_issues(
    provider: str = typer.Option("gitlab", "--provider", "-p", help="Provider (azure_devops, gitlab)."),
    action: str = typer.Option("list", "--action", "-a", help="Action (list, get, create)."),
    project_or_org: str = typer.Option("", "--org", help="Organization or Project ID."),
    project: str = typer.Option("", "--project", help="Project name."),
    issue_id: str = typer.Option("", "--id", help="Issue ID (for get action)."),
    title: str = typer.Option("", "--title", "-t", help="Issue title (for create action)."),
    body: str = typer.Option("", "--body", "-b", help="Issue description/body."),
) -> None:
    """Manage issues on Azure DevOps or GitLab."""
    from nexcoder_interfaces.tools.vcs import vcs_manage_issue

    result = vcs_manage_issue(
        provider=provider,
        action=action,
        project_or_org=project_or_org,
        project=project,
        issue_id=issue_id,
        title=title,
        body=body,
    )
    if result.get("status") == "success":
        if action == "list":
            typer.echo(f"Issues ({result.get('count', 0)}):")
            for item in result.get("issues", []):
                typer.echo(f"  #{item.get('number')} [{item.get('state')}] {item.get('title')}")
        else:
            typer.echo(f"Success: {result.get('issue')}")
    else:
        typer.echo(f"Error: {result.get('message')}", err=True)
        raise typer.Exit(code=1)


@vcs_app.command(name="prs")
def cmd_vcs_prs(
    provider: str = typer.Option("gitlab", "--provider", "-p", help="Provider (azure_devops, gitlab)."),
    action: str = typer.Option("list", "--action", "-a", help="Action (list, get, create, merge)."),
    project_or_org: str = typer.Option("", "--org", help="Organization or Project ID."),
    project: str = typer.Option("", "--project", help="Project name."),
    pr_id: str = typer.Option("", "--id", help="Pull request ID."),
    title: str = typer.Option("", "--title", "-t", help="PR title."),
    body: str = typer.Option("", "--body", "-b", help="PR description."),
    source_branch: str = typer.Option("", "--source", "-s", help="Source branch."),
    target_branch: str = typer.Option("develop", "--target", help="Target branch."),
) -> None:
    """Manage pull requests or merge requests."""
    from nexcoder_interfaces.tools.vcs import vcs_manage_pull_request

    result = vcs_manage_pull_request(
        provider=provider,
        action=action,
        project_or_org=project_or_org,
        project=project,
        pr_id=pr_id,
        title=title,
        body=body,
        source_branch=source_branch,
        target_branch=target_branch,
    )
    if result.get("status") == "success":
        if action == "list":
            typer.echo(f"Pull Requests ({result.get('count', 0)}):")
            for item in result.get("pull_requests", []):
                pr_num = item.get("number")
                pr_st = item.get("state")
                pr_title = item.get("title")
                src = item.get("source_branch")
                tgt = item.get("target_branch")
                typer.echo(f"  #{pr_num} [{pr_st}] {pr_title} ({src} -> {tgt})")
        else:
            typer.echo(f"Success: {result.get('pull_request')}")
    else:
        typer.echo(f"Error: {result.get('message')}", err=True)
        raise typer.Exit(code=1)


@vcs_app.command(name="svn")
def cmd_vcs_svn(
    action: str = typer.Option("status", "--action", "-a", help="Action (status, diff, log, checkout, commit)."),
    repo_url: str = typer.Option("", "--url", help="Repository URL."),
    dest_path: str = typer.Option(".", "--dest", "-d", help="Working copy directory."),
    message: str = typer.Option("", "--msg", "-m", help="Commit message."),
    revision: str = typer.Option("HEAD", "--rev", help="Revision number."),
) -> None:
    """Run SVN operations via the svn CLI."""
    from nexcoder_interfaces.tools.vcs import vcs_svn_operation

    result = vcs_svn_operation(
        action=action,
        repo_url=repo_url,
        dest_path=dest_path,
        message=message,
        revision=revision,
    )
    if result.get("status") == "success":
        typer.echo(f"SVN {action} completed successfully.")
        typer.echo(result)
    else:
        typer.echo(f"Error: {result.get('message')}", err=True)
        raise typer.Exit(code=1)


@vcs_app.command(name="tortoise")
def cmd_vcs_tortoise(
    command: str = typer.Option(
        "commit",
        "--command",
        "-c",
        help="TortoiseGit command (commit, log, diff, push, pull, status).",
    ),
    path: str = typer.Option(".", "--path", "-p", help="Target working tree path."),
) -> None:
    """Generate or launch Windows TortoiseGit command shortcut."""
    from nexcoder_planning.vcs import TortoiseGitProvider

    prov = TortoiseGitProvider(working_dir=path)
    cmd_line = prov.get_gui_shortcut_command(command=command, path=path)
    installed = prov.is_tortoisegit_installed()
    typer.echo(f"TortoiseGit Installed: {installed}")
    typer.echo(f"Command line: {cmd_line}")


@vcs_app.command(name="audit")
def cmd_vcs_audit(
    provider: str = typer.Option("", "--provider", "-p", help="Filter by provider."),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of records to show."),
) -> None:
    """View repository and VCS audit logs."""
    from nexcoder_interfaces.tools.vcs import vcs_audit_records

    result = vcs_audit_records(provider=provider or None, limit=limit)
    if result.get("status") == "success":
        typer.echo(f"Audit Records ({result.get('count', 0)}):")
        for rec in result.get("records", []):
            ts = rec.get("timestamp")
            p = rec.get("provider")
            a = rec.get("action")
            rt = rec.get("resource_type")
            rid = rec.get("resource_id")
            s = rec.get("success")
            typer.echo(f"  [{ts}] {p} - {a} on {rt}:{rid} (success={s})")
    else:
        typer.echo(f"Error: {result.get('message')}", err=True)
        raise typer.Exit(code=1)


def main() -> None:
    """CLI entry point for console_scripts."""
    app()


if __name__ == "__main__":
    main()
