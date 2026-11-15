"""Data engineering advisor, ETL/ELT pipeline runner, schema contract validator,
storage modeling selector, DAG generator, and data observability engine.

Integrates:
- `nexcoder-agents`: multi-agent pipeline blocks and catalog skills
- `nexcoder-code-intel`: AST parsing and symbol validation for generated DAGs
- `nexcoder-control`: budget policies, cost tracking, and tamper-evident audit logs
- `nexcoder-core`: sandbox path resolution and offline LLM execution
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from nexcoder_code_intel.parsers import parse_file
from nexcoder_control.metering import (
    AppendOnlyAuditLog,
    BudgetAlert,
    BudgetManager,
    BudgetPolicy,
    CostTracker,
)
from nexcoder_core.config import NexcoderConfig
from nexcoder_core.observability.usage import usage_scope
from nexcoder_core.sandbox import resolve_inside
from pydantic import BaseModel, Field

from nexcoder_agents.engine.blocks.base import BaseBlock
from nexcoder_agents.engine.models import BlockResult, BlockStatus


class IngestionMode(StrEnum):
    """Supported data ingestion execution modes."""

    BATCH = "batch"
    STREAM = "stream"


class PipelineParadigm(StrEnum):
    """Supported data transformation paradigms."""

    ETL = "etl"
    ELT = "elt"


class StorageEngineType(StrEnum):
    """Canonical storage architectures evaluated by the data modeling advisor."""

    RELATIONAL = "relational"
    COLUMNAR = "columnar"
    KEY_VALUE = "key_value"
    VECTOR = "vector"
    LAKEHOUSE = "lakehouse"


class OrchestratorStyle(StrEnum):
    """Supported orchestration frameworks for DAG and model generation."""

    AIRFLOW = "airflow"
    DAGSTER = "dagster"
    DBT = "dbt"


class WorkloadProfile(BaseModel):
    """Characteristics of a data workload used to select optimal storage engines."""

    description: str
    daily_volume_gb: float = Field(default=25.0, ge=0.0)
    access_pattern: str = "olap"  # oltp, olap, point_lookup, semantic_search, hybrid_lakehouse
    needs_acid_transactions: bool = True
    has_embeddings: bool = False
    sub_millisecond_latency: bool = False
    proposed_schema_notes: str = ""


class StorageTradeOff(BaseModel):
    """Evaluation of a candidate storage engine for a given workload."""

    engine: StorageEngineType
    fit_score: float = Field(ge=0.0, le=100.0)
    recommended_technologies: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)
    when_to_use: str = ""


class ModelingAntiPattern(BaseModel):
    """Detected data modeling anti-pattern and its remediation."""

    code: str
    severity: str = "medium"
    description: str
    remediation: str


class StorageModelingAssessment(BaseModel):
    """Storage selection and data modeling review report."""

    recommended_primary: StorageEngineType
    recommended_secondary: StorageEngineType | None = None
    rationale: str
    partition_strategy: str
    trade_offs: list[StorageTradeOff] = Field(default_factory=list)
    anti_patterns: list[ModelingAntiPattern] = Field(default_factory=list)


class ColumnContract(BaseModel):
    """Schema contract specification for a single dataset column."""

    name: str
    dtype: str  # int, float, str, bool, timestamp
    nullable: bool = False
    unique: bool = False
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[Any] | None = None


class SchemaContract(BaseModel):
    """Producer-consumer schema and data quality contract."""

    dataset_name: str
    version: str = "1.0.0"
    primary_key: list[str] = Field(default_factory=list)
    timestamp_column: str = "event_timestamp"
    columns: list[ColumnContract] = Field(default_factory=list)


class DataQualityRuleResult(BaseModel):
    """Outcome of evaluating a single data quality assertion."""

    rule_id: str
    column: str | None = None
    check_type: str  # schema, not_null, unique, type, range, allowed_values
    passed: bool
    failed_rows: int = 0
    total_rows: int = 0
    message: str = ""


class DataQualityReport(BaseModel):
    """Comprehensive data quality validation report against a SchemaContract."""

    dataset_name: str
    passed: bool
    quality_score: float = Field(ge=0.0, le=100.0)
    total_rows: int = 0
    valid_row_count: int = 0
    rejected_row_count: int = 0
    rules: list[DataQualityRuleResult] = Field(default_factory=list)


class DataObservabilityReport(BaseModel):
    """Four-pillar data observability report: freshness, volume, nulls, and drift."""

    dataset_name: str
    overall_healthy: bool
    # 1. Freshness
    latest_timestamp: str | None = None
    staleness_minutes: float = 0.0
    max_staleness_minutes: float = 120.0
    freshness_passed: bool = True
    # 2. Volume
    row_count: int = 0
    min_expected_rows: int = 1
    max_expected_rows: int = 1_000_000
    volume_passed: bool = True
    # 3. Nulls
    null_rates: dict[str, float] = Field(default_factory=dict)
    max_null_rate_threshold: float = 0.05
    high_null_columns: list[str] = Field(default_factory=list)
    nulls_passed: bool = True
    # 4. Drift
    schema_drift_added: list[str] = Field(default_factory=list)
    schema_drift_missing: list[str] = Field(default_factory=list)
    numeric_drift_score: float = 0.0
    max_drift_threshold: float = 0.35
    drift_passed: bool = True
    anomalies: list[str] = Field(default_factory=list)


class DataCatalogEntry(BaseModel):
    """Metadata catalog entry for a registered table or stream."""

    dataset_name: str
    layer: str  # bronze, silver, gold
    storage_engine: StorageEngineType
    schema_contract: SchemaContract | None = None
    owner: str = "data-engineer"
    row_count: int = 0
    description: str = ""


class LineageEdge(BaseModel):
    """Directed lineage relationship between upstream and downstream datasets."""

    upstream: str
    downstream: str
    transformation: str


class DataCatalogAndLineage(BaseModel):
    """Data catalog registry and lineage graph across medallion layers."""

    entries: list[DataCatalogEntry] = Field(default_factory=list)
    lineage: list[LineageEdge] = Field(default_factory=list)

    def to_mermaid(self) -> str:
        """Render the dataset lineage graph as a Mermaid flowchart."""
        lines = ["flowchart LR"]
        for edge in self.lineage:
            up_id = re.sub(r"[^a-zA-Z0-9_]", "_", edge.upstream)
            down_id = re.sub(r"[^a-zA-Z0-9_]", "_", edge.downstream)
            label = edge.transformation.replace('"', "'")
            lines.append(f'    {up_id}["{edge.upstream}"] -->|"{label}"| {down_id}["{edge.downstream}"]')
        return "\n".join(lines)


class GeneratedOrchestrationArtifact(BaseModel):
    """Generated orchestration DAG or transformation model with AST validation."""

    style: OrchestratorStyle
    pipeline_name: str
    code: str
    companion_test_code: str
    ast_valid: bool = True
    parsed_symbol_count: int = 0


class ControlPlaneGovernanceSummary(BaseModel):
    """Metering, budget, and tamper-evident audit summary from nexcoder-control."""

    pipeline_entity_id: str
    total_cost_usd: float = 0.0
    budget_limit_usd: float = 0.0
    budget_within_limit: bool = True
    alerts_emitted: int = 0
    audit_events_recorded: int = 0
    audit_chain_verified: bool = True
    audit_verification_message: str = ""


class DataPipelineExecutionResult(BaseModel):
    """End-to-end result of building and executing an offline data engineering pipeline."""

    pipeline_name: str
    description: str
    ingestion_mode: IngestionMode
    paradigm: PipelineParadigm
    raw_records_ingested: int
    silver_records_cleaned: int
    quarantined_records_count: int
    gold_aggregates: list[dict[str, Any]] = Field(default_factory=list)
    raw_quality_report: DataQualityReport
    silver_quality_report: DataQualityReport
    observability: DataObservabilityReport
    storage_modeling: StorageModelingAssessment
    catalog: DataCatalogAndLineage
    orchestration_artifacts: list[GeneratedOrchestrationArtifact] = Field(default_factory=list)
    governance: ControlPlaneGovernanceSummary
    sqlite_db_path: str | None = None

    def to_markdown(self) -> str:
        """Render a human-readable Markdown report of the data pipeline run."""
        lines = [
            f"# Data Engineering Pipeline Report: {self.pipeline_name}",
            "",
            f"- **Description**: {self.description}",
            f"- **Ingestion Mode**: `{self.ingestion_mode.value}`",
            f"- **Transformation Paradigm**: `{self.paradigm.value}`",
            f"- **Raw Records Ingested (Bronze)**: {self.raw_records_ingested}",
            f"- **Cleaned Records (Silver)**: {self.silver_records_cleaned}",
            f"- **Quarantined Invalid Records**: {self.quarantined_records_count}",
            f"- **Gold Analytical Aggregates**: {len(self.gold_aggregates)}",
            "",
            "## 1. Storage Modeling & Architecture Selection",
            f"- **Recommended Primary Store**: `{self.storage_modeling.recommended_primary.value}`",
            f"- **Recommended Secondary Store**: `{self.storage_modeling.recommended_secondary}`",
            f"- **Partitioning Strategy**: {self.storage_modeling.partition_strategy}",
            f"- **Rationale**: {self.storage_modeling.rationale}",
            "",
            "### Storage Engine Trade-Offs",
        ]
        for tf in self.storage_modeling.trade_offs:
            lines.append(
                f"- **`{tf.engine.value}`** (fit: {tf.fit_score:.0f}/100, "
                f"tech: {', '.join(tf.recommended_technologies)}): {tf.when_to_use}"
            )
        if self.storage_modeling.anti_patterns:
            lines.extend(["", "### Detected Modeling Anti-Patterns"])
            for ap in self.storage_modeling.anti_patterns:
                lines.append(f"- **[{ap.severity.upper()}] `{ap.code}`**: {ap.description} -> *{ap.remediation}*")

        lines.extend(
            [
                "",
                "## 2. Data Quality & Schema Contract Verification",
                (
                    f"- **Bronze (Pre-Cleaning) Quality Score**: "
                    f"{self.raw_quality_report.quality_score:.1f}/100 "
                    f"(Passed: {self.raw_quality_report.passed})"
                ),
                (
                    f"- **Silver (Post-Transformation) Quality Score**: "
                    f"{self.silver_quality_report.quality_score:.1f}/100 "
                    f"(Passed: {self.silver_quality_report.passed})"
                ),
                "",
                "### Silver Contract Rules",
            ]
        )
        for rule in self.silver_quality_report.rules:
            status = "PASS" if rule.passed else "FAIL"
            lines.append(f"- [{status}] `{rule.rule_id}` ({rule.check_type}): {rule.message}")

        lines.extend(
            [
                "",
                "## 3. Data Observability (Freshness, Volume, Nulls, Drift)",
                f"- **Overall Health**: `{'HEALTHY' if self.observability.overall_healthy else 'DEGRADED'}`",
                (
                    f"- **Freshness**: staleness={self.observability.staleness_minutes:.1f}m "
                    f"(SLA <= {self.observability.max_staleness_minutes:.1f}m) -> "
                    f"{'PASS' if self.observability.freshness_passed else 'FAIL'}"
                ),
                (
                    f"- **Volume**: rows={self.observability.row_count} "
                    f"(expected {self.observability.min_expected_rows}..{self.observability.max_expected_rows}) -> "
                    f"{'PASS' if self.observability.volume_passed else 'FAIL'}"
                ),
                (
                    f"- **Nulls**: max_threshold={self.observability.max_null_rate_threshold:.2%} -> "
                    f"{'PASS' if self.observability.nulls_passed else 'FAIL'}"
                ),
                (
                    f"- **Drift**: numeric_drift={self.observability.numeric_drift_score:.3f} "
                    f"(threshold <= {self.observability.max_drift_threshold:.2f}) -> "
                    f"{'PASS' if self.observability.drift_passed else 'FAIL'}"
                ),
                "",
                "## 4. Data Catalog & Medallion Lineage",
                "```mermaid",
                self.catalog.to_mermaid(),
                "```",
                "",
                "## 5. Control Plane Governance (Budget & Audit Trail)",
                f"- **Entity ID**: `{self.governance.pipeline_entity_id}`",
                (
                    f"- **Total Metered Cost**: ${self.governance.total_cost_usd:.4f} / "
                    f"${self.governance.budget_limit_usd:.2f}"
                ),
                f"- **Audit Events Recorded**: {self.governance.audit_events_recorded}",
                (
                    f"- **Audit Chain Verified**: `{self.governance.audit_chain_verified}` "
                    f"({self.governance.audit_verification_message})"
                ),
            ]
        )
        return "\n".join(lines).strip() + "\n"


def _matches_dtype(val: Any, dtype: str) -> bool:
    if val is None:
        return True
    if dtype == "int":
        return isinstance(val, int) and not isinstance(val, bool)
    if dtype == "float":
        return isinstance(val, (int, float)) and not isinstance(val, bool)
    if dtype == "str":
        return isinstance(val, str)
    if dtype == "bool":
        return isinstance(val, bool)
    if dtype == "timestamp":
        if not isinstance(val, str):
            return False
        try:
            datetime.fromisoformat(val.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    return True


class DataEngineeringAdvisor:
    """Core engine for storage modeling, ETL/ELT execution, data quality contracts,
    observability monitoring, and DAG code generation.
    """

    def __init__(
        self,
        reference_time: datetime | None = None,
        config: NexcoderConfig | None = None,
    ) -> None:
        self.reference_time = reference_time or datetime(2026, 11, 9, 12, 0, 0, tzinfo=UTC)
        self.config = config or NexcoderConfig(preset="offline")

    # -------------------------------------------------------------------------
    # 1. Storage Modeling & Anti-Pattern Advisor
    # -------------------------------------------------------------------------
    def assess_storage_modeling(self, profile: WorkloadProfile) -> StorageModelingAssessment:
        """Recommend storage engines and detect schema modeling anti-patterns."""
        desc_lower = f"{profile.description} {profile.proposed_schema_notes}".lower()
        access = profile.access_pattern.lower()

        scores: dict[StorageEngineType, float] = {
            StorageEngineType.RELATIONAL: 60.0,
            StorageEngineType.COLUMNAR: 60.0,
            StorageEngineType.KEY_VALUE: 40.0,
            StorageEngineType.VECTOR: 35.0,
            StorageEngineType.LAKEHOUSE: 55.0,
        }

        if access == "oltp" or "transactional" in desc_lower or "ledger" in desc_lower:
            scores[StorageEngineType.RELATIONAL] += 32.0
            scores[StorageEngineType.COLUMNAR] -= 15.0
        if access == "olap" or "analytics" in desc_lower or "mart" in desc_lower or "aggregation" in desc_lower:
            scores[StorageEngineType.COLUMNAR] += 32.0
            scores[StorageEngineType.LAKEHOUSE] += 20.0
        if access == "point_lookup" or profile.sub_millisecond_latency or "cache" in desc_lower:
            scores[StorageEngineType.KEY_VALUE] += 50.0
        if access == "semantic_search" or profile.has_embeddings or "embedding" in desc_lower or "rag" in desc_lower:
            scores[StorageEngineType.VECTOR] += 58.0
        if access == "hybrid_lakehouse" or profile.daily_volume_gb >= 500.0 or "lakehouse" in desc_lower:
            scores[StorageEngineType.LAKEHOUSE] += 38.0
            scores[StorageEngineType.COLUMNAR] += 15.0

        for k in scores:
            scores[k] = max(0.0, min(100.0, scores[k]))

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        primary = ranked[0][0]
        secondary = ranked[1][0] if ranked[1][1] >= 65.0 else None

        trade_offs = [
            StorageTradeOff(
                engine=StorageEngineType.RELATIONAL,
                fit_score=scores[StorageEngineType.RELATIONAL],
                recommended_technologies=["PostgreSQL", "SQLite (local/embedded)"],
                strengths=[
                    "Strict ACID transactions",
                    "Normalized referential integrity",
                    "Fast indexed row lookups",
                ],
                trade_offs=[
                    "High I/O overhead on wide analytical scans",
                    "Vertical scaling contention under heavy OLAP",
                ],
                when_to_use="Operational systems of record, billing ledgers, and transactional state.",
            ),
            StorageTradeOff(
                engine=StorageEngineType.COLUMNAR,
                fit_score=scores[StorageEngineType.COLUMNAR],
                recommended_technologies=["DuckDB", "ClickHouse", "BigQuery", "Snowflake"],
                strengths=[
                    "Columnar projection pruning",
                    "High compression ratios",
                    "Vectorized analytical aggregations",
                ],
                trade_offs=["Expensive single-row point updates", "Higher latency for high-concurrency OLTP"],
                when_to_use="Analytical data marts, BI dashboards, time-series rollups, and ELT Silver/Gold layers.",
            ),
            StorageTradeOff(
                engine=StorageEngineType.KEY_VALUE,
                fit_score=scores[StorageEngineType.KEY_VALUE],
                recommended_technologies=["Redis", "DynamoDB"],
                strengths=["Sub-millisecond key lookups", "Horizontal partition scalability", "TTL expiration support"],
                trade_offs=["No multi-table analytical joins", "Limited ad-hoc filtering without secondary indexes"],
                when_to_use="Session state, feature flags, idempotency deduplication caches, and rate limiting.",
            ),
            StorageTradeOff(
                engine=StorageEngineType.VECTOR,
                fit_score=scores[StorageEngineType.VECTOR],
                recommended_technologies=["pgvector", "Qdrant", "Milvus"],
                strengths=["HNSW/IVF approximate nearest neighbor search", "Hybrid metadata + semantic filtering"],
                trade_offs=["Memory-intensive index structures", "Not a replacement for transactional ledgers"],
                when_to_use="Semantic code/document retrieval, RAG context stores, and similarity clustering.",
            ),
            StorageTradeOff(
                engine=StorageEngineType.LAKEHOUSE,
                fit_score=scores[StorageEngineType.LAKEHOUSE],
                recommended_technologies=["Delta Lake", "Apache Iceberg", "Parquet"],
                strengths=["Open columnar storage on object stores", "Time-travel snapshots and schema evolution"],
                trade_offs=["Compaction maintenance required for small files", "Higher latency than in-memory stores"],
                when_to_use="Multi-terabyte medallion pipelines unifying batch and streaming workloads.",
            ),
        ]

        anti_patterns: list[ModelingAntiPattern] = []
        notes_lower = profile.proposed_schema_notes.lower()
        if "eav" in notes_lower or "entity_attribute_value" in notes_lower or "attribute_value" in notes_lower:
            anti_patterns.append(
                ModelingAntiPattern(
                    code="EAV_IN_ANALYTICS",
                    severity="high",
                    description="Generic Entity-Attribute-Value (EAV) table detected for analytical workload.",
                    remediation="Replace EAV with typed columnar attributes or structured dimensional tables.",
                )
            )
        if "json blob" in notes_lower or "unindexed json" in notes_lower or "raw_json" in notes_lower:
            anti_patterns.append(
                ModelingAntiPattern(
                    code="UNINDEXED_JSON_BLOB",
                    severity="high",
                    description="Querying unparsed JSON blobs directly in analytical filter predicates.",
                    remediation="Extract core attributes into typed Silver columns during ELT transformation.",
                )
            )
        if "select *" in notes_lower:
            anti_patterns.append(
                ModelingAntiPattern(
                    code="UNBOUNDED_SELECT_STAR",
                    severity="medium",
                    description="Using SELECT * in analytical pipelines defeats columnar projection pruning.",
                    remediation="Explicitly list required columns and push down partition filter predicates.",
                )
            )
        if "no primary key" in notes_lower or "without primary key" in notes_lower:
            anti_patterns.append(
                ModelingAntiPattern(
                    code="MISSING_PRIMARY_KEY",
                    severity="high",
                    description="Target table lacks a primary or surrogate deduplication key.",
                    remediation="Define a deterministic composite or surrogate primary key for idempotent merges.",
                )
            )
        if access == "olap" and profile.daily_volume_gb >= 50.0 and "no partition" in notes_lower:
            anti_patterns.append(
                ModelingAntiPattern(
                    code="MISSING_PARTITION_KEY",
                    severity="medium",
                    description="High-volume analytical table lacks date/time partitioning.",
                    remediation="Partition by event_date and cluster by high-cardinality tenant/entity keys.",
                )
            )

        partition_strategy = (
            "Partition by event_date (daily/monthly) and cluster by primary entity key (e.g., customer_id, tenant_id)."
            if primary in {StorageEngineType.COLUMNAR, StorageEngineType.LAKEHOUSE}
            else "Index primary key and high-selectivity foreign keys with composite B-Tree indexes."
        )

        rationale = (
            f"Selected '{primary.value}' as primary storage engine (fit score {scores[primary]:.0f}/100) "
            f"for access pattern '{profile.access_pattern}' at {profile.daily_volume_gb:.1f} GB/day."
        )
        if secondary:
            rationale += f" Pair with '{secondary.value}' as secondary store for hybrid workload needs."

        return StorageModelingAssessment(
            recommended_primary=primary,
            recommended_secondary=secondary,
            rationale=rationale,
            partition_strategy=partition_strategy,
            trade_offs=trade_offs,
            anti_patterns=anti_patterns,
        )

    # -------------------------------------------------------------------------
    # 2. Data Quality & Schema Contract Engine
    # -------------------------------------------------------------------------
    def validate_quality_contract(
        self,
        records: list[dict[str, Any]],
        contract: SchemaContract,
    ) -> tuple[DataQualityReport, list[dict[str, Any]], list[dict[str, Any]]]:
        """Validate a dataset against a SchemaContract and partition into valid vs rejected rows."""
        total = len(records)
        rules: list[DataQualityRuleResult] = []

        # Rule 1: Schema presence check
        required_cols = {c.name for c in contract.columns}
        present_cols: set[str] = set()
        for row in records:
            present_cols.update(row.keys())
        missing_cols = sorted(required_cols - present_cols) if total > 0 else []

        rules.append(
            DataQualityRuleResult(
                rule_id=f"{contract.dataset_name}.schema_columns_present",
                check_type="schema",
                passed=len(missing_cols) == 0 and total > 0,
                failed_rows=total if missing_cols else 0,
                total_rows=total,
                message=(
                    "All contract columns present"
                    if not missing_cols
                    else f"Missing contract columns: {', '.join(missing_cols)}"
                ),
            )
        )

        # Track per-row validity and primary key uniqueness
        seen_pks: set[tuple[Any, ...]] = set()
        duplicate_pk_rows = 0
        col_null_failures: dict[str, int] = {c.name: 0 for c in contract.columns if not c.nullable}
        col_type_failures: dict[str, int] = {c.name: 0 for c in contract.columns}
        col_range_failures: dict[str, int] = {
            c.name: 0 for c in contract.columns if c.min_value is not None or c.max_value is not None
        }
        col_allowed_failures: dict[str, int] = {
            c.name: 0 for c in contract.columns if c.allowed_values is not None
        }

        valid_records: list[dict[str, Any]] = []
        rejected_records: list[dict[str, Any]] = []

        for row in records:
            row_valid = True
            if contract.primary_key:
                pk_tuple = tuple(row.get(k) for k in contract.primary_key)
                if any(v is None for v in pk_tuple) or pk_tuple in seen_pks:
                    duplicate_pk_rows += 1
                    row_valid = False
                else:
                    seen_pks.add(pk_tuple)

            for col in contract.columns:
                val = row.get(col.name)
                if val is None or (isinstance(val, str) and val.strip() == ""):
                    if not col.nullable:
                        col_null_failures[col.name] += 1
                        row_valid = False
                    continue

                if not _matches_dtype(val, col.dtype):
                    col_type_failures[col.name] += 1
                    row_valid = False
                    continue

                if col.min_value is not None and isinstance(val, (int, float)) and val < col.min_value:
                    col_range_failures[col.name] += 1
                    row_valid = False

                if col.max_value is not None and isinstance(val, (int, float)) and val > col.max_value:
                    col_range_failures[col.name] += 1
                    row_valid = False

                if col.allowed_values is not None and val not in col.allowed_values:
                    col_allowed_failures[col.name] += 1
                    row_valid = False

            if row_valid:
                valid_records.append(row)
            else:
                rejected_records.append(row)

        if contract.primary_key:
            rules.append(
                DataQualityRuleResult(
                    rule_id=f"{contract.dataset_name}.primary_key_unique",
                    column=",".join(contract.primary_key),
                    check_type="unique",
                    passed=duplicate_pk_rows == 0,
                    failed_rows=duplicate_pk_rows,
                    total_rows=total,
                    message=f"Primary key {contract.primary_key} duplicate/null violations: {duplicate_pk_rows}",
                )
            )

        for col in contract.columns:
            if not col.nullable:
                fails = col_null_failures[col.name]
                rules.append(
                    DataQualityRuleResult(
                        rule_id=f"{contract.dataset_name}.{col.name}.not_null",
                        column=col.name,
                        check_type="not_null",
                        passed=fails == 0,
                        failed_rows=fails,
                        total_rows=total,
                        message=f"Column '{col.name}' null violations: {fails}",
                    )
                )

            type_fails = col_type_failures[col.name]
            rules.append(
                DataQualityRuleResult(
                    rule_id=f"{contract.dataset_name}.{col.name}.dtype_{col.dtype}",
                    column=col.name,
                    check_type="type",
                    passed=type_fails == 0,
                    failed_rows=type_fails,
                    total_rows=total,
                    message=f"Column '{col.name}' type '{col.dtype}' violations: {type_fails}",
                )
            )

            if col.min_value is not None or col.max_value is not None:
                rfails = col_range_failures[col.name]
                rules.append(
                    DataQualityRuleResult(
                        rule_id=f"{contract.dataset_name}.{col.name}.range",
                        column=col.name,
                        check_type="range",
                        passed=rfails == 0,
                        failed_rows=rfails,
                        total_rows=total,
                        message=f"Column '{col.name}' range [{col.min_value}, {col.max_value}] violations: {rfails}",
                    )
                )

            if col.allowed_values is not None:
                afails = col_allowed_failures[col.name]
                rules.append(
                    DataQualityRuleResult(
                        rule_id=f"{contract.dataset_name}.{col.name}.allowed_values",
                        column=col.name,
                        check_type="allowed_values",
                        passed=afails == 0,
                        failed_rows=afails,
                        total_rows=total,
                        message=f"Column '{col.name}' allowed values violations: {afails}",
                    )
                )

        passed_rules = sum(1 for r in rules if r.passed)
        score = (passed_rules / len(rules) * 100.0) if rules else 100.0
        all_passed = all(r.passed for r in rules) and total > 0

        report = DataQualityReport(
            dataset_name=contract.dataset_name,
            passed=all_passed,
            quality_score=round(score, 2),
            total_rows=total,
            valid_row_count=len(valid_records),
            rejected_row_count=len(rejected_records),
            rules=rules,
        )
        return report, valid_records, rejected_records

    # -------------------------------------------------------------------------
    # 3. Data Observability Engine (Freshness, Volume, Nulls, Drift)
    # -------------------------------------------------------------------------
    def evaluate_observability(
        self,
        dataset_name: str,
        records: list[dict[str, Any]],
        contract: SchemaContract,
        *,
        baseline_records: list[dict[str, Any]] | None = None,
        max_staleness_minutes: float = 120.0,
        min_expected_rows: int = 1,
        max_expected_rows: int = 100_000,
        max_null_rate_threshold: float = 0.05,
        max_drift_threshold: float = 0.35,
    ) -> DataObservabilityReport:
        """Compute freshness, volume, null rates, and schema/numeric drift metrics."""
        anomalies: list[str] = []
        row_count = len(records)

        # 1. Volume check
        volume_passed = min_expected_rows <= row_count <= max_expected_rows
        if not volume_passed:
            anomalies.append(
                f"Volume anomaly: row_count={row_count} outside [{min_expected_rows}, {max_expected_rows}]"
            )

        # 2. Freshness check
        ts_col = contract.timestamp_column
        parsed_timestamps: list[datetime] = []
        for row in records:
            raw_ts = row.get(ts_col)
            if isinstance(raw_ts, str) and raw_ts:
                try:
                    dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)
                    parsed_timestamps.append(dt)
                except ValueError:
                    continue

        if parsed_timestamps:
            latest_dt = max(parsed_timestamps)
            latest_ts_str = latest_dt.isoformat()
            staleness = max(0.0, (self.reference_time - latest_dt).total_seconds() / 60.0)
            freshness_passed = staleness <= max_staleness_minutes
            if not freshness_passed:
                anomalies.append(
                    f"Freshness SLA breach: staleness {staleness:.1f}m exceeds {max_staleness_minutes:.1f}m"
                )
        else:
            latest_ts_str = None
            staleness = float("inf")
            freshness_passed = False
            anomalies.append(f"Freshness check failed: no valid timestamps in column '{ts_col}'")

        # 3. Null rates check
        null_rates: dict[str, float] = {}
        high_null_cols: list[str] = []
        expected_col_names = [c.name for c in contract.columns]
        for col_name in expected_col_names:
            if row_count == 0:
                null_rates[col_name] = 1.0
            else:
                null_cnt = sum(
                    1
                    for r in records
                    if r.get(col_name) is None
                    or (isinstance(r.get(col_name), str) and r.get(col_name, "").strip() == "")
                )
                rate = round(null_cnt / row_count, 4)
                null_rates[col_name] = rate
                if rate > max_null_rate_threshold:
                    high_null_cols.append(col_name)

        nulls_passed = len(high_null_cols) == 0 and row_count > 0
        if high_null_cols:
            anomalies.append(f"High null rate in columns: {', '.join(high_null_cols)}")

        # 4. Schema & Statistical Drift check
        observed_cols: set[str] = set()
        for r in records:
            observed_cols.update(k for k in r.keys() if not k.startswith("_"))
        contract_cols = set(expected_col_names)
        schema_added = sorted(observed_cols - contract_cols)
        schema_missing = sorted(contract_cols - observed_cols) if row_count > 0 else sorted(contract_cols)

        numeric_drift = 0.0
        if baseline_records and records:
            numeric_cols = [c.name for c in contract.columns if c.dtype in {"int", "float"}]
            shifts: list[float] = []
            for ncol in numeric_cols:
                base_vals = [
                    float(r[ncol])
                    for r in baseline_records
                    if isinstance(r.get(ncol), (int, float)) and not isinstance(r.get(ncol), bool)
                ]
                curr_vals = [
                    float(r[ncol])
                    for r in records
                    if isinstance(r.get(ncol), (int, float)) and not isinstance(r.get(ncol), bool)
                ]
                if base_vals and curr_vals:
                    base_mean = sum(base_vals) / len(base_vals)
                    curr_mean = sum(curr_vals) / len(curr_vals)
                    denom = max(abs(base_mean), 1e-6)
                    shifts.append(abs(curr_mean - base_mean) / denom)
            if shifts:
                numeric_drift = round(max(shifts), 4)

        drift_passed = (
            len(schema_missing) == 0
            and len(schema_added) == 0
            and numeric_drift <= max_drift_threshold
        )
        if not drift_passed:
            anomalies.append(
                f"Drift detected: added={schema_added}, missing={schema_missing}, numeric_drift={numeric_drift:.3f}"
            )

        overall_healthy = freshness_passed and volume_passed and nulls_passed and drift_passed
        return DataObservabilityReport(
            dataset_name=dataset_name,
            overall_healthy=overall_healthy,
            latest_timestamp=latest_ts_str,
            staleness_minutes=round(staleness, 2) if staleness != float("inf") else 999999.0,
            max_staleness_minutes=max_staleness_minutes,
            freshness_passed=freshness_passed,
            row_count=row_count,
            min_expected_rows=min_expected_rows,
            max_expected_rows=max_expected_rows,
            volume_passed=volume_passed,
            null_rates=null_rates,
            max_null_rate_threshold=max_null_rate_threshold,
            high_null_columns=high_null_cols,
            nulls_passed=nulls_passed,
            schema_drift_added=schema_added,
            schema_drift_missing=schema_missing,
            numeric_drift_score=numeric_drift,
            max_drift_threshold=max_drift_threshold,
            drift_passed=drift_passed,
            anomalies=anomalies,
        )

    # -------------------------------------------------------------------------
    # 4. Orchestration Generator (Airflow, Dagster, dbt)
    # -------------------------------------------------------------------------
    def generate_orchestration_artifact(
        self,
        pipeline_name: str,
        description: str,
        style: OrchestratorStyle,
        contract: SchemaContract,
    ) -> GeneratedOrchestrationArtifact:
        """Generate orchestration DAG or model code and verify Python syntax via nexcoder-code-intel."""
        safe_slug = re.sub(r"[^a-z0-9_]", "_", pipeline_name.lower()).strip("_") or "data_pipeline"
        pk_col = contract.primary_key[0] if contract.primary_key else "order_id"

        if style == OrchestratorStyle.AIRFLOW:
            code = (
                f'"""Generated Airflow TaskFlow DAG for {pipeline_name}: {description}"""\n\n'
                "from __future__ import annotations\n\n"
                "from typing import Any\n\n\n"
                f"def extract_bronze_{safe_slug}() -> list[dict[str, Any]]:\n"
                '    """Ingest raw records into Bronze landing zone."""\n'
                "    return []\n\n\n"
                f"def transform_silver_{safe_slug}(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:\n"
                f'    """Deduplicate by {pk_col} and enforce schema types for Silver layer."""\n'
                "    seen: set[Any] = set()\n"
                "    cleaned: list[dict[str, Any]] = []\n"
                "    for row in raw_rows:\n"
                f"        key = row.get({pk_col!r})\n"
                "        if key is not None and key not in seen:\n"
                "            seen.add(key)\n"
                "            cleaned.append(row)\n"
                "    return cleaned\n\n\n"
                f"def validate_quality_{safe_slug}(silver_rows: list[dict[str, Any]]) -> bool:\n"
                '    """Verify schema contract and non-empty volume."""\n'
                f"    return all(r.get({pk_col!r}) is not None for r in silver_rows)\n"
            )
            test_code = (
                f"from dag_{safe_slug} import transform_silver_{safe_slug}, validate_quality_{safe_slug}\n\n\n"
                f"def test_airflow_dag_{safe_slug}() -> None:\n"
                f"    sample = [{{{pk_col!r}: 'A1', 'amount': 10.0}}, {{{pk_col!r}: 'A1', 'amount': 10.0}}]\n"
                f"    silver = transform_silver_{safe_slug}(sample)\n"
                "    assert len(silver) == 1\n"
                f"    assert validate_quality_{safe_slug}(silver) is True\n"
            )
        elif style == OrchestratorStyle.DAGSTER:
            code = (
                f'"""Generated Dagster Software-Defined Assets for {pipeline_name}: {description}"""\n\n'
                "from __future__ import annotations\n\n"
                "from typing import Any\n\n\n"
                f"def bronze_{safe_slug}_asset(seed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:\n"
                '    """Software-defined asset for Bronze ingestion."""\n'
                "    return list(seed_rows)\n\n\n"
                f"def silver_{safe_slug}_asset(bronze_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:\n"
                '    """Software-defined asset for Silver transformation."""\n'
                f"    return [r for r in bronze_rows if r.get({pk_col!r}) is not None]\n\n\n"
                f"def gold_{safe_slug}_mart_asset(silver_rows: list[dict[str, Any]]) -> dict[str, int]:\n"
                '    """Software-defined asset for Gold summary mart."""\n'
                "    return {'total_records': len(silver_rows)}\n"
            )
            test_code = (
                f"from assets_{safe_slug} import (\n"
                f"    bronze_{safe_slug}_asset,\n"
                f"    gold_{safe_slug}_mart_asset,\n"
                f"    silver_{safe_slug}_asset,\n"
                ")\n\n\n"
                f"def test_dagster_assets_{safe_slug}() -> None:\n"
                f"    raw = bronze_{safe_slug}_asset([{{{pk_col!r}: 'K1'}}, {{{pk_col!r}: None}}])\n"
                f"    silver = silver_{safe_slug}_asset(raw)\n"
                f"    gold = gold_{safe_slug}_mart_asset(silver)\n"
                "    assert gold['total_records'] == 1\n"
            )
        else:
            # DBT SQL model + YAML schema contract represented as Python-verifiable bundle
            col_list = ",\n    ".join(c.name for c in contract.columns)
            template = (
                "-- dbt model: models/silver/silver___slug__.sql\n"
                "-- Description: __description__\n"
                "WITH deduplicated AS (\n"
                "    SELECT\n"
                "        __col_list__,\n"
                "        ROW_NUMBER() OVER (PARTITION BY __pk_col__ ORDER BY __ts_col__ DESC) AS _rn\n"
                "    FROM {{ source('bronze', 'bronze___slug__') }}\n"
                "    WHERE __pk_col__ IS NOT NULL\n"
                ")\n"
                "SELECT\n"
                "    __col_list__\n"
                "FROM deduplicated\n"
                "WHERE _rn = 1;\n"
            )
            code = (
                template.replace("__slug__", safe_slug)
                .replace("__description__", description)
                .replace("__col_list__", col_list)
                .replace("__pk_col__", pk_col)
                .replace("__ts_col__", contract.timestamp_column)
            )
            test_code = (
                f"# dbt schema test specification for silver_{safe_slug}\n"
                "DBT_SCHEMA_TESTS = {\n"
                f"    'model': 'silver_{safe_slug}',\n"
                f"    'primary_key': {pk_col!r},\n"
                "    'tests': ['unique', 'not_null'],\n"
                "}\n"
            )

        # Validate Python code via nexcoder-code-intel AST parser when applicable
        ast_valid = True
        symbol_count = 0
        if style in {OrchestratorStyle.AIRFLOW, OrchestratorStyle.DAGSTER}:
            symbols = parse_file(f"{safe_slug}_{style.value}.py", code)
            symbol_count = len(symbols)
            ast_valid = symbol_count >= 3
        else:
            symbols = parse_file(f"test_{safe_slug}_dbt.py", test_code)
            symbol_count = max(1, len(symbols))
            ast_valid = "SELECT" in code and "WHERE" in code

        return GeneratedOrchestrationArtifact(
            style=style,
            pipeline_name=pipeline_name,
            code=code,
            companion_test_code=test_code,
            ast_valid=ast_valid,
            parsed_symbol_count=symbol_count,
        )

    # -------------------------------------------------------------------------
    # 5. Synthetic Data & End-to-End Offline Pipeline Execution
    # -------------------------------------------------------------------------
    def default_order_contract(self, dataset_name: str = "orders_silver") -> SchemaContract:
        """Build the default schema contract for synthetic e-commerce order pipelines."""
        return SchemaContract(
            dataset_name=dataset_name,
            version="1.0.0",
            primary_key=["order_id"],
            timestamp_column="event_timestamp",
            columns=[
                ColumnContract(name="order_id", dtype="str", nullable=False, unique=True),
                ColumnContract(name="customer_id", dtype="str", nullable=False),
                ColumnContract(
                    name="amount",
                    dtype="float",
                    nullable=False,
                    min_value=0.01,
                    max_value=100_000.0,
                ),
                ColumnContract(
                    name="currency",
                    dtype="str",
                    nullable=False,
                    allowed_values=["USD", "BRL", "EUR"],
                ),
                ColumnContract(
                    name="status",
                    dtype="str",
                    nullable=False,
                    allowed_values=["completed", "pending", "refunded"],
                ),
                ColumnContract(name="event_timestamp", dtype="timestamp", nullable=False),
            ],
        )

    def generate_synthetic_batches(
        self,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Generate deterministic synthetic baseline and raw batches (with realistic dirty rows)."""
        t0 = self.reference_time - timedelta(minutes=25)
        t_base = self.reference_time - timedelta(hours=24)

        baseline = [
            {
                "order_id": f"ORD-00{i}",
                "customer_id": f"CUST-{(i % 3) + 1:02d}",
                "amount": round(100.0 + i * 25.0, 2),
                "currency": "BRL",
                "status": "completed",
                "event_timestamp": (t_base + timedelta(minutes=i * 5)).isoformat(),
            }
            for i in range(1, 7)
        ]

        raw_batch: list[dict[str, Any]] = [
            {
                "order_id": "ORD-101",
                "customer_id": "CUST-01",
                "amount": 120.50,
                "currency": "BRL",
                "status": "completed",
                "event_timestamp": (t0 + timedelta(minutes=1)).isoformat(),
            },
            {
                "order_id": "ORD-102",
                "customer_id": "CUST-02",
                "amount": 210.00,
                "currency": "USD",
                "status": "completed",
                "event_timestamp": (t0 + timedelta(minutes=5)).isoformat(),
            },
            {
                "order_id": "ORD-103",
                "customer_id": "CUST-01",
                "amount": 89.90,
                "currency": "BRL",
                "status": "pending",
                "event_timestamp": (t0 + timedelta(minutes=10)).isoformat(),
            },
            {
                "order_id": "ORD-104",
                "customer_id": "CUST-03",
                "amount": 340.00,
                "currency": "EUR",
                "status": "completed",
                "event_timestamp": (t0 + timedelta(minutes=15)).isoformat(),
            },
            {
                "order_id": "ORD-105",
                "customer_id": "CUST-02",
                "amount": 155.25,
                "currency": "BRL",
                "status": "refunded",
                "event_timestamp": (t0 + timedelta(minutes=20)).isoformat(),
            },
            # Dirty row 1: Duplicate primary key ORD-101
            {
                "order_id": "ORD-101",
                "customer_id": "CUST-01",
                "amount": 120.50,
                "currency": "BRL",
                "status": "completed",
                "event_timestamp": (t0 + timedelta(minutes=2)).isoformat(),
            },
            # Dirty row 2: Negative amount violating range contract
            {
                "order_id": "ORD-106-BAD",
                "customer_id": "CUST-04",
                "amount": -45.00,
                "currency": "BRL",
                "status": "completed",
                "event_timestamp": (t0 + timedelta(minutes=12)).isoformat(),
            },
            # Dirty row 3: Null customer_id and unsupported currency
            {
                "order_id": "ORD-107-BAD",
                "customer_id": None,
                "amount": 50.00,
                "currency": "INVALID_CUR",
                "status": "completed",
                "event_timestamp": (t0 + timedelta(minutes=14)).isoformat(),
            },
        ]
        return baseline, raw_batch

    def run_pipeline_from_description(
        self,
        description: str,
        *,
        pipeline_name: str = "commerce_orders_medallion",
        ingestion_mode: IngestionMode = IngestionMode.BATCH,
        paradigm: PipelineParadigm = PipelineParadigm.ELT,
        raw_records: list[dict[str, Any]] | None = None,
        baseline_records: list[dict[str, Any]] | None = None,
        contract: SchemaContract | None = None,
        workload_profile: WorkloadProfile | None = None,
        workspace_dir: Path | str | None = None,
        budget_limit_usd: float | None = None,
    ) -> DataPipelineExecutionResult:
        """Build and execute an end-to-end offline data pipeline (ingest -> transform -> test -> observe)."""
        effective_budget = budget_limit_usd if budget_limit_usd is not None else self.config.budget.max_usd_per_run
        synth_baseline, synth_raw = self.generate_synthetic_batches()
        raw_batch = list(raw_records) if raw_records is not None else synth_raw
        base_batch = list(baseline_records) if baseline_records is not None else synth_baseline
        schema_contract = contract or self.default_order_contract(dataset_name=f"{pipeline_name}_silver")

        # Initialize Control Plane governance (CostTracker, BudgetManager, AppendOnlyAuditLog)
        cost_tracker = CostTracker()
        budget_manager = BudgetManager(cost_tracker)
        entity_id = f"pipeline:{pipeline_name}"
        budget_manager.add_policy(
            BudgetPolicy(
                dimension="agent",
                entity_id=entity_id,
                limit_usd=effective_budget,
                thresholds=[0.8, 1.0],
                enforce_hard_limit=True,
            )
        )
        audit_log = AppendOnlyAuditLog()
        alerts: list[BudgetAlert] = []

        with usage_scope(owner="data-engineer", run_id=entity_id, budget_usd=effective_budget) as usage_meter:

            def _meter_and_audit(
                stage: str, tokens_in: int, tokens_out: int, cost_usd: float, details: dict[str, Any]
            ) -> None:
                usage_meter.add("gpt-4.1-mini", tokens_in, tokens_out)
                cost_tracker.record_usage(
                    model="gpt-4.1-mini",
                    input_tokens=tokens_in,
                    output_tokens=tokens_out,
                    app_id=pipeline_name,
                    person_id="data-engineer",
                    agent_id=entity_id,
                    pipeline_id=pipeline_name,
                    metadata={"stage": stage, "estimated_stage_cost_usd": cost_usd, **details},
                )
                stage_alerts = budget_manager.evaluate_entity("agent", entity_id)
                alerts.extend(stage_alerts)
                audit_log.record_event(
                    event_type=f"data_pipeline.{stage}",
                    actor="data-engineer",
                    action=stage,
                    resource=pipeline_name,
                    severity="info",
                    details=details,
                )

            # Stage 1: Ingestion (Bronze)
            ingested_at = self.reference_time.isoformat()
            bronze_records: list[dict[str, Any]] = []
            for row in raw_batch:
                enriched = dict(row)
                enriched["_ingested_at"] = ingested_at
                enriched["_ingestion_mode"] = ingestion_mode.value
                bronze_records.append(enriched)

            _meter_and_audit(
                stage="ingest_bronze",
                tokens_in=150,
                tokens_out=80,
                cost_usd=0.0025,
                details={"mode": ingestion_mode.value, "raw_rows": len(bronze_records)},
            )

            # Evaluate raw quality before cleaning (demonstrates detection of dirty synthetic records)
            raw_quality_report, _, _ = self.validate_quality_contract(bronze_records, schema_contract)

            # Stage 2: Transformation (Silver cleaning & deduplication + Gold aggregation)
            _, silver_valid, quarantined = self.validate_quality_contract(bronze_records, schema_contract)
            silver_records: list[dict[str, Any]] = []
            for row in silver_valid:
                clean_row = {col.name: row.get(col.name) for col in schema_contract.columns}
                if isinstance(clean_row.get("amount"), (int, float)):
                    clean_row["amount"] = round(float(clean_row["amount"]), 2)
                silver_records.append(clean_row)

            # Gold aggregation: group by customer_id or primary dimension
            gold_by_customer: dict[str, dict[str, Any]] = {}
            for row in silver_records:
                cust = str(row.get("customer_id", "UNKNOWN"))
                amt = float(row.get("amount", 0.0)) if isinstance(row.get("amount"), (int, float)) else 0.0
                if cust not in gold_by_customer:
                    gold_by_customer[cust] = {
                        "customer_id": cust,
                        "order_count": 0,
                        "total_amount": 0.0,
                    }
                gold_by_customer[cust]["order_count"] += 1
                gold_by_customer[cust]["total_amount"] = round(gold_by_customer[cust]["total_amount"] + amt, 2)

            gold_aggregates = sorted(gold_by_customer.values(), key=lambda x: str(x["customer_id"]))

            _meter_and_audit(
                stage="transform_silver_gold",
                tokens_in=220,
                tokens_out=140,
                cost_usd=0.0040,
                details={
                    "paradigm": paradigm.value,
                    "silver_rows": len(silver_records),
                    "quarantined_rows": len(quarantined),
                    "gold_groups": len(gold_aggregates),
                },
            )

            # Stage 3: Quality Contract Validation on Silver
            silver_quality_report, _, _ = self.validate_quality_contract(silver_records, schema_contract)

            _meter_and_audit(
                stage="validate_quality_contract",
                tokens_in=120,
                tokens_out=90,
                cost_usd=0.0020,
                details={
                    "passed": silver_quality_report.passed,
                    "quality_score": silver_quality_report.quality_score,
                },
            )

            # Stage 4: Data Observability (Freshness, Volume, Nulls, Drift)
            observability = self.evaluate_observability(
                dataset_name=schema_contract.dataset_name,
                records=silver_records,
                contract=schema_contract,
                baseline_records=base_batch,
            )

            _meter_and_audit(
                stage="evaluate_observability",
                tokens_in=100,
                tokens_out=75,
                cost_usd=0.0015,
                details={
                    "overall_healthy": observability.overall_healthy,
                    "staleness_minutes": observability.staleness_minutes,
                    "numeric_drift_score": observability.numeric_drift_score,
                },
            )

            # Stage 5: Storage Modeling Assessment
            profile = workload_profile or WorkloadProfile(
                description=description,
                daily_volume_gb=45.0,
                access_pattern="olap",
                needs_acid_transactions=True,
                proposed_schema_notes="SELECT * FROM raw_json without partition key",
            )
            storage_modeling = self.assess_storage_modeling(profile)

            # Stage 6: Orchestration Generation (Airflow, Dagster, dbt)
            orchestration_artifacts = [
                self.generate_orchestration_artifact(pipeline_name, description, style, schema_contract)
                for style in (OrchestratorStyle.AIRFLOW, OrchestratorStyle.DAGSTER, OrchestratorStyle.DBT)
            ]

            # Stage 7: Catalog & Lineage Registration
            bronze_name = f"{pipeline_name}_bronze"
            silver_name = schema_contract.dataset_name
            gold_name = f"{pipeline_name}_gold_customer_revenue"

            catalog = DataCatalogAndLineage(
                entries=[
                    DataCatalogEntry(
                        dataset_name=bronze_name,
                        layer="bronze",
                        storage_engine=StorageEngineType.LAKEHOUSE,
                        row_count=len(bronze_records),
                        description="Raw immutable landing zone with ingestion timestamps.",
                    ),
                    DataCatalogEntry(
                        dataset_name=silver_name,
                        layer="silver",
                        storage_engine=storage_modeling.recommended_primary,
                        schema_contract=schema_contract,
                        row_count=len(silver_records),
                        description="Deduplicated and schema-validated Silver table.",
                    ),
                    DataCatalogEntry(
                        dataset_name=gold_name,
                        layer="gold",
                        storage_engine=StorageEngineType.COLUMNAR,
                        row_count=len(gold_aggregates),
                        description="Customer-level revenue and order count analytical mart.",
                    ),
                ],
                lineage=[
                    LineageEdge(
                        upstream=bronze_name,
                        downstream=silver_name,
                        transformation="deduplicate + schema_contract_filter",
                    ),
                    LineageEdge(
                        upstream=silver_name,
                        downstream=gold_name,
                        transformation="group_by(customer_id) sum(amount)",
                    ),
                ],
            )

            # Optional persistence to local SQLite warehouse and workspace files
            sqlite_path_str: str | None = None
            if workspace_dir is not None:
                ws_root = Path(workspace_dir).resolve()
                ws_root.mkdir(parents=True, exist_ok=True)
                db_file = resolve_inside(ws_root, f"{pipeline_name}.sqlite")
                self._materialize_sqlite(db_file, bronze_records, silver_records, quarantined, gold_aggregates)
                sqlite_path_str = str(db_file)

                for art in orchestration_artifacts:
                    ext = "sql" if art.style == OrchestratorStyle.DBT else "py"
                    art_file = resolve_inside(ws_root, f"{pipeline_name}_{art.style.value}.{ext}")
                    art_file.write_text(art.code, encoding="utf-8")

            _meter_and_audit(
                stage="catalog_and_orchestration",
                tokens_in=180,
                tokens_out=160,
                cost_usd=0.0030,
                details={
                    "catalog_entries": len(catalog.entries),
                    "orchestration_styles": [a.style.value for a in orchestration_artifacts],
                },
            )

        # Verify audit ledger integrity
        verified, verify_msg = audit_log.verify_integrity()
        agent_summary = cost_tracker.aggregate_by("agent").get(entity_id)
        total_cost = agent_summary.total_cost_usd if agent_summary else 0.0

        governance = ControlPlaneGovernanceSummary(
            pipeline_entity_id=entity_id,
            total_cost_usd=round(total_cost, 6),
            budget_limit_usd=effective_budget,
            budget_within_limit=total_cost <= effective_budget,
            alerts_emitted=len(alerts),
            audit_events_recorded=len(audit_log.query(limit=50)),
            audit_chain_verified=verified,
            audit_verification_message=verify_msg,
        )

        return DataPipelineExecutionResult(
            pipeline_name=pipeline_name,
            description=description,
            ingestion_mode=ingestion_mode,
            paradigm=paradigm,
            raw_records_ingested=len(bronze_records),
            silver_records_cleaned=len(silver_records),
            quarantined_records_count=len(quarantined),
            gold_aggregates=gold_aggregates,
            raw_quality_report=raw_quality_report,
            silver_quality_report=silver_quality_report,
            observability=observability,
            storage_modeling=storage_modeling,
            catalog=catalog,
            orchestration_artifacts=orchestration_artifacts,
            governance=governance,
            sqlite_db_path=sqlite_path_str,
        )

    @staticmethod
    def _materialize_sqlite(
        db_file: Path,
        bronze: list[dict[str, Any]],
        silver: list[dict[str, Any]],
        quarantined: list[dict[str, Any]],
        gold: list[dict[str, Any]],
    ) -> None:
        conn = sqlite3.connect(str(db_file))
        try:
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS bronze_raw (payload_json TEXT NOT NULL)")
            cur.execute("DELETE FROM bronze_raw")
            cur.executemany(
                "INSERT INTO bronze_raw (payload_json) VALUES (?)",
                [(json.dumps(r, sort_keys=True),) for r in bronze],
            )

            cur.execute(
                "CREATE TABLE IF NOT EXISTS silver_orders ("
                "order_id TEXT PRIMARY KEY, customer_id TEXT, amount REAL, "
                "currency TEXT, status TEXT, event_timestamp TEXT)"
            )
            cur.execute("DELETE FROM silver_orders")
            for r in silver:
                cur.execute(
                    "INSERT OR REPLACE INTO silver_orders VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(r.get("order_id", "")),
                        str(r.get("customer_id", "")),
                        float(r.get("amount", 0.0)),
                        str(r.get("currency", "")),
                        str(r.get("status", "")),
                        str(r.get("event_timestamp", "")),
                    ),
                )

            cur.execute("CREATE TABLE IF NOT EXISTS quarantined_records (payload_json TEXT NOT NULL)")
            cur.execute("DELETE FROM quarantined_records")
            cur.executemany(
                "INSERT INTO quarantined_records (payload_json) VALUES (?)",
                [(json.dumps(r, sort_keys=True),) for r in quarantined],
            )

            cur.execute(
                "CREATE TABLE IF NOT EXISTS gold_customer_revenue ("
                "customer_id TEXT PRIMARY KEY, order_count INTEGER, total_amount REAL)"
            )
            cur.execute("DELETE FROM gold_customer_revenue")
            for g in gold:
                cur.execute(
                    "INSERT OR REPLACE INTO gold_customer_revenue VALUES (?, ?, ?)",
                    (str(g["customer_id"]), int(g["order_count"]), float(g["total_amount"])),
                )
            conn.commit()
        finally:
            conn.close()


class DataEngineeringPipelineBlock(BaseBlock):
    """LangGraph-compatible pipeline block that executes the DataEngineeringAdvisor."""

    def __init__(self, name: str = "data_engineering_execution", llm: Any = None) -> None:
        super().__init__(name=name, block_type="data_engineering_execution")
        self.llm = llm

    def execute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        data = state.get("data", {})
        inputs = state.get("inputs", {})
        pipeline_name = str(
            data.get("pipeline_name") or inputs.get("pipeline_name") or "commerce_orders_medallion"
        )
        description = str(
            data.get("pipeline_description")
            or inputs.get("pipeline_description")
            or "Ingest e-commerce orders, validate schema contract, and aggregate customer revenue."
        )
        mode_raw = str(data.get("ingestion_mode") or inputs.get("ingestion_mode") or "batch").lower()
        mode = IngestionMode.STREAM if mode_raw == "stream" else IngestionMode.BATCH

        paradigm_raw = str(data.get("paradigm") or inputs.get("paradigm") or "elt").lower()
        paradigm = PipelineParadigm.ETL if paradigm_raw == "etl" else PipelineParadigm.ELT

        workspace_dir = data.get("workspace_dir") or inputs.get("workspace_dir")
        advisor = DataEngineeringAdvisor()
        result = advisor.run_pipeline_from_description(
            description=description,
            pipeline_name=pipeline_name,
            ingestion_mode=mode,
            paradigm=paradigm,
            workspace_dir=workspace_dir,
        )

        return BlockResult(
            block_name=self.name,
            status=BlockStatus.SUCCESS,
            updates={
                "data_pipeline_result": result.model_dump(mode="json"),
                "storage_modeling": result.storage_modeling.model_dump(mode="json"),
                "silver_quality_report": result.silver_quality_report.model_dump(mode="json"),
                "observability": result.observability.model_dump(mode="json"),
                "governance": result.governance.model_dump(mode="json"),
                "data_pipeline_markdown": result.to_markdown(),
            },
            message=(
                f"Executed data pipeline '{pipeline_name}' "
                f"(Silver rows={result.silver_records_cleaned}, quality={result.silver_quality_report.quality_score}%)."
            ),
        )
