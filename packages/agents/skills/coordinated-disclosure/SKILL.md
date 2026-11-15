---
name: coordinated-disclosure
description: Enforce coordinated vulnerability disclosure for open-source findings by routing security flaws to private channels and stripping exploit payloads.
user-invocable: true
---

# Coordinated Vulnerability Disclosure

Mandatory guardrails when reporting security vulnerabilities discovered in open-source or third-party projects.

## Disclosure Rules

1. **Private Channel Only**
   - Security vulnerabilities must never be opened as public issues or public pull requests.
   - Extract the maintainer's preferred private reporting channel from `SECURITY.md` (security contact email or GitHub Private Vulnerability Reporting / Security Advisories).

2. **No Exploit Payloads**
   - Reports must describe the vulnerable code location, root cause, CWE/CVE classification, and defensive remediation patch.
   - Never generate, attach, or publish functional exploits, weaponized payloads, or offensive proof-of-concept (PoC) scripts.

3. **Remediation-First Reporting**
   - Provide a minimal, surgical diff or replacement snippet that eliminates the vulnerability while preserving backward compatibility.
   - Allow maintainers a reasonable embargo window to verify and release a patched version before any public discussion.
