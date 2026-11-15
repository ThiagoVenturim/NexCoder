---
name: sql-injection-prevention
description: Audit database queries and ORM calls to eliminate SQL injection caused by string concatenation, format strings, or unsafe raw queries.
user-invocable: true
---

# SQL Injection Prevention

Methodology for identifying and remediating SQL injection vulnerabilities across raw database drivers and ORMs.

## Core Vulnerability Patterns

1. **Query String Concatenation and Interpolation**
   - **Risk**: Building SQL statements with `+`, f-strings (`f"SELECT ... {user_id}"`), `.format()`, or `%` formatting allows attackers to alter query structure and access or modify unauthorized data (CWE-89).
   - **Remediation**: Always use parameterized queries with bind placeholders (`?`, `%s`, or `:param`) and pass parameter values separately to the database driver.

2. **Unsafe ORM Raw Query Usage**
   - **Risk**: Calling `.raw()`, `.extra()`, `text()`, or `RawSQL()` with interpolated strings bypasses the ORM's built-in parameterization.
   - **Remediation**: Use standard ORM query builders/filters or pass bound parameter dictionaries to `text("SELECT ... WHERE id = :id"), {"id": value}`.
