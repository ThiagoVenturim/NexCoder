---
name: delphi-crash-guard
description: Diagnostic and preventive rules to avoid Access Violations, pointer corruption, and runtime crashes in Delphi VCL applications.
user-invocable: true
---

# Delphi Crash Guard

Comprehensive safeguards to eliminate Access Violations, nil pointer dereferences, and application freezes in Delphi VCL codebases.

## Critical Guardrails
1. **Mandatory Object Lifecycle Cleanup**:
   Every constructor invocation (`TMyClass.Create`) must be immediately followed by a `try..finally Free` or `FreeAndNil` block:
   ```pascal
   Obj := TMyClass.Create;
   try
     Obj.DoWork;
   finally
     FreeAndNil(Obj);
   end;
   ```
2. **Nil Checks Before Pointer Access**:
   Never assume an event handler, owner reference, or query parameter is initialized. Verify `Assigned(Pointer)` before invoking methods.
3. **Safe Dataset Iteration**:
   Always wrap dataset loops with `DisableControls` and `EnableControls` inside `try..finally`:
   ```pascal
   Query.DisableControls;
   try
     Query.First;
     while not Query.Eof do
     begin
       ProcessRecord;
       Query.Next;
     end;
   finally
     Query.EnableControls;
   end;
   ```
