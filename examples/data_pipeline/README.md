# nexcoder Data Engineering Pipeline Example (Offline Medallion ETL/ELT)

This example runs an end-to-end offline data engineering pipeline from a natural-language workload description using synthetic e-commerce data (`preset="offline"`).

## What This Example Covers

1. **Ingestion (`Bronze`)**:
   Loads deterministic synthetic order records (including realistic dirty duplicates, negative amounts, and null keys) with ingestion timestamps and execution mode metadata.
2. **Transformation (`Silver` & `Gold`)**:
   Deduplicates by primary key (`order_id`), enforces schema types and domain rules, quarantines invalid records into a dead-letter table (`quarantined_records`), and computes customer-level revenue aggregates (`gold_customer_revenue`).
3. **Data Quality & Schema Contracts**:
   Evaluates producer-consumer `SchemaContract` rules (`schema`, `unique`, `not_null`, `type`, `range`, `allowed_values`) before and after Silver cleaning.
4. **Data Observability**:
   Monitors the four pillars of data health: freshness SLA (`staleness_minutes`), volume bounds, per-column null ratios, and schema/statistical drift against a baseline batch.
5. **Storage Modeling & Anti-Pattern Advisor**:
   Scores candidate storage engines (`relational`, `columnar`, `key_value`, `vector`, `lakehouse`) and flags modeling anti-patterns (`EAV_IN_ANALYTICS`, `UNINDEXED_JSON_BLOB`, `UNBOUNDED_SELECT_STAR`, `MISSING_PARTITION_KEY`).
6. **Orchestration Code Generation**:
   Generates Airflow TaskFlow DAGs, Dagster Software-Defined Assets, and dbt SQL models, validating generated Python syntax with `nexcoder-code-intel`.
7. **Control Plane Governance**:
   Tracks token/compute budgets and records tamper-evident hash-chained audit events via `nexcoder-control`.

## How to Run

```bash
python examples/data_pipeline/run_data_pipeline.py
```

Or via the `nexcoder-agents` CLI:

```bash
nexcoder-agents run-data-pipeline "Ingest orders and aggregate customer revenue" --workspace-dir ./dist/data_demo
```
