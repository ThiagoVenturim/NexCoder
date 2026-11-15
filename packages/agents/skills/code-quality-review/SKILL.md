---
name: code-quality-review
description: Detect over-engineering, duplicate functions, useless wrappers, temporary markers, long or complex functions, performance smells, confusing folder layout, and branch hygiene issues.
user-invocable: true
---

# Code Quality Review

Structured methodology and rules for reviewing code quality and architecture, prioritizing findings into `P1` (fix first), `P2` (plan next), and `P3` (clean up when touching the code), always anchored with `file:line` and a concrete refactoring suggestion.

## Target Authorization Gate

- Run quality review pipelines only against repositories owned by the user or explicitly authorized via the control-plane `TargetAuthorizationGate`.
- Every review grant, refusal, and completion must be recorded in the append-only audit log (`AppendOnlyAuditLog`).

## Detection Categories and Rules

1. **Unnecessary Abstractions and Over-Engineering (`over_engineering`)**
   - `single-implementation-abstraction` (`P2`): Abstract base classes or interfaces with only one concrete implementation in the codebase. Inline into the concrete class until a second real implementation exists.
   - `unimplemented-abstraction` (`P3`): Interfaces or abstract classes with zero implementations. Delete if unused, or document as an external extension point.
   - `pass-through-layer` (`P2`): Classes whose public methods all forward directly to a single collaborator without adding domain logic, validation, or state transitions.
   - `class-as-function` (`P3`): Stateless classes with a single public method that never uses `self` or `cls`. Replace with a plain module-level function.

2. **Duplication (`duplication`)**
   - `duplicate-function` (`P1`/`P2`): Functions across modules that share identical or near-identical normalized AST/token structure (4-token shingle Jaccard similarity). Consolidate into a single shared function and parameterize any differences.

3. **Useless Wrappers (`useless_wrapper`)**
   - `pass-through-wrapper` (`P2`/`P3`): Functions that only forward their arguments in the same order to another callable without adding defaults, validation, type conversion, or error handling. Call the underlying function directly.

4. **Temporary Solutions (`temporary_solution`)**
   - `temporary-marker` (`P2` for `FIXME`/`HACK`/`XXX`/workarounds; `P3` for `TODO`): Comments admitting temporary shortcuts or unfinished fixes. Replace workarounds with the permanent fix or link to a tracked issue.

5. **Readability and Complexity (`readability`)**
   - `long-function` (`P1`/`P2`): Functions exceeding the line threshold (default 50 lines; critical at 100 lines). Split by step (validate, compute, persist, format).
   - `high-complexity` (`P1`/`P2`): Functions exceeding McCabe cyclomatic complexity limits (default 10; critical at 20). Extract branches or replace condition chains with dispatch tables.
   - `deep-nesting` (`P3`): Control flow nested deeper than 4 levels. Invert conditions into guard clauses.
   - `too-many-parameters` (`P3`): Functions taking more than 6 parameters. Group cohesive arguments into a value object or dataclass.
   - `vague-name` (`P3`): Non-descriptive identifiers (`foo`, `tmp`, `do_it`, numbered names like `process2`). Rename to `verb_noun` describing the outcome.

6. **Performance Smells (`performance`)**
   - `query-in-loop` (`P2`): Database queries (`execute`, `fetchone`, `fetchall`, `get_by_id`) inside loops causing N+1 query patterns. Batch with `IN` or `JOIN` before the loop.
   - `io-in-loop` (`P3`): File or HTTP I/O executed on every loop iteration. Batch, prefetch, or cache outside the loop.
   - `nested-loops` (`P3`): Loops nested 3 or more levels deep causing polynomial runtime growth. Index inner collections in a `dict` or `set`.

7. **Folder Structure and Branch Organization (`structure`, `branching`)**
   - `leftover-file-name` / `leftover-directory-name` (`P2`): Manual backup copies (`*_old.py`, `*_bak`, `copy_*`). Delete and rely on version control history.
   - `deep-directory` / `crowded-directory` / `catch-all-module` (`P3`): Deeply nested folders, directories with too many files, or oversized `utils.py` / `helpers.py` modules. Organize by feature slice.
   - `direct-commit-on-default-branch` (`P1`), `long-lived-branch` (`P2`), `stale-branch` (`P3`), `branch-name-convention` (`P3`): Enforce `type/short-description` branches and pull-request-only merges into protected branches.
