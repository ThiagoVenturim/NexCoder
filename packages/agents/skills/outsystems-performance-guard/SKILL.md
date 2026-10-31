---
name: outsystems-performance-guard
description: High-performance rules and anti-pattern prevention for OutSystems reactive web, mobile, and server actions.
user-invocable: true
---

# OutSystems Performance Guard

Optimization standards and best practices for high-performance OutSystems applications.

## Key Principles
1. **Aggregates vs. SQL Nodes**:
   - Prefer Aggregates whenever possible; the OutSystems compiler automatically generates optimized SELECT projections containing only the attributes used on screen.
   - When using SQL nodes, explicitly enumerate selected columns instead of writing `SELECT *`.
2. **Screen Preparation Optimization**:
   - Never place heavy computational loops or sequential REST integrations in the data loading lifecycle.
   - Fetch only the first page of rows (e.g. `Max Records = 25`) with pagination support.
3. **Data Segregation**:
   - Isolate binary data (BLOBs, PDFs, large images) into dedicated side-car entities.
   - Do not query binary attributes during list iterations.
