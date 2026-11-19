from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nexcoder_control.approval import TargetNotAuthorizedError

from nexcoder_agents.ai_engineering import (
    AIFeatureAdvisor,
    AIFeatureRequest,
    RecipeType,
)
from nexcoder_agents.backends import BACKEND_NAMES, AgentBackendError, ContainerBackendConfig, build_agent_backend
from nexcoder_agents.catalog.registry import AgentCatalog
from nexcoder_agents.catalog.skills import SkillCatalog
from nexcoder_agents.data_engineering import (
    DataEngineeringAdvisor,
    IngestionMode,
    PipelineParadigm,
)
from nexcoder_agents.engine.pipelines import get_pipeline_template, list_pipeline_templates
from nexcoder_agents.export import export_claude_package
from nexcoder_agents.marketing import MarketingOrchestrator, TargetAudience
from nexcoder_agents.oss_contribution import OSSContributionAdvisor
from nexcoder_agents.quality import QualityReviewer
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

    # quality-review subcommand
    quality_parser = subparsers.add_parser(
        "quality-review",
        help="Run gated code quality and architecture detectors on an owned or authorized project.",
    )
    quality_parser.add_argument("project_dir", type=Path, help="Path to target project directory.")
    quality_parser.add_argument(
        "--owned-target",
        action="store_true",
        help="Confirm the target directory is owned by the operator.",
    )
    quality_parser.add_argument(
        "--authorized-by",
        type=str,
        default="owner",
        help="Actor authorizing the target review (default: owner).",
    )
    quality_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Optional path to write the Markdown quality report.",
    )

    # run-data-pipeline subcommand
    data_parser = subparsers.add_parser(
        "run-data-pipeline",
        help="Generate and run an offline data engineering pipeline (ingest -> transform -> quality -> observe).",
    )
    data_parser.add_argument(
        "description",
        type=str,
        help="Natural-language description of the data pipeline and analytical workload.",
    )
    data_parser.add_argument(
        "--name",
        "-n",
        type=str,
        default="commerce_orders_medallion",
        help="Pipeline identifier (default: commerce_orders_medallion).",
    )
    data_parser.add_argument(
        "--mode",
        choices=["batch", "stream"],
        default="batch",
        help="Ingestion mode: batch or stream (default: batch).",
    )
    data_parser.add_argument(
        "--paradigm",
        choices=["elt", "etl"],
        default="elt",
        help="Transformation paradigm: elt or etl (default: elt).",
    )
    data_parser.add_argument(
        "--workspace-dir",
        "-w",
        type=Path,
        default=None,
        help="Optional directory to materialize SQLite warehouse and generated Airflow/Dagster/dbt files.",
    )
    data_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Optional path to write the Markdown data pipeline execution report.",
    )

    # analyze-oss subcommand
    oss_parser = subparsers.add_parser(
        "analyze-oss",
        help="Run read-only open-source project analysis, bug/security discovery, and contribution report.",
    )
    oss_parser.add_argument(
        "target",
        type=str,
        help="Local path or repository URL of the target open-source project.",
    )
    oss_parser.add_argument(
        "--local-checkout",
        type=Path,
        default=None,
        help="Optional local directory when target is a repository URL.",
    )
    oss_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Optional path to write the Markdown OSS contribution report.",
    )

    # marketing-campaign subcommand
    mkt_parser = subparsers.add_parser(
        "marketing-campaign",
        help="Generate ad copy, social posts, video script/storyboard/subtitles, and calendar drafts.",
    )
    mkt_parser.add_argument(
        "feature",
        type=str,
        help="Summary or description of the product feature to promote.",
    )
    mkt_parser.add_argument(
        "--product-name",
        "-p",
        type=str,
        default="NexCoder",
        help="Product name (default: NexCoder).",
    )
    mkt_parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Optional directory to save all marketing drafts.",
    )
    mkt_parser.add_argument(
        "--audience",
        "-a",
        choices=["developers", "engineering_leaders", "tech_founders", "enterprise_architects"],
        default="developers",
        help="Target audience for copy generation.",
    )
    mkt_parser.add_argument(
        "--duration",
        "-d",
        type=float,
        default=30.0,
        help="Target video duration in seconds (default: 30.0).",
    )

    # implement-ai-feature subcommand
    ai_parser = subparsers.add_parser(
        "implement-ai-feature",
        help="Scaffold an end-to-end ML/AI feature in an authorized target project.",
    )
    ai_parser.add_argument("project_dir", type=Path, help="Path to target project directory.")
    ai_parser.add_argument(
        "--name",
        "-n",
        type=str,
        default="sample_classifier",
        help="Feature identifier name (default: sample_classifier).",
    )
    ai_parser.add_argument(
        "--recipe",
        "-r",
        choices=["classification", "extraction", "rag", "recommendation", "summarization", "chatbot"],
        default="classification",
        help="Ready-made recipe type.",
    )
    ai_parser.add_argument(
        "--description",
        "-d",
        type=str,
        default="Automated AI feature implemented by NexCoder",
        help="Natural language description of the feature capability.",
    )
    ai_parser.add_argument(
        "--latency-budget-ms",
        type=int,
        default=500,
        help="Inference latency target in milliseconds (default: 500).",
    )
    ai_parser.add_argument(
        "--monthly-budget-usd",
        type=float,
        default=100.0,
        help="Monthly cost ceiling in USD (default: 100.0).",
    )
    ai_parser.add_argument(
        "--owned-target",
        action="store_true",
        default=True,
        help="Confirm operator ownership of target project.",
    )
    ai_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip writing generated files to disk.",
    )
    ai_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Optional path to write the Markdown summary report.",
    )

    # evaluate-ml-approach subcommand
    approach_parser = subparsers.add_parser(
        "evaluate-ml-approach",
        help="Evaluate whether a feature requires rules, classical ML, or LLM/RAG.",
    )
    approach_parser.add_argument(
        "description",
        type=str,
        help="Description of feature workload.",
    )
    approach_parser.add_argument(
        "--recipe",
        "-r",
        choices=["classification", "extraction", "rag", "recommendation", "summarization", "chatbot"],
        default="classification",
        help="Recipe type (default: classification).",
    )
    approach_parser.add_argument(
        "--latency-budget-ms",
        type=int,
        default=500,
        help="Maximum allowed latency in milliseconds.",
    )
    approach_parser.add_argument(
        "--sample-count",
        type=int,
        default=0,
        help="Count of available training samples.",
    )

    # dispatch subcommand (agent backends, issue #115)
    dispatch_parser = subparsers.add_parser(
        "dispatch",
        help="Send one task to an agent backend (offline by default, or the agent CLI container) and print JSON.",
    )
    dispatch_parser.add_argument("prompt", type=str, help="Task text.")
    dispatch_parser.add_argument(
        "--backend",
        choices=list(BACKEND_NAMES),
        default=None,
        help="Agent backend (default: $NEXCODER_AGENT_BACKEND or offline).",
    )
    dispatch_parser.add_argument("--system-prompt", type=str, default=None, help="Optional system prompt.")
    dispatch_parser.add_argument("--timeout", type=float, default=None, help="Task timeout in seconds.")
    dispatch_parser.add_argument("--actor", type=str, default="cli", help="Actor recorded in the audit log.")
    dispatch_parser.add_argument("--runtime", type=str, default="docker", help="Container runtime (docker or podman).")
    dispatch_parser.add_argument("--image", type=str, default="nexcoder/agent-cli:local", help="Agent CLI image.")
    dispatch_parser.add_argument("--volume", type=str, default="nexcoder-agent-cli-home", help="Login volume name.")
    dispatch_parser.add_argument("--cli", type=str, default="claude", help="Adapter inside the image.")
    dispatch_parser.add_argument("--mode", choices=["run", "exec"], default="run", help="docker run or docker exec.")
    dispatch_parser.add_argument("--container-name", type=str, default="nexcoder-agent-cli", help="For exec mode.")
    dispatch_parser.add_argument("--workspace", type=Path, default=None, help="Directory mounted at /workspace.")
    dispatch_parser.add_argument("--writable-workspace", action="store_true", help="Mount the workspace read-write.")
    dispatch_parser.add_argument("--network", type=str, default=None, help="Container network.")
    dispatch_parser.add_argument(
        "--command",
        dest="agent_command",
        type=str,
        default=None,
        help="Argv for the command backend (default: $NEXCODER_AGENT_COMMAND).",
    )

    return parser


def _dispatch(parsed: argparse.Namespace) -> int:
    from nexcoder_control.metering.audit import AppendOnlyAuditLog
    from nexcoder_control.metering.cost_tracker import CostTracker

    audit_log = AppendOnlyAuditLog()
    cost_tracker = CostTracker()
    kwargs: dict = {"audit_log": audit_log, "cost_tracker": cost_tracker}
    if parsed.timeout is not None:
        kwargs["timeout_s"] = parsed.timeout
    try:
        config = ContainerBackendConfig(
            runtime=parsed.runtime,
            image=parsed.image,
            credentials_volume=parsed.volume,
            cli=parsed.cli,
            mode=parsed.mode,
            container_name=parsed.container_name,
            workspace_dir=parsed.workspace,
            workspace_read_only=not parsed.writable_workspace,
            network=parsed.network,
            **({"timeout_s": parsed.timeout} if parsed.timeout is not None else {}),
        )
        backend = build_agent_backend(
            parsed.backend, container_config=config, command=parsed.agent_command, **kwargs
        )
    except (AgentBackendError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    result = backend.dispatch(
        parsed.prompt,
        system_prompt=parsed.system_prompt,
        timeout_s=parsed.timeout,
        actor=parsed.actor,
        agent_id="cli_dispatch",
    )
    payload = result.model_dump(mode="json")
    payload["audit_events"] = len(audit_log.query(actor=parsed.actor))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def main(args: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.command:
        parser.print_help()
        return 0

    if parsed.command == "dispatch":
        return _dispatch(parsed)

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

    if parsed.command == "quality-review":
        try:
            reviewer = QualityReviewer()
            report = reviewer.review(
                parsed.project_dir,
                owned_target=parsed.owned_target,
                authorized_by=parsed.authorized_by,
            )
            md = report.to_markdown()
            if parsed.output:
                parsed.output.parent.mkdir(parents=True, exist_ok=True)
                parsed.output.write_text(md, encoding="utf-8")
                print(f"Quality review report written to {parsed.output}")
            else:
                print(md)
            return 0
        except (TargetNotAuthorizedError, FileNotFoundError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if parsed.command == "run-data-pipeline":
        advisor = DataEngineeringAdvisor()
        mode = IngestionMode.STREAM if parsed.mode == "stream" else IngestionMode.BATCH
        paradigm = PipelineParadigm.ETL if parsed.paradigm == "etl" else PipelineParadigm.ELT
        result = advisor.run_pipeline_from_description(
            description=parsed.description,
            pipeline_name=parsed.name,
            ingestion_mode=mode,
            paradigm=paradigm,
            workspace_dir=parsed.workspace_dir,
        )
        md = result.to_markdown()
        if parsed.output:
            parsed.output.parent.mkdir(parents=True, exist_ok=True)
            parsed.output.write_text(md, encoding="utf-8")
            print(f"Data engineering pipeline report written to {parsed.output}")
        else:
            print(md)
        return 0

    if parsed.command == "analyze-oss":
        try:
            oss_advisor = OSSContributionAdvisor()
            oss_report = oss_advisor.analyze_oss_project(
                parsed.target,
                local_checkout=parsed.local_checkout,
                read_only=True,
                dry_run=True,
            )
            md = oss_report.to_markdown()
            if parsed.output:
                parsed.output.parent.mkdir(parents=True, exist_ok=True)
                parsed.output.write_text(md, encoding="utf-8")
                print(f"OSS contribution report written to {parsed.output}")
            else:
                print(md)
            return 0
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if parsed.command == "marketing-campaign":
        orchestrator = MarketingOrchestrator()
        aud_map = {
            "developers": TargetAudience.DEVELOPERS,
            "engineering_leaders": TargetAudience.ENGINEERING_LEADERS,
            "tech_founders": TargetAudience.TECH_FOUNDERS,
            "enterprise_architects": TargetAudience.ENTERPRISE_ARCHITECTS,
        }
        bundle = orchestrator.generate_campaign(
            product_name=parsed.product_name,
            feature_summary=parsed.feature,
            output_dir=parsed.output_dir,
            audience=aud_map.get(parsed.audience, TargetAudience.DEVELOPERS),
            video_duration_seconds=parsed.duration,
        )
        print("Marketing campaign generated successfully.")
        print(f"Draft directory: {bundle.draft_directory}")
        print(f"Ads generated: {len(bundle.ads)} channels")
        print("Social posts: LinkedIn, Instagram carousel, TikTok video script")
        print("Video artifacts: Storyboard, SRT, VTT, narration WAV, assembly scripts")
        print(
            f"Calendar: {len(bundle.calendar.schedule)} posts scheduled, "
            f"{len(bundle.calendar.nextor_tasks)} Nextor tasks"
        )
        return 0

    if parsed.command == "implement-ai-feature":
        try:
            advisor = AIFeatureAdvisor()
            req = AIFeatureRequest(
                project_dir=str(parsed.project_dir),
                feature_name=parsed.name,
                recipe=RecipeType(parsed.recipe),
                description=parsed.description,
                latency_budget_ms=parsed.latency_budget_ms,
                monthly_budget_usd=parsed.monthly_budget_usd,
                owned_target=parsed.owned_target,
            )
            res = advisor.implement_feature(req, write_to_disk=not parsed.dry_run, run_eval=True)
            output_lines = [
                f"# AI Feature Implementation: {res.feature_name}",
                f"- **Recipe**: {res.recipe.value}",
                f"- **Approach**: {res.approach_decision.approach.value}",
                f"- **Model**: {res.approach_decision.recommended_model}",
                f"- **Files Generated**: {len(res.generated_files)}",
                f"- **Audit Event ID**: {res.audit_event_id}",
                f"- **Evaluation Passed**: {res.evaluation.passed if res.evaluation else 'N/A'}",
            ]
            summary_text = "\n".join(output_lines)
            if parsed.output:
                parsed.output.parent.mkdir(parents=True, exist_ok=True)
                parsed.output.write_text(summary_text, encoding="utf-8")
                print(f"AI feature report written to {parsed.output}")
            else:
                print(summary_text)
            return 0
        except (TargetNotAuthorizedError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if parsed.command == "evaluate-ml-approach":
        advisor = AIFeatureAdvisor()
        decision = advisor.evaluate_approach(
            description=parsed.description,
            recipe=RecipeType(parsed.recipe),
            latency_budget_ms=parsed.latency_budget_ms,
            sample_count=parsed.sample_count,
        )
        print(f"Recommended Approach: {decision.approach.value}")
        print(f"Model: {decision.recommended_model} ({decision.model_openness.value})")
        print(f"Rationale: {decision.rationale}")
        print(f"Estimated Cost: ${decision.estimated_cost_usd_per_1k_calls:.4f}/1k calls")
        print(f"Estimated Latency: ~{decision.estimated_latency_ms}ms")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
