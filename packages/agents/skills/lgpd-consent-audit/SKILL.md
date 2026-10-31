---
name: lgpd-consent-audit
description: Auditing methodology for user consent life cycles, data minimization, and sensitive PII protection under LGPD and GDPR.
user-invocable: true
---

# LGPD/GDPR Consent Audit

Checklist and auditing guidelines for verifying privacy compliance across backend architectures.

## Verification Checklist
1. **Consent Registry**:
   - Each consent entry must record: User Identifier, Purpose Identifier, Consent Timestamp, Consent Version, and Origin IP/Channel.
   - Revocation must be supported through an idempotent API endpoint.
2. **Blind Indexing for Searchable PII**:
   - Sensitive personal documents (e.g. CPF, National ID) must never be stored in plain text or standard reversible encryption when queried.
   - Use HMAC-SHA256 with an isolated secret key to generate a searchable blind index.
3. **Data Retention & Right to Erasure**:
   - Verify that automated retention policies purge expired data.
   - Ensure soft-deleted records have their personal identifiers anonymized upon final user deletion requests.
