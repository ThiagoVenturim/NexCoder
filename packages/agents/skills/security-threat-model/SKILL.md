---
name: security-threat-model
description: Structured threat modeling framework combining STRIDE and DREAD for architecture security reviews.
user-invocable: true
---

# Security Threat Modeling Framework

This skill establishes structured threat modeling methodology for system architectures, APIs, and data flows.

## 1. STRIDE Threat Categorization
- **Spoofing**: Can an attacker forge identities or credentials? Require strong mutual authentication and signed tokens.
- **Tampering**: Can data in flight or at rest be modified? Enforce cryptographic hashing, TLS 1.3, and HMAC integrity.
- **Repudiation**: Can actions be denied by users or systems? Ensure append-only, tamper-evident audit logs.
- **Information Disclosure**: Are secrets, PII, or internal topologies leaked? Enforce encryption at rest, field-level encryption, and strict error sanitization.
- **Denial of Service**: Can resources be exhausted? Enforce rate limiting, connection pooling timeouts, and execution budget limits.
- **Elevation of Privilege**: Can unauthorized actions be performed? Enforce least privilege, strict RBAC/ABAC authorization checks on every boundary.

## 2. DREAD Risk Scoring
Every identified threat is scored (1-10) across five dimensions:
1. **Damage Potential**: How severe is the impact if the exploit succeeds?
2. **Reproducibility**: How reliably can the attack be executed?
3. **Exploitability**: What level of skill, tools, or authentication is required?
4. **Affected Users**: What percentage of the tenant population is vulnerable?
5. **Discoverability**: How visible is the vulnerability to threat actors?
