---
name: database-modeling
description: Review SQL schemas and data models for missing primary keys, unindexed foreign keys, repeated column groups, list-valued text columns, and relational tables misused as key-value stores.
user-invocable: true
---

# Database Modeling

Principles and static checks for relational schema design, indexing, normalization, and storage engine selection.

## Schema Review Rules

1. **Primary Keys and Identity (`missing-primary-key` - `P2`)**
   - Every relational table must declare an explicit `PRIMARY KEY` (column-level or table-level constraint) so rows can be uniquely addressed, deduplicated, replicated, and referenced.

2. **Foreign Key Indexing (`foreign-key-without-index` - `P2`)**
   - Columns referencing another table (`REFERENCES ...` or `*_id` foreign keys) must be covered by an index (`CREATE INDEX`, `UNIQUE`, or leading column of a composite key) to prevent full table scans on joins and cascading deletes.

3. **First Normal Form and Repeating Groups (`repeated-column-group` - `P2`, `list-in-column` - `P3`)**
   - Avoid numbered attribute columns (`phone1`, `phone2`, `phone3`, `tag_1`, `tag_2`). Extract a child table with one row per item and a foreign key to the parent table.
   - Avoid comma-separated lists stored in text columns (`*_ids`, `*_list`, `*_csv` as `TEXT`/`VARCHAR`). Use an association table or a native array/JSON column with appropriate indexing.

4. **Storage Engine Fit (`key-value-in-relational` - `P3`)**
   - Tables consisting only of a `key` and `value` pair (plus optional audit timestamps) indicate a key-value store embedded in a relational schema. Use a dedicated configuration/key-value store when accessed strictly by key, or model structured settings as typed columns.

5. **Query Access Patterns (`query-in-loop` - `P2`)**
   - Never issue row-by-row lookups inside application loops (N+1 queries). Fetch related records in bulk using `WHERE id IN (...)` or `JOIN` statements and index the result in memory.
