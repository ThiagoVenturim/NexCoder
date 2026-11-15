---
name: etl-pipeline-design
description: Design idempotent batch and streaming ETL/ELT pipelines, medallion architectures, and orchestrated DAGs (Airflow, Dagster, dbt).
user-invocable: true
---

# ETL and ELT Pipeline Design

Structured methodology for building reliable, idempotent batch and streaming data pipelines.

## Core Principles

1. **Idempotency and Replayability**
   - Every ingestion and transformation step must produce identical results when re-executed for the same partition or time window.
   - Use deterministic merge keys (`MERGE INTO` / upsert by primary key + event timestamp) or partition overwrite strategies instead of blind appends.

2. **Medallion Architecture (Bronze -> Silver -> Gold)**
   - **Bronze (Raw Ingestion)**: Immutable append-only landing zone preserving raw source payloads, ingestion timestamps (`_ingested_at`), and source lineage metadata.
   - **Silver (Cleaned & Conformed)**: Deduplicated, schema-enforced, type-cast, and null-validated entities with standardized keys and timestamps.
   - **Gold (Business Aggregates & Marts)**: Dimensional star schemas, denormalized analytical marts, or feature/vector stores tailored for BI and ML consumption.

3. **Batch vs. Streaming Trade-offs**
   - **Batch Ingestion**: Scheduled micro-batches or daily/hourly extracts; lower operational cost and simpler state recovery.
   - **Streaming Ingestion**: Event-driven continuous ingestion (Kafka, CDC) with watermarking, late-arrival handling, and dead-letter queues (DLQ) for malformed payloads.

4. **Orchestration Patterns (Airflow, Dagster, dbt)**
   - **Airflow**: Task-centric DAGs with explicit sensor/operator dependencies, retries, and SLA callbacks.
   - **Dagster**: Asset-centric declarative pipelines where software-defined assets track upstream data dependencies and materialization metadata.
   - **dbt**: SQL-first ELT transformations with built-in schema tests (`not_null`, `unique`, `accepted_values`, `relationships`) and lineage DAGs.
