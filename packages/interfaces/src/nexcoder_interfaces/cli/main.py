from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from nexcoder_interfaces.mcp.server import MCPServer
from nexcoder_interfaces.plugin.claude import export_claude_plugin, write_mcp_json
from nexcoder_interfaces.tools.agents import run_agent, run_pipeline
from nexcoder_interfaces.tools.code import generate_docs, search_code
from nexcoder_interfaces.tools.ideation import judge_idea, research_idea
from nexcoder_interfaces.tools.planning import plan_sprints
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


def main() -> None:
    """CLI entry point for console_scripts."""
    app()


if __name__ == "__main__":
    main()
