---
name: application-security-review
description: Audit application security controls including route authentication, fail-closed access control, CORS policy, constant-time token comparison, path traversal, SSRF, and shell command execution.
user-invocable: true
---

# Application Security Review

Comprehensive defensive review checklist for application endpoints, authentication boundaries, file system access, and network calls.

## Core Vulnerability Patterns

1. **Unauthenticated Routes and Fail-Open Authentication**
   - **Risk**: Sensitive HTTP routes without authentication dependencies or auth handlers that catch exceptions and return `True`/`pass` allow unauthorized access (CWE-306, CWE-636).
   - **Remediation**: Enforce authentication dependencies on all non-public routes and ensure every exception path in auth verification fails closed.

2. **Wildcard CORS with Credentials**
   - **Risk**: Combining `allow_origins=["*"]` with `allow_credentials=True` exposes authenticated sessions to untrusted origins (CWE-942).
   - **Remediation**: Restrict `allow_origins` to an explicit allowlist of trusted origins.

3. **Non-Constant-Time Token Comparison**
   - **Risk**: Comparing tokens, API keys, or HMAC signatures with `==` or `!=` enables timing side-channel attacks (CWE-208).
   - **Remediation**: Use `hmac.compare_digest(provided, expected)` or `secrets.compare_digest(provided, expected)`.

4. **Path Traversal, SSRF, and Shell Command Injection**
   - **Risk**: Joining unvalidated user paths (`CWE-22`), fetching unvalidated external URLs (`CWE-918`), or running `subprocess` with `shell=True` / `os.system` (`CWE-78`).
   - **Remediation**: Validate file paths with `resolve_inside(base_dir, user_path)`, enforce outbound URL host allowlists blocking private/metadata IPs, and execute commands as argument lists with `shell=False`.
