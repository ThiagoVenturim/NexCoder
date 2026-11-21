"""Offline unit and integration tests for data engineering pipelines, ETL/ELT,
schema quality contracts, storage modeling, DAG orchestration, and observability (Issue #83).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from nexcoder_agents.catalog.registry import AgentCatalog
from nexcoder_agents.catalog.skills import SkillCatalog
from nexcoder_agents.cli import main
from nexcoder_agents.data_engineering import (
    DataEngineeringAdvisor,
    IngestionMode,
    OrchestratorStyle,
    PipelineParadigm,
    StorageEngineType,
    WorkloadProfile,
)
from nexcoder_agents.engine.models import ApprovalStatus
from nexcoder_agents.engine.pipelines import build_pipeline, get_pipeline_template
from nexcoder_core.config import NexcoderConfig
from nexcoder_core.llm.fake import FakeChatModel
from nexcoder_core.llm.registry import get_chat_model


def test_data_engineering_skills_and_persona_catalog() -> None:
    skills = SkillCatalog.default()
    expected_slugs = [
        "etl-pipeline-design",
        "dimensional-modeling",
        "query-optimization",
        "data-quality-contracts",
        "data-observability",
    ]
    for slug in expected_slugs:
        skill = skills.get(slug)
        assert skill is not None, f"Expected data skill '{slug}' in default catalog"
        assert skill.description
        assert skill.content

    agents = AgentCatalog.default()
    de = agents.get_or_raise("data-engineer")
    assert de.sector == "data-ai"
    for slug in expected_slugs:
        assert slug in de.skills


def test_storage_modeling_and_antipattern_detection() -> None:
    cfg = NexcoderConfig(preset="offline")
    advisor = DataEngineeringAdvisor(config=cfg)

    # 1. Columnar OLAP with modeling anti-patterns
    olap_profile = WorkloadProfile(
        description="Analytical customer revenue mart with daily aggregations",
        daily_volume_gb=120.0,
        access_pattern="olap",
        proposed_schema_notes=(
            "Uses EAV entity_attribute_value table, SELECT * FROM raw_json, "
            "no partition key, without primary key"
        ),
    )
    olap_assessment = advisor.assess_storage_modeling(olap_profile)
    assert olap_assessment.recommended_primary == StorageEngineType.COLUMNAR
    assert len(olap_assessment.trade_offs) == 5
    codes = {ap.code for ap in olap_assessment.anti_patterns}
    assert "EAV_IN_ANALYTICS" in codes
    assert "UNINDEXED_JSON_BLOB" in codes
    assert "UNBOUNDED_SELECT_STAR" in codes
    assert "MISSING_PRIMARY_KEY" in codes
    assert "MISSING_PARTITION_KEY" in codes

    # 2. Relational OLTP
    oltp_assessment = advisor.assess_storage_modeling(
        WorkloadProfile(description="Transactional billing ledger", access_pattern="oltp", daily_volume_gb=5.0)
    )
    assert oltp_assessment.recommended_primary == StorageEngineType.RELATIONAL

    # 3. Key-Value low-latency lookup
    kv_assessment = advisor.assess_storage_modeling(
        WorkloadProfile(
            description="Session deduplication cache",
            access_pattern="point_lookup",
            sub_millisecond_latency=True,
        )
    )
    assert kv_assessment.recommended_primary == StorageEngineType.KEY_VALUE

    # 4. Vector semantic search
    vec_assessment = advisor.assess_storage_modeling(
        WorkloadProfile(
            description="RAG document embeddings similarity index",
            access_pattern="semantic_search",
            has_embeddings=True,
        )
    )
    assert vec_assessment.recommended_primary == StorageEngineType.VECTOR

    # 5. Lakehouse high-volume multi-modal
    lh_assessment = advisor.assess_storage_modeling(
        WorkloadProfile(
            description="Multi-terabyte medallion lakehouse",
            access_pattern="hybrid_lakehouse",
            daily_volume_gb=800.0,
        )
    )
    assert lh_assessment.recommended_primary == StorageEngineType.LAKEHOUSE


def test_end_to_end_offline_pipeline_and_sqlite_materialization(tmp_path: Path) -> None:
    cfg = NexcoderConfig(preset="offline")
    advisor = DataEngineeringAdvisor(config=cfg)

    ws_dir = tmp_path / "warehouse"
    result = advisor.run_pipeline_from_description(
        "Ingest batch e-commerce orders, validate Silver schema contracts, and build Gold customer revenue mart.",
        pipeline_name="orders_medallion",
        ingestion_mode=IngestionMode.BATCH,
        paradigm=PipelineParadigm.ELT,
        workspace_dir=ws_dir,
    )

    # 1. Ingestion & Transformation counts (8 raw synthetic records: 5 valid + 3 dirty quarantined)
    assert result.raw_records_ingested == 8
    assert result.silver_records_cleaned == 5
    assert result.quarantined_records_count == 3
    assert len(result.gold_aggregates) == 3

    # 2. Bronze vs Silver quality reports
    assert result.raw_quality_report.passed is False
    assert result.raw_quality_report.rejected_row_count == 3
    assert result.silver_quality_report.passed is True
    assert result.silver_quality_report.quality_score == 100.0
    assert result.silver_quality_report.rejected_row_count == 0

    # 3. Four-pillar observability (freshness, volume, nulls, drift)
    assert result.observability.overall_healthy is True
    assert result.observability.freshness_passed is True
    assert result.observability.volume_passed is True
    assert result.observability.nulls_passed is True
    assert result.observability.drift_passed is True
    assert result.observability.anomalies == []

    # 4. Catalog & lineage graph
    assert len(result.catalog.entries) == 3
    assert len(result.catalog.lineage) == 2
    mermaid = result.catalog.to_mermaid()
    assert "flowchart LR" in mermaid
    assert "orders_medallion_bronze" in mermaid
    assert "orders_medallion_gold_customer_revenue" in mermaid

    # 5. Orchestration artifacts (Airflow, Dagster, dbt) verified with nexcoder-code-intel AST parser
    styles = {a.style: a for a in result.orchestration_artifacts}
    assert set(styles.keys()) == {
        OrchestratorStyle.AIRFLOW,
        OrchestratorStyle.DAGSTER,
        OrchestratorStyle.DBT,
    }
    for art in result.orchestration_artifacts:
        assert art.ast_valid is True
        assert art.parsed_symbol_count >= 1
        assert art.companion_test_code

    # 6. Control plane governance (CostTracker, BudgetManager, AppendOnlyAuditLog)
    assert result.governance.budget_within_limit is True
    assert result.governance.total_cost_usd > 0
    assert result.governance.audit_events_recorded == 5
    assert result.governance.audit_chain_verified is True

    # 7. SQLite materialization & generated files
    assert result.sqlite_db_path is not None
    db_file = Path(result.sqlite_db_path)
    assert db_file.is_file()
    assert (ws_dir / "orders_medallion_airflow.py").is_file()
    assert (ws_dir / "orders_medallion_dagster.py").is_file()
    assert (ws_dir / "orders_medallion_dbt.sql").is_file()

    conn = sqlite3.connect(str(db_file))
    try:
        bronze_cnt = conn.execute("SELECT COUNT(*) FROM bronze_raw").fetchone()[0]
        silver_cnt = conn.execute("SELECT COUNT(*) FROM silver_orders").fetchone()[0]
        quar_cnt = conn.execute("SELECT COUNT(*) FROM quarantined_records").fetchone()[0]
        gold_cnt = conn.execute("SELECT COUNT(*) FROM gold_customer_revenue").fetchone()[0]
    finally:
        conn.close()

    assert bronze_cnt == 8
    assert silver_cnt == 5
    assert quar_cnt == 3
    assert gold_cnt == 3

    md = result.to_markdown()
    assert "# Data Engineering Pipeline Report: orders_medallion" in md
    assert "## 3. Data Observability (Freshness, Volume, Nulls, Drift)" in md


def test_observability_anomaly_detection() -> None:
    ref_time = datetime(2026, 11, 9, 12, 0, 0, tzinfo=UTC)
    advisor = DataEngineeringAdvisor(reference_time=ref_time)
    contract = advisor.default_order_contract("orders_stale")

    baseline = [
        {
            "order_id": "ORD-1",
            "customer_id": "C1",
            "amount": 100.0,
            "currency": "BRL",
            "status": "completed",
            "event_timestamp": (ref_time - timedelta(hours=1)).isoformat(),
        }
    ]
    # Stale timestamp (10 hours old), high null rate, unexpected extra column, and huge amount shift
    degraded_batch = [
        {
            "order_id": "ORD-2",
            "customer_id": None,
            "amount": 5000.0,
            "currency": "BRL",
            "status": "completed",
            "event_timestamp": (ref_time - timedelta(hours=10)).isoformat(),
            "unexpected_new_col": "drift_val",
        }
    ]

    obs = advisor.evaluate_observability(
        "orders_stale",
        degraded_batch,
        contract,
        baseline_records=baseline,
        max_staleness_minutes=60.0,
        min_expected_rows=5,
        max_null_rate_threshold=0.05,
        max_drift_threshold=0.25,
    )

    assert obs.overall_healthy is False
    assert obs.freshness_passed is False
    assert obs.volume_passed is False
    assert obs.nulls_passed is False
    assert obs.drift_passed is False
    assert "customer_id" in obs.high_null_columns
    assert "unexpected_new_col" in obs.schema_drift_added
    assert obs.numeric_drift_score > 1.0
    assert len(obs.anomalies) >= 4


def test_data_engineering_pipeline_template_execution(tmp_path: Path) -> None:
    tmpl = get_pipeline_template("data-engineering-pipeline")
    assert tmpl.category == "data"
    assert "pipeline_name" in tmpl.required_inputs

    cfg = NexcoderConfig(preset="offline")
    fake_llm = FakeChatModel(
        responses=[
            "Data architecture verified: Columnar Silver store with 100% schema contract compliance.",
        ]
    )
    _ = get_chat_model("medium", config=cfg, tracing=False)

    pipeline = build_pipeline("data-engineering-pipeline", model=fake_llm)
    res = pipeline.run(
        inputs={
            "pipeline_name": "streaming_orders_elt",
            "pipeline_description": "Stream order events into Silver columnar store with quality gates",
            "ingestion_mode": "stream",
            "paradigm": "elt",
            "workspace_dir": str(tmp_path / "pipe_ws"),
        },
        dry_run=True,
    )

    assert res.status == "completed"
    assert res.approval is not None
    assert res.approval.status == ApprovalStatus.DRY_RUN
    assert res.data["silver_quality_report"]["passed"] is True
    assert res.data["observability"]["overall_healthy"] is True
    assert res.data["governance"]["audit_chain_verified"] is True


def test_cli_run_data_pipeline_and_example(tmp_path: Path, capsys) -> None:
    out_report = tmp_path / "cli_data_report.md"
    ws_dir = tmp_path / "cli_ws"
    code = main(
        [
            "run-data-pipeline",
            "Ingest orders and validate quality contracts",
            "--name",
            "cli_orders_pipeline",
            "--mode",
            "stream",
            "--paradigm",
            "etl",
            "--workspace-dir",
            str(ws_dir),
            "--output",
            str(out_report),
        ]
    )
    assert code == 0
    assert out_report.is_file()
    assert (ws_dir / "cli_orders_pipeline.sqlite").is_file()
    content = out_report.read_text(encoding="utf-8")
    assert "cli_orders_pipeline" in content
    assert "Silver (Post-Transformation) Quality Score" in content
    _ = capsys.readouterr()


def test_runnable_data_pipeline_example_script(tmp_path: Path) -> None:
    import importlib.util

    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    script_path = repo_root / "examples" / "data_pipeline" / "run_data_pipeline.py"
    assert script_path.is_file()

    spec = importlib.util.spec_from_file_location("run_data_pipeline", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    out = module.run_data_pipeline_example(output_dir=tmp_path / "example_out")
    assert out["status"] == "success"
    assert out["report_path"].is_file()
    assert out["sqlite_db_path"].is_file()
    assert out["result"].silver_quality_report.passed is True
    assert out["pipeline_run"].status == "completed"

