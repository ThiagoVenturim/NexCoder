---
name: guided-refactoring
description: Plan and execute safe, test-backed code refactorings using AST blast-radius analysis, characterization tests, and incremental verification.
user-invocable: true
---

# Guided Refactoring

Disciplined workflow for improving internal code structure without altering observable external behavior.

## Safe Refactoring Protocol

1. **Blast Radius Assessment**
   - Build the project `CodeGraph` and run `impact_analysis(symbol_id)` before modifying any symbol.
   - Identify all callers, inheritors, and dependent files (`risk_level`: `low`, `medium`, `high`, `critical`).

2. **Test Safety Net**
   - Verify existing tests pass before touching production code.
   - If the target routine lacks test coverage, write characterization and regression tests first.

3. **Incremental Transformation**
   - Apply small, behavior-preserving transformations (extract method/class, invert dependency, replace magic literals, fix inverted predicates, add missing test coverage).
   - Preserve public function signatures and module exports unless an explicit migration plan is approved.

4. **Post-Refactor Verification**
   - Run the offline test suite immediately after applying the change.
   - Revert or adjust any transformation that breaks existing contracts or introduces regressions.
