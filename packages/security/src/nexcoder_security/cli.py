from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from nexcoder_control.approval import (
    TargetAuthorizationGate,
    TargetNotAuthorizedError,
)
from nexcoder_control.metering.audit import AppendOnlyAuditLog

from nexcoder_security.gate import (
    GatePolicy,
    SecurityGateEvaluator,
    scaffold_app_security,
)
from nexcoder_security.scanners import MultiScannerEngine, SyftScanner


def _add_target_auth_args(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--owned-target",
        action="store_true",
        default=False,
        help="Confirm target is owned or explicitly authorized per USAGE_POLICY.md",
    )
    subparser.add_argument(
        "--authorized-by",
        default="owner",
        help="Identity of the person or team authorizing the scan (recorded in audit log)",
    )
    subparser.add_argument(
        "--approval-token",
        default=None,
        help="Single-use control plane approval token for target authorization",
    )


def main(
    argv: list[str] | None = None,
    *,
    audit_log: AppendOnlyAuditLog | None = None,
    target_gate: TargetAuthorizationGate | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="nexcoder-security",
        description="Security scanners, specialist agents, and release gate for nexcoder.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available security commands")

    # scan
    scan_p = subparsers.add_parser("scan", help="Run security scanners over a path")
    scan_p.add_argument("path", default=".", nargs="?", help="Path to scan")
    scan_p.add_argument("--offline", action="store_true", help="Force offline heuristics and fallback engines")
    scan_p.add_argument(
        "--scanners",
        nargs="*",
        help="Specific scanners to run (semgrep, bandit, gitleaks, osv-scanner, trivy, pip-audit, syft)",
    )
    scan_p.add_argument("--json", action="store_true", help="Output full JSON result")
    _add_target_auth_args(scan_p)

    # gate
    gate_p = subparsers.add_parser("gate", help="Evaluate security gate for release gating")
    gate_p.add_argument("path", default=".", nargs="?", help="Path to evaluate")
    gate_p.add_argument("--offline", action="store_true", help="Run scanners offline")
    gate_p.add_argument("--max-critical", type=int, default=0, help="Maximum allowed critical findings")
    gate_p.add_argument("--max-high", type=int, default=0, help="Maximum allowed high findings")
    gate_p.add_argument("--require-sbom", action="store_true", help="Require a valid SBOM to approve release")
    gate_p.add_argument(
        "--policy",
        choices=["default", "production"],
        default=None,
        help="Gate policy preset (defaults to 'production' if CI=1 is set, otherwise 'default')",
    )
    gate_p.add_argument(
        "--allow-fallbacks",
        action="store_true",
        default=None,
        help="Explicitly permit fallback heuristic scans",
    )
    gate_p.add_argument(
        "--forbid-fallbacks",
        action="store_true",
        default=None,
        help="Explicitly forbid fallback heuristic scans",
    )
    _add_target_auth_args(gate_p)

    # sbom
    sbom_p = subparsers.add_parser("sbom", help="Generate SBOM (CycloneDX / SPDX) for a repository or application")
    sbom_p.add_argument("path", default=".", nargs="?", help="Target project path")
    sbom_p.add_argument("--format", default="cyclonedx-json", choices=["cyclonedx-json", "spdx-json"])
    sbom_p.add_argument("--offline", action="store_true", help="Use offline dependency parser")
    _add_target_auth_args(sbom_p)

    # init-app-security
    init_p = subparsers.add_parser("init-app-security", help="Scaffold SECURITY.md and CSP headers for a project")
    init_p.add_argument("path", default=".", nargs="?", help="Target project directory")
    init_p.add_argument("--name", default="Application", help="Project name")
    init_p.add_argument("--email", default="security@example.com", help="Responsible disclosure contact email")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    active_gate = target_gate or TargetAuthorizationGate(audit_log=audit_log)

    if args.command == "scan":
        engine = MultiScannerEngine(target_gate=active_gate, audit_log=active_gate.audit_log)
        try:
            result = engine.scan(
                target_path=args.path,
                enabled_scanners=args.scanners,
                force_offline=args.offline,
                owned_target=args.owned_target,
                authorized_by=args.authorized_by,
                approval_token=args.approval_token,
            )
        except TargetNotAuthorizedError as exc:
            print(f"Refused: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(result.model_dump_json(indent=2))
        else:
            print(f"Scanned: {result.target_path}")
            print(f"Total findings: {result.total_findings()}")
            print(f"Critical: {len(result.by_severity('critical'))}")  # type: ignore[arg-type]
            print(f"High: {len(result.by_severity('high'))}")  # type: ignore[arg-type]
            for f in result.findings:
                loc = f"{f.location.file_path}:{f.location.line_start}" if f.location else "general"
                print(f"  [{f.severity.upper()}] {f.scanner} - {f.title} ({loc})")
        if result.has_errors() or (result.metadata and not result.metadata.success):
            return 1
        return 0

    if args.command == "gate":
        engine = MultiScannerEngine(target_gate=active_gate, audit_log=active_gate.audit_log)
        try:
            scan_res = engine.scan(
                target_path=args.path,
                force_offline=args.offline,
                owned_target=args.owned_target,
                authorized_by=args.authorized_by,
                approval_token=args.approval_token,
            )
        except TargetNotAuthorizedError as exc:
            print(f"Refused: {exc}", file=sys.stderr)
            return 1

        is_ci = bool(os.environ.get("CI"))
        preset = args.policy or ("production" if is_ci else "default")

        if preset == "production":
            policy = GatePolicy.production(require_sbom=args.require_sbom)
        else:
            policy = GatePolicy(
                name="default",
                max_critical=args.max_critical,
                max_high=args.max_high,
                require_sbom=args.require_sbom,
                allow_fallbacks=True,
            )

        if args.allow_fallbacks is True:
            policy.allow_fallbacks = True
        elif args.forbid_fallbacks is True:
            policy.allow_fallbacks = False

        if args.max_critical != 0:
            policy.max_critical = args.max_critical
        if args.max_high != 0:
            policy.max_high = args.max_high

        evaluator = SecurityGateEvaluator(default_policy=policy)
        verdict = evaluator.evaluate(scan_res, policy=policy, sbom=scan_res.sbom)

        print(verdict.summary)
        for r in verdict.reasons:
            print(f"  - {r}")
        return 0 if verdict.passed else 1

    if args.command == "sbom":
        try:
            active_gate.verify_target(
                target=args.path,
                mode="sbom",
                owned_target=args.owned_target,
                authorized_by=args.authorized_by,
                approval_token=args.approval_token,
            )
        except TargetNotAuthorizedError as exc:
            print(f"Refused: {exc}", file=sys.stderr)
            return 1
        syft = SyftScanner()
        doc = syft.generate_sbom(target_path=args.path, output_format=args.format, force_offline=args.offline)
        print(doc.raw_content)
        return 0

    if args.command == "init-app-security":
        assets = scaffold_app_security(
            target_dir=Path(args.path),
            project_name=args.name,
            contact_email=args.email,
        )
        print("Generated security assets:")
        print(f"  SECURITY.md: {assets['security_md']}")
        print(f"  CSP Header: {assets['csp_header']}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
