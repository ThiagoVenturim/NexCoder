"""Command-line interface for multi-agent extreme application testing (nexcoder-testing)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nexcoder_control.approval import TargetAuthorizationGate, TargetNotAuthorizedError
from nexcoder_control.metering.audit import AppendOnlyAuditLog

from nexcoder_testing.models import ExtremeTestConfig, TestScope
from nexcoder_testing.orchestrator import ExtremeTestOrchestrator
from nexcoder_testing.synthetic import create_synthetic_target_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nexcoder-testing",
        description="Multi-agent extreme application testing (unit, system, DOM, API, and security) for owned targets.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available extreme testing commands")

    # run
    run_p = subparsers.add_parser("run", help="Run extreme application tests on an owned/authorized target")
    run_p.add_argument("path", default=".", nargs="?", help="Path to target application directory")
    run_p.add_argument(
        "--num-agents",
        "-n",
        type=int,
        default=3,
        help="Number of parallel test worker agents to run (default: 3)",
    )
    run_p.add_argument(
        "--scopes",
        nargs="*",
        choices=[s.value for s in TestScope.all_scopes()],
        default=None,
        help="Specific testing scopes to execute (unit, system, dom, api, security)",
    )
    run_p.add_argument(
        "--base-url",
        default=None,
        help="Optional local base URL of running owned target application",
    )
    run_p.add_argument(
        "--owned-target",
        action="store_true",
        default=False,
        help="Confirm target is owned or explicitly authorized per USAGE_POLICY.md",
    )
    run_p.add_argument(
        "--authorized-by",
        default="owner",
        help="Identity of the owner or team authorizing the test run",
    )
    run_p.add_argument(
        "--approval-token",
        default=None,
        help="Single-use control plane approval token for target authorization",
    )
    run_p.add_argument(
        "--offline",
        action="store_true",
        default=True,
        help="Run in offline mode (default: True)",
    )
    run_p.add_argument(
        "--json",
        action="store_true",
        help="Output consolidated report as JSON",
    )
    run_p.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Optional file path to write the Markdown or JSON report",
    )

    # demo-synthetic
    demo_p = subparsers.add_parser(
        "demo-synthetic",
        help="Create a synthetic target application in a workspace directory and run N-agent offline tests",
    )
    demo_p.add_argument("workspace_dir", type=Path, help="Directory where synthetic app will be materialized")
    demo_p.add_argument("--num-agents", "-n", type=int, default=3, help="Number of parallel agents (default: 3)")
    demo_p.add_argument("--clean-target", action="store_true", help="Create flaw-free synthetic target")
    demo_p.add_argument("--json", action="store_true", help="Output consolidated report as JSON")

    return parser


def main(
    argv: list[str] | None = None,
    *,
    audit_log: AppendOnlyAuditLog | None = None,
    target_gate: TargetAuthorizationGate | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    orchestrator = ExtremeTestOrchestrator(target_gate=target_gate, audit_log=audit_log)

    if args.command == "run":
        scopes = [TestScope(s) for s in args.scopes] if args.scopes else TestScope.all_scopes()
        cfg = ExtremeTestConfig(
            target_path=Path(args.path),
            base_url=args.base_url,
            num_agents=args.num_agents,
            scopes=scopes,
            offline=args.offline,
            owned_target=args.owned_target,
            authorized_by=args.authorized_by,
            approval_token=args.approval_token,
        )
        try:
            report = orchestrator.run(cfg)
        except TargetNotAuthorizedError as exc:
            print(f"Refused: {exc}", file=sys.stderr)
            return 1

        rendered = report.model_dump_json(indent=2) if args.json else report.to_markdown()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print(f"Report written to {args.output}")
        else:
            print(rendered)
        return 0

    if args.command == "demo-synthetic":
        synth = create_synthetic_target_app(args.workspace_dir, include_flaws=not args.clean_target)
        cfg = ExtremeTestConfig(
            target_path=synth.root_dir,
            num_agents=args.num_agents,
            scopes=TestScope.all_scopes(),
            offline=True,
            owned_target=True,
            authorized_by="synthetic-owner",
            endpoints=synth.endpoints,
            screens=synth.screens,
            system_flows=synth.system_flows,
        )
        report = orchestrator.run(cfg, requester=synth.dispatch_request)
        rendered = report.model_dump_json(indent=2) if args.json else report.to_markdown()
        print(rendered)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
