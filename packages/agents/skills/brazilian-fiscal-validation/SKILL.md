---
name: brazilian-fiscal-validation
description: Validation rules for Brazilian electronic tax documents, CFOP/CST combinations, and SPED ledger consistency.
user-invocable: true
---

# Brazilian Fiscal Validation

Verification guidelines for electronic invoicing and tax bookkeeping compliance.

## Audit Rules
1. **CFOP and CST Consistency**:
   - Internal operations must use CFOPs starting with `1` (inbound) or `5` (outbound).
   - Interstate operations must use CFOPs starting with `2` (inbound) or `6` (outbound).
   - International operations must use CFOPs starting with `3` (inbound) or `7` (outbound).
   - Verify that tax substitute CFOPs (e.g. `5.405`, `6.403`) match CST codes representing tax substitution (e.g. `10`, `60`, `70`).
2. **SEFAZ XML Schema Compliance**:
   - Verify that invoice payloads validate against current SEFAZ XSD schemas before digital signature transmission.
   - Compute Danfe bar codes and digest values using SHA-1 canonical XML formatting.
