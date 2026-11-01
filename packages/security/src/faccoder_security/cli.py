from __future__ import annotations

import argparse
import sys
from pathlib import Path

from faccoder_security.gate import (
    GatePolicy,
    SecurityGateEvaluator,
    scaffold_app_security,
)
from faccoder_security.scanners import MultiScannerEngine, SyftScanner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="faccoder-security",
        description="Security scanners, specialist agents, and release gate for faccoder.",
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

    # gate
    gate_p = subparsers.add_parser("gate", help="Evaluate security gate for release gating")
    gate_p.add_argument("path", default=".", nargs="?", help="Path to evaluate")
    gate_p.add_argument("--offline", action="store_true", help="Run scanners offline")
    gate_p.add_argument("--max-critical", type=int, default=0, help="Maximum allowed critical findings")
    gate_p.add_argument("--max-high", type=int, default=0, help="Maximum allowed high findings")
    gate_p.add_argument("--require-sbom", action="store_true", help="Require a valid SBOM to approve release")

    # sbom
    sbom_p = subparsers.add_parser("sbom", help="Generate SBOM (CycloneDX / SPDX) for a repository or application")
    sbom_p.add_argument("path", default=".", nargs="?", help="Target project path")
    sbom_p.add_argument("--format", default="cyclonedx-json", choices=["cyclonedx-json", "spdx-json"])
    sbom_p.add_argument("--offline", action="store_true", help="Use offline dependency parser")

    # init-app-security
    init_p = subparsers.add_parser("init-app-security", help="Scaffold SECURITY.md and CSP headers for a project")
    init_p.add_argument("path", default=".", nargs="?", help="Target project directory")
    init_p.add_argument("--name", default="Application", help="Project name")
    init_p.add_argument("--email", default="security@example.com", help="Responsible disclosure contact email")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "scan":
        engine = MultiScannerEngine()
        result = engine.scan(
            target_path=args.path,
            enabled_scanners=args.scanners,
            force_offline=args.offline,
        )
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
        engine = MultiScannerEngine()
        scan_res = engine.scan(target_path=args.path, force_offline=args.offline)
        policy = GatePolicy(
            max_critical=args.max_critical,
            max_high=args.max_high,
            require_sbom=args.require_sbom,
        )
        evaluator = SecurityGateEvaluator(default_policy=policy)
        verdict = evaluator.evaluate(scan_res, policy=policy, sbom=scan_res.sbom)

        print(verdict.summary)
        for r in verdict.reasons:
            print(f"  - {r}")
        return 0 if verdict.passed else 1

    if args.command == "sbom":
        try:
            syft = SyftScanner()
            doc = syft.generate_sbom(target_path=args.path, output_format=args.format, force_offline=args.offline)
            print(doc.raw_content)
            return 0
        except Exception as exc:
            print(f"SBOM generation failed: {exc}", file=sys.stderr)
            return 1

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
