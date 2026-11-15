---
name: data-leakage-prevention
description: Prevent secrets, tokens, credentials, and PII from leaking into application logs, HTTP responses, reports, HAR captures, serialized state, or unconfigured external egress.
user-invocable: true
---

# Data Leakage Prevention

Checklist and remediation rules for preventing credential, token, and PII exposure across application boundaries.

## Core Vulnerability Patterns

1. **Secrets, Tokens, or PII in Logs**
   - **Risk**: Writing API keys, bearer tokens, passwords, or PII (CPF, SSN, credit card numbers) to logs exposes sensitive data to log aggregation systems (CWE-532).
   - **Remediation**: Redact sensitive fields using `redact_secrets()` before logging and log only non-sensitive identifiers.

2. **Sensitive Data in Responses, Reports, HAR Captures, or Serialized State**
   - **Risk**: Returning raw credentials/tokens in API responses or persisting unredacted `Authorization`/`Cookie` headers in `.har` files, reports, or state dumps leaks secrets at rest and in transit (CWE-200).
   - **Remediation**: Use explicit response DTOs that exclude sensitive attributes and sanitize all HAR/report/state payloads before serialization.

3. **Unconfigured Customer Data Egress**
   - **Risk**: Transmitting customer records or PII to external endpoints without explicit tenant configuration violates privacy and data residency controls (CWE-359).
   - **Remediation**: Gate any external transmission behind an explicit opt-in configuration flag and anonymize PII prior to egress.
