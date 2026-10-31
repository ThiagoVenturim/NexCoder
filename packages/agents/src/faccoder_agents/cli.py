from __future__ import annotations

import argparse
import sys
from pathlib import Path

from faccoder_agents.catalog.registry import AgentCatalog
from faccoder_agents.catalog.skills import SkillCatalog
from faccoder_agents.export import export_claude_package


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="faccoder-agents",
        description="CLI tooling for faccoder agents, personas, skills, and Claude Code export.",
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
