from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nexcoder_agents.catalog.registry import AgentCatalog
from nexcoder_agents.catalog.skills import SkillCatalog
from nexcoder_agents.engine.pipelines import get_pipeline_template, list_pipeline_templates
from nexcoder_agents.export import export_claude_package
from nexcoder_agents.software_engineering import SoftwareEngineeringAdvisor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nexcoder-agents",
        description="CLI tooling for nexcoder agents, personas, skills, and Claude Code export.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # export subcommand
    export_parser = subparsers.add_parser("export", help="Export agent catalog to external formats.")
    export_parser.add_argument("--claude", action="store_true", required=True, help="Export as Claude Code package.")
    export_parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path("dist/claude-package"),
        help="Target output directory (default: dist/claude-package).",
    )
    export_parser.add_argument("--sector", "-s", type=str, default=None, help="Filter by sector.")
    export_parser.add_argument("--tier", "-t", type=str, default=None, help="Filter by tier.")
    export_parser.add_argument("--zip", action="store_true", help="Compress package into a .zip file.")

    # list-agents subcommand
    list_agents_parser = subparsers.add_parser("list-agents", help="List registered personas in catalog.")
    list_agents_parser.add_argument("--sector", "-s", type=str, default=None, help="Filter by sector.")
    list_agents_parser.add_argument("--tier", "-t", type=str, default=None, help="Filter by tier.")

    # list-skills subcommand
    subparsers.add_parser("list-skills", help="List registered skills in catalog.")

    # list-pipelines subcommand
    list_pipelines_parser = subparsers.add_parser("list-pipelines", help="List ready-made pipeline templates.")
    list_pipelines_parser.add_argument("--category", "-c", type=str, default=None, help="Filter by category.")

    # show-pipeline subcommand
    show_pipeline_parser = subparsers.add_parser("show-pipeline", help="Show details of a pipeline template.")
    show_pipeline_parser.add_argument("name", type=str, help="Pipeline template name.")

    # review-project subcommand
    review_parser = subparsers.add_parser(
        "review-project",
        help="Run software engineering architecture review, ADR generation, and guided refactoring on a project.",
    )
    review_parser.add_argument("project_dir", type=Path, help="Path to target project directory.")
    review_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Optional path to write the Markdown assessment report.",
    )
    review_parser.add_argument(
        "--no-refactor",
        action="store_true",
        help="Skip applying safe test-backed refactoring in workspace copy.",
    )

    return parser


def main(args: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.command:
        parser.print_help()
        return 0

    catalog = AgentCatalog.default()
    skills = SkillCatalog.default()

    if parsed.command == "export":
        sectors = [parsed.sector] if parsed.sector else None
        tiers = [parsed.tier] if parsed.tier else None
        result = export_claude_package(
            catalog=catalog,
            output_dir=parsed.output_dir,
            skill_catalog=skills,
            sectors=sectors,
            tiers=tiers,
            zip_output=parsed.zip,
        )
        print(
            f"Exported {len(result.agents_exported)} agents and "
            f"{len(result.skills_exported)} skills to {result.output_dir}"
        )
        if result.zip_path:
            print(f"Archive created at {result.zip_path}")
        return 0

    if parsed.command == "list-agents":
        agents = catalog.list(sector=parsed.sector, tier=parsed.tier)
        print(f"Found {len(agents)} persona(s):")
        for a in agents:
            print(f"  - {a.slug:<28} [{a.sector:<12} | {a.tier:<6}] {a.name}")
        return 0

    if parsed.command == "list-skills":
        all_skills = skills.list()
        print(f"Found {len(all_skills)} skill(s):")
        for s in all_skills:
            print(f"  - {s.slug:<32} {s.description}")
        return 0

    if parsed.command == "list-pipelines":
        templates = list_pipeline_templates(category=parsed.category)
        print(f"Found {len(templates)} pipeline template(s):")
        for t in templates:
            print(f"  - {t.name:<24} [{t.category:<12}] {t.description}")
        return 0

    if parsed.command == "show-pipeline":
        try:
            tmpl = get_pipeline_template(parsed.name)
            print(f"Pipeline: {tmpl.name}")
            print(f"Category: {tmpl.category}")
            print(f"Description: {tmpl.description}")
            print(f"Required Inputs: {', '.join(tmpl.required_inputs)}")
            return 0
        except KeyError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if parsed.command == "review-project":
        try:
            advisor = SoftwareEngineeringAdvisor()
            report = advisor.analyze_project(
                parsed.project_dir,
                apply_safe_refactor=not parsed.no_refactor,
            )
            md = report.to_markdown()
            if parsed.output:
                parsed.output.parent.mkdir(parents=True, exist_ok=True)
                parsed.output.write_text(md, encoding="utf-8")
                print(f"Software engineering report written to {parsed.output}")
            else:
                print(md)
            return 0
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
