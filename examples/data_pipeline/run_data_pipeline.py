"""End-to-end offline data engineering pipeline example for nexcoder (Issue #83).

Demonstrates from a natural-language description how nexcoder generates and runs
an offline Medallion data pipeline over synthetic e-commerce order events:
1. Ingestion (Bronze): batch or stream landing with ingestion metadata
2. Transformation (Silver & Gold): deduplication, schema casting, quarantine of dirty rows, and customer revenue rollups
3. Data Quality & Schema Contracts: primary-key uniqueness, not-null, dtype, range, and domain assertions
4. Data Observability: freshness SLA, row-volume bounds, null rates, and statistical/schema drift
5. Storage Modeling & Anti-Pattern Review: relational, columnar, key-value, vector, and lakehouse fit scoring
6. Orchestration Generation: AST-verified Airflow DAG, Dagster assets, and dbt SQL model
7. Control Plane Governance: offline usage metering, budget policy enforcement, and hash-chained audit trail
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from nexcoder_agents.data_engineering import (
    DataEngineeringAdvisor,
    IngestionMode,
    PipelineParadigm,
)
from nexcoder_agents.engine.pipelines import build_pipeline
from nexcoder_core.config import NexcoderConfig
from nexcoder_core.llm.registry import get_chat_model


def run_data_pipeline_example(output_dir: Path | str | None = None) -> dict[str, Any]:
    """Execute the end-to-end offline data engineering pipeline and materialize artifacts."""
    base_dir = Path(__file__).parent.resolve()
    out_dir = Path(output_dir).resolve() if output_dir else base_dir / ".data_pipeline_artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = NexcoderConfig(preset="offline")
    offline_model = get_chat_model("medium", config=cfg, tracing=False)

    description = (
        "Ingest batch and streaming e-commerce orders into a Lakehouse Bronze zone, "
        "deduplicate and enforce schema contracts into a Columnar Silver table, "
        "quarantine invalid records, and compute Gold customer revenue aggregates."
    )

    advisor = DataEngineeringAdvisor(config=cfg)
    result = advisor.run_pipeline_from_description(
        description=description,
        pipeline_name="commerce_orders_medallion",
        ingestion_mode=IngestionMode.BATCH,
        paradigm=PipelineParadigm.ELT,
        workspace_dir=out_dir,
    )

    report_path = out_dir / "data_pipeline_report.md"
    report_path.write_text(result.to_markdown(), encoding="utf-8")

    # Also run the multi-agent governance pipeline (Validator -> DataEngineeringBlock -> Prompt -> Committee -> Gate)
    pipeline = build_pipeline("data-engineering-pipeline", model=offline_model)
    pipeline_run = pipeline.run(
        inputs={
            "pipeline_name": "commerce_orders_medallion",
            "pipeline_description": description,
            "ingestion_mode": "batch",
            "paradigm": "elt",
            "workspace_dir": str(out_dir),
        },
        dry_run=True,
    )

    pipeline_json_path = out_dir / "pipeline_governance_run.json"
    pipeline_json_path.write_text(pipeline_run.model_dump_json(indent=2), encoding="utf-8")

    print("======================================================================")
    print("nexcoder Offline Data Engineering Pipeline (Bronze -> Silver -> Gold)")
    print("======================================================================")
    print(f"Pipeline Name:          {result.pipeline_name}")
    print(f"Raw Records (Bronze):   {result.raw_records_ingested}")
    print(f"Valid Records (Silver): {result.silver_records_cleaned}")
    print(f"Quarantined Records:    {result.quarantined_records_count}")
    print(f"Gold Customer Rollups:  {len(result.gold_aggregates)}")
    print(
        f"Bronze Quality Score:   {result.raw_quality_report.quality_score:.1f}/100 "
        f"(Passed: {result.raw_quality_report.passed})"
    )
    print(
        f"Silver Quality Score:   {result.silver_quality_report.quality_score:.1f}/100 "
        f"(Passed: {result.silver_quality_report.passed})"
    )
    print(f"Observability Healthy:  {result.observability.overall_healthy}")
    print(f"Primary Storage Store:  {result.storage_modeling.recommended_primary.value}")
    print(
        f"Audit Chain Verified:   {result.governance.audit_chain_verified} "
        f"({result.governance.audit_events_recorded} events)"
    )
    print(f"Report Written To:      {report_path}")
    print("======================================================================")

    return {
        "status": "success",
        "result": result,
        "pipeline_run": pipeline_run,
        "report_path": report_path,
        "sqlite_db_path": Path(result.sqlite_db_path) if result.sqlite_db_path else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run nexcoder offline data engineering pipeline example.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to write SQLite warehouse, generated DAGs, and Markdown report.",
    )
    args = parser.parse_args()
    run_data_pipeline_example(output_dir=args.output_dir)


if __name__ == "__main__":
    main()
