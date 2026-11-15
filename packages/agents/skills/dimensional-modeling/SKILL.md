---
name: dimensional-modeling
description: Select optimal storage engines (relational, columnar, key-value, vector, lakehouse), design star/medallion schemas, and prevent modeling anti-patterns.
user-invocable: true
---

# Dimensional and Storage Modeling

Guidance for selecting the right data storage engine, designing analytical and operational schemas, and eliminating modeling anti-patterns.

## Storage Engine Selection Matrix

1. **Relational (OLTP - PostgreSQL, MySQL)**
   - **Best for**: Transactional integrity (ACID), normalized domain entities (3NF), high-concurrency point lookups, and row-level updates.
   - **Avoid for**: Unbounded full-table analytical scans over billions of historical events or high-dimensional vector similarity searches.

2. **Columnar Warehouse (OLAP - ClickHouse, DuckDB, BigQuery, Snowflake)**
   - **Best for**: Analytical aggregations, wide fact tables, time-series rollups, and ad-hoc BI queries scanning few columns across millions of rows.
   - **Avoid for**: Frequent single-row transactional updates or low-latency key-value session state.

3. **Key-Value / In-Memory Store (Redis, DynamoDB)**
   - **Best for**: Sub-millisecond point lookups by key, session caches, rate-limiting counters, and feature flags.
   - **Avoid for**: Multi-table joins, ad-hoc secondary filtering without indexes, or complex analytical reporting.

4. **Vector Store (pgvector, Qdrant, Milvus)**
   - **Best for**: Semantic retrieval, RAG embeddings, approximate nearest neighbor (ANN / HNSW / IVF) similarity search with metadata pre-filtering.
   - **Avoid for**: Exact financial ledger accounting or primary relational source-of-truth storage without hybrid relational backing.

5. **Lakehouse (Delta Lake, Apache Iceberg, Parquet on Object Storage)**
   - **Best for**: Petabyte-scale multi-modal data, open columnar formats with ACID transactions, time-travel auditing, and unified batch + streaming ELT.
   - **Avoid for**: Ultra-low-latency (<10ms) transactional point mutations.

## Modeling Anti-Patterns to Prevent

- **Generic EAV (Entity-Attribute-Value) in Analytics**: Destroys columnar compression, forces self-joins, and bypasses static schema types.
- **Unindexed JSON Blobs for Core Filter Predicates**: Causes full-table scans and hides schema drift until runtime query failures occur.
- **Missing Partitioning or Clustering on Fact Tables**: Leads to full scans and runaway compute costs on time-series datasets.
- **OLTP Row Store Used as Heavy Analytical Warehouse**: Contends lock managers and degrades production transaction latency.
- **Missing Primary/Surrogate Keys and Slowly Changing Dimension (SCD) Strategy**: Causes silent fan-out duplicates in downstream joins.
