---
name: query-optimization
description: Optimize analytical and transactional queries via partitioning, indexing, predicate pushdown, and execution plan analysis.
user-invocable: true
---

# Query Optimization

Practices for minimizing query latency, I/O scan volume, and compute cost across relational and columnar engines.

## Optimization Checklist

1. **Partitioning and Clustering**
   - Partition large fact and event tables by date/time granularity (`event_date`, `ingestion_month`) aligned with query filter predicates.
   - Cluster or sort within partitions by high-cardinality filter/join keys (`tenant_id`, `customer_id`).

2. **Predicate Pushdown and Projection Pruning**
   - Never use `SELECT *` in production ETL or analytical models; project only required columns to leverage columnar pruning.
   - Push filter predicates as early as possible before expensive joins or window functions.

3. **Join and Aggregation Hygiene**
   - Deduplicate dimension keys before joining to fact tables to prevent Cartesian fan-out.
   - Pre-aggregate high-volume event streams into incremental rollup tables when serving dashboards.

4. **Index Strategy (OLTP & Vector)**
   - Cover frequent equality and range predicates with composite B-Tree indexes ordered by selectivity.
   - Use HNSW or IVF indexes with tuned recall/latency parameters for vector similarity queries.
