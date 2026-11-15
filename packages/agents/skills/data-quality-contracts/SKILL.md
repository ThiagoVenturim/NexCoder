---
name: data-quality-contracts
description: Enforce schema contracts, primary-key uniqueness, referential integrity, null bounds, and domain invariants in data pipelines.
user-invocable: true
---

# Data Quality and Schema Contracts

Enforce explicit producer-consumer data contracts and automated quality gates at every pipeline stage.

## Contract Dimensions

1. **Schema Enforcement**
   - Validate required column names, data types (`int`, `float`, `str`, `bool`, `timestamp`), and non-nullable constraints before promoting Bronze to Silver.
   - Detect breaking schema changes (dropped columns, incompatible type narrowing) before downstream materialization.

2. **Completeness and Uniqueness Assertions**
   - Assert primary/composite key uniqueness (`unique`) to catch duplicate event delivery.
   - Enforce maximum null-rate thresholds per column (`not_null` or bounded null percentage).

3. **Value Domain and Business Rules**
   - Validate numeric ranges (e.g., `amount >= 0`), accepted categorical values, and regex formats (e.g., ISO timestamps, currency codes).
   - Quarantine invalid records to a dead-letter / rejected table with diagnostic rule IDs rather than silently corrupting Gold marts.
