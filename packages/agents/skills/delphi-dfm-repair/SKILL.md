---
name: delphi-dfm-repair
description: Guidelines to detect, clean, and repair corrupted Delphi VCL form definition (.dfm) files and orphan events.
user-invocable: true
---

# Delphi DFM Repair

Systematic rules for diagnosing and resolving form descriptor anomalies in Delphi `.dfm` and `.pas` pairings.

## Diagnostic Steps
1. **Orphan Event Handlers**:
   - Verify that every event property declared in the `.dfm` (e.g. `OnClick = btnSaveClick`) corresponds to a published method in the form class definition.
   - Delete dangling references where the method was removed from `.pas` but lingered in `.dfm`.
2. **Explicit Bounds Removal**:
   - Modern Delphi versions inject `ExplicitLeft`, `ExplicitTop`, `ExplicitWidth`, and `ExplicitHeight` properties into `.dfm` files.
   - Strip all `Explicit*` properties when committing forms to maintain compatibility with legacy IDE versions and eliminate visual drift.
3. **Ghost Components**:
   - Inspect `.dfm` files for components referencing uninstalled third-party packages.
