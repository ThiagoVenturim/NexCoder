---
name: data-observability
description: Monitor data freshness SLAs, row-volume anomalies, null spikes, and statistical/schema drift with audit logging.
user-invocable: true
---

# Data Observability

Continuous monitoring across the four pillars of data health: freshness, volume, nulls, and drift.

## Four Pillars of Data Observability

1. **Freshness (Recency / SLA)**
   - Track the delta between the current evaluation time and the latest event/ingestion timestamp (`max_staleness_minutes`).
   - Alert when upstream ingestion stalls or misses scheduled SLA windows.

2. **Volume (Completeness Anomaly Detection)**
   - Verify batch row counts against expected minimum and maximum bounds or historical moving averages.
   - Detect sudden drops (truncated loads, broken connectors) or spikes (duplicate replay storms).

3. **Nulls and Field Health**
   - Compute per-column null ratios on every batch and compare against contract thresholds.
   - Flag sudden null spikes caused by upstream payload changes or broken parsers.

4. **Drift (Schema and Distribution Shift)**
   - **Schema Drift**: Detect unexpected added or missing columns compared to the registered contract baseline.
   - **Statistical / Value Drift**: Measure relative shift in numeric means/distributions or categorical proportions against historical baselines.
