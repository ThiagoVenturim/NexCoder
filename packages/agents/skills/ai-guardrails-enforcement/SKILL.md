---
name: ai-guardrails-enforcement
description: Enforces target project authorization, budget policies, tamper-evident audit logging, and sensitive data scanning across all AI feature implementations.
user-invocable: false
---

# AI Guardrails Enforcement

This skill defines mandatory governance and safety checks that NexCoder agents enforce prior to generating, training, or deploying AI capabilities.

## Guardrail Pillars

1. **Target Authorization Gate**:
   - Every AI feature implementation must target a project directory verified through `TargetAuthorizationGate`.
   - The target must be confirmed as owned by the operator or backed by a cryptographically signed authorization token.
   - Unauthorized execution attempts are rejected immediately with `TargetNotAuthorizedError` and logged to the audit ledger.

2. **Budget and Cost Governance**:
   - Every feature definition specifies expected call volume and monthly budget limits.
   - Enforce budget ceilings using `BudgetManager` and `CostTracker` from `nexcoder-control`.
   - If estimated training or monthly inference costs exceed active policy thresholds, execution fails closed with `BudgetExceededError`.

3. **Tamper-Evident Audit Logging**:
   - All high-impact events (approach selection, code generation, training run initiation, model evaluation, and serving manifest export) are written to `AppendOnlyAuditLog`.
   - Each event includes SHA-256 hash chaining to the preceding entry, ensuring immutable traceability.

4. **Sensitive Data and Secret Prevention**:
   - Scans training samples, prompts, and schema definitions for leaked credentials, private keys, authorization headers, and unmasked PII.
   - Rejects inputs containing detected secrets prior to dataset curation or model fine-tuning.

5. **Open Model Preference**:
   - Enforces default usage of open-weights models.
   - If a proprietary cloud model is requested, validates that an explicit justification flag is present and budget limits accommodate the higher unit cost.
