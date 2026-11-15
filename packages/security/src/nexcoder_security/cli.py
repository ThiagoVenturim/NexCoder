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
from nexcoder_security.review import SecurityReviewEngine
from nexcoder_security.scanners import MultiScannerEngine, SyftScanner
from nexcoder_security.server import (
    DataMasker,
    HardeningOptions,
    NginxConfigGenerator,
    ServerIsolationAuditor,
    audit_server_action,
    generate_bash_hardening_script,
    generate_ps1_hardening_script,
    validate_nginx_config_in_container,
)


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
    subparser.add_argument(
        "--auth-doc",
        "--authorization-document",
        dest="auth_doc",
        default=None,
        help="Path or content of a signed authorization document (YAML/JSON)",
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

    # review
    review_p = subparsers.add_parser(
        "review",
        help="Run comprehensive security review (prompt injection, SQLi, data leakage, general security)",
    )
    review_p.add_argument("path", default=".", nargs="?", help="Target path to review")
    review_p.add_argument("--json", action="store_true", help="Output JSON report")
    review_p.add_argument("--markdown", action="store_true", help="Output Markdown report")
    review_p.add_argument("--enable-monitor", action="store_true", help="Enable optional runtime security monitor")
    review_p.add_argument(
        "--oss-mode",
        action="store_true",
        help="Enable OSS contribution responsible disclosure mode",
    )
    _add_target_auth_args(review_p)

    # server
    server_p = subparsers.add_parser(
        "server",
        help="Server exposure, Nginx reverse proxy, OS hardening, privatization, and PII masking",
    )
    server_subs = server_p.add_subparsers(dest="server_action", help="Server exposure operations")

    # server nginx
    nginx_p = server_subs.add_parser("nginx", help="Generate secure Nginx reverse proxy and TLS configuration")
    nginx_p.add_argument("--profile", choices=["basic", "advanced"], default="basic", help="Configuration profile")
    nginx_p.add_argument("--domain", default="localhost", help="Domain name / server_name")
    nginx_p.add_argument("--upstream", default="127.0.0.1:8000", help="Upstream backend host:port")
    nginx_p.add_argument("--no-tls", action="store_true", help="Disable TLS and serve plain HTTP")
    nginx_p.add_argument("--output", help="Write generated config to file path")
    nginx_p.add_argument(
        "--validate-container",
        action="store_true",
        help="Validate generated config using nginx -t in container",
    )
    _add_target_auth_args(nginx_p)

    # server hardening
    hard_p = server_subs.add_parser("hardening", help="Generate idempotent server hardening scripts")
    hard_p.add_argument("--profile", choices=["basic", "advanced"], default="basic", help="Hardening profile")
    hard_p.add_argument("--os", choices=["linux", "windows"], default="linux", help="Target operating system")
    hard_p.add_argument("--output-bash", help="Output path for generated bash script")
    hard_p.add_argument("--output-ps1", help="Output path for generated powershell script")
    _add_target_auth_args(hard_p)

    # server isolate
    iso_p = server_subs.add_parser("isolate", help="Audit and remediate unshielded port bindings in docker-compose")
    iso_p.add_argument("path", default="docker-compose.yml", nargs="?", help="Path to compose file to audit")
    iso_p.add_argument("--remediate", action="store_true", help="Remediate compose file in-place to 127.0.0.1 bindings")
    _add_target_auth_args(iso_p)

    # server mask
    mask_p = server_subs.add_parser("mask", help="Mask PII and secrets in text, logs, SQL dumps, or JSON")
    mask_p.add_argument("path", help="Path to file to mask")
    mask_p.add_argument(
        "--format",
        choices=["text", "log", "json", "sql", "csv"],
        default="text",
        help="Content format",
    )
    mask_p.add_argument(
        "--strategy",
        choices=["placeholder", "redact", "hash"],
        default="placeholder",
        help="Masking strategy",
    )
    mask_p.add_argument("--salt", default="nexcoder-default-salt", help="Salt for hash masking")
    mask_p.add_argument("--output", help="Write masked content to file path")
    _add_target_auth_args(mask_p)

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
                authorization_document=getattr(args, "auth_doc", None),
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
                authorization_document=getattr(args, "auth_doc", None),
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
                authorization_document=getattr(args, "auth_doc", None),
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

    if args.command == "review":
        review_engine = SecurityReviewEngine(target_gate=active_gate, audit_log=active_gate.audit_log)
        try:
            report = review_engine.review(
                target_path=args.path,
                owned_target=args.owned_target,
                authorized_by=args.authorized_by,
                approval_token=args.approval_token,
                enable_runtime_monitor=args.enable_monitor,
                oss_contribution_mode=args.oss_mode,
            )
        except TargetNotAuthorizedError as exc:
            print(f"Refused: {exc}", file=sys.stderr)
            return 1

        if args.json:
            print(report.model_dump_json(indent=2))
        elif args.markdown:
            print(report.to_markdown())
        else:
            print(f"Security Review: {report.target_path}")
            print(f"Total findings: {report.total_findings}")
            print(f"Disclosure mode: {report.disclosure_mode} (exploit_published={report.exploit_published})")
            for item in report.findings:
                print(f"  [{item.severity.upper()}] {item.location} - {item.title} ({item.rule_id})")
                print(f"    Fix: {item.how_to_fix}")
        return 0

    if args.command == "server":
        if args.server_action == "nginx":
            enable_tls = not args.no_tls
            if args.profile == "advanced":
                gen = NginxConfigGenerator.advanced(
                    domain=args.domain,
                    upstreams=[args.upstream],
                )
            else:
                gen = NginxConfigGenerator.basic(
                    upstream=args.upstream,
                    domain=args.domain,
                    enable_tls=enable_tls,
                )
            conf = gen.generate()

            if args.validate_container:
                val = validate_nginx_config_in_container(conf)
                if not val.valid:
                    print(f"Validation failed: {val.details}", file=sys.stderr)
                    return 1
                print(f"Nginx config validation: OK (container={val.executed_in_container})")

            if args.output:
                Path(args.output).write_text(conf, encoding="utf-8")
                print(f"Nginx configuration written to: {args.output}")
            else:
                print(conf)

            audit_server_action(
                action="generate_nginx_config",
                resource=args.domain,
                details={"profile": args.profile, "upstream": args.upstream, "tls": enable_tls},
                audit_log=active_gate.audit_log,
                actor=args.authorized_by,
            )
            return 0

        if args.server_action == "hardening":
            opts = HardeningOptions(
                profile=args.profile,
                os_target=args.os,
            )
            bash_script = generate_bash_hardening_script(opts)
            ps1_script = generate_ps1_hardening_script(opts)

            if args.output_bash:
                Path(args.output_bash).write_text(bash_script, encoding="utf-8")
                print(f"Bash hardening script written to: {args.output_bash}")
            if args.output_ps1:
                Path(args.output_ps1).write_text(ps1_script, encoding="utf-8")
                print(f"PowerShell hardening script written to: {args.output_ps1}")
            if not args.output_bash and not args.output_ps1:
                print(bash_script if args.os == "linux" else ps1_script)

            audit_server_action(
                action="generate_hardening_scripts",
                resource=args.os,
                details={"profile": args.profile, "target_os": args.os},
                audit_log=active_gate.audit_log,
                actor=args.authorized_by,
            )
            return 0

        if args.server_action == "isolate":
            target = Path(args.path)
            if not target.exists():
                print(f"File not found: {args.path}", file=sys.stderr)
                return 1
            content = target.read_text(encoding="utf-8")
            auditor = ServerIsolationAuditor()
            rep = auditor.audit_compose_text(content)

            if rep.passed:
                print(f"Isolation audit PASSED for {args.path} (0 violations)")
            else:
                print(f"Isolation audit FAILED for {args.path} ({rep.total_violations} violations):")
                for v in rep.violations:
                    print(f"  [{v.severity.upper()}] {v.target}: {v.message}")
                    print(f"    Remediation: {v.remediation}")

            if args.remediate and not rep.passed:
                remediated = auditor.remediate_compose_text(content)
                target.write_text(remediated, encoding="utf-8")
                print(f"Remediated {args.path} with 127.0.0.1 bindings.")

            audit_server_action(
                action="audit_isolation",
                resource=str(target),
                details={"passed": rep.passed, "violations": rep.total_violations},
                audit_log=active_gate.audit_log,
                actor=args.authorized_by,
            )
            return 0 if rep.passed or args.remediate else 1

        if args.server_action == "mask":
            target = Path(args.path)
            if not target.exists():
                print(f"File not found: {args.path}", file=sys.stderr)
                return 1
            content = target.read_text(encoding="utf-8")
            masker = DataMasker(strategy=args.strategy, salt=args.salt)

            if args.format == "json":
                masked = str(masker.mask_json(content))
            elif args.format == "sql":
                masked = masker.mask_sql_dump(content)
            elif args.format == "csv":
                masked = masker.mask_csv(content)
            elif args.format == "log":
                masked = masker.mask_log_file(content)
            else:
                masked = masker.mask_text(content)

            if args.output:
                Path(args.output).write_text(masked, encoding="utf-8")
                print(f"Masked output written to: {args.output}")
            else:
                print(masked)

            audit_server_action(
                action="mask_data",
                resource=str(target),
                details={"strategy": args.strategy, "format": args.format},
                audit_log=active_gate.audit_log,
                actor=args.authorized_by,
            )
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
