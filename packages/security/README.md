# nexcoder-security

Security scanners, specialist agents, and release gate for the nexcoder platform.

## Overview

`nexcoder-security` provides automated vulnerability scanning, specialist security intelligence agents, and a release gating engine designed to protect software throughout the development pipeline:

1. **Scanners and Adapters**: Unified wrapper and offline heuristic engine integrating:
   - **Semgrep**: Static analysis for security vulnerabilities and code anti-patterns.
   - **Bandit**: Python security linter and AST analysis.
   - **Gitleaks**: Secrets, access keys, private certificates, and high-entropy token detection.
   - **OSV-Scanner**: Open Source Vulnerabilities scanner across software packages and lockfiles.
   - **pip-audit**: Known vulnerability scanner for Python environments and requirements.
   - **Trivy**: Container image misconfiguration and filesystem vulnerability detection.
   - **Syft**: Software Bill of Materials (SBOM) generator supporting CycloneDX 1.5 JSON and SPDX formats.

2. **Specialist Security Agents**:
   - `sec-threat-model`: Automated architectural threat modeling based on STRIDE and Data Flow Diagrams (DFDs).
   - `sec-sast-triage`: False positive reduction, deduplication, and exploitability assessment of static analysis findings.
   - `sec-deps`: Dependency CVE correlation, breaking change analysis, and automated upgrade commands.
   - `sec-secrets`: Exposed credential analysis, cryptographic entropy calculation, and immediate revocation/rotation playbooks.
   - `sec-asvs`: Full compliance audit against OWASP ASVS v4.0 (L1-L3), OWASP Web Top 10, and OWASP LLM Top 10.
   - `sec-fixer`: Generation of surgical unified diff patches to remediate detected vulnerabilities.
   - `sec-prompt-injection`: Audits LLM prompts, system/user role separation, external data boundaries, and unvalidated tool calls.
   - `sec-sql-injection`: Detects SQL queries assembled with string concatenation/formatting and unsafe ORM raw statements.
   - `sec-data-leakage`: Detects secrets, tokens, and PII leaked in logs, HTTP responses, HAR captures, reports, state dumps, and unconfigured egress.
   - `sec-appsec-general`: Audits unauthenticated routes, fail-open auth, wildcard CORS with credentials, non-constant-time token comparisons (`==`), path traversal, SSRF, and `shell=True` commands.
   - `RuntimeSecurityMonitor`: Optional runtime monitor that inspects prompts and tool calls and blocks prompt injection and dangerous tool arguments.

3. **Release Security Gate & Configuration**:
   - `security-gate`: Configurable release blocker preventing deployments with unresolved high or critical vulnerabilities.
   - `app_config`: Secure defaults scaffolding including Content Security Policy (CSP) headers, `SECURITY.md` responsible disclosure documentation, and deterministic dependency pinning.

4. **Security Posture Dashboards (`nexdash` Integration)**:
   - Converts multi-scanner findings, SBOM outdated dependencies, and release gate coverage into the `security_posture` semantic cube (`compute_security_metrics`, `generate_security_dashboard`).
   - Communicates with `nexdash` via MCP, REST, or offline mode to produce CSP-hardened HTML dashboards.

5. **Server Exposure, Hardening & Data Masking**:
   - `server nginx`: Hardened Nginx reverse proxy configuration generator with TLS 1.2/1.3, Let's Encrypt support, gzip compression, rate limiting zones, HSTS/CSP security headers, and syntax/container validation.
   - `server hardening`: Idempotent OS hardening scripts in Bash (`.sh`) and PowerShell (`.ps1`) covering firewall (ufw/nftables/netsh), passwordless SSH, fail2ban, unattended upgrades, non-root service accounts, and kernel sysctl parameters.
   - `server isolate`: Privatization engine auditing and remediating unshielded port mappings (binding internal databases and caches strictly to `127.0.0.1`).
   - `server mask`: PII and secret anonymizer for text logs, SQL database dumps, structured JSON records, and CSV files supporting placeholder, redact, and salted hash strategies.

## Installation

```bash
pip install nexcoder-security
```

## Quick Start

### Multi-Scanner Engine

```python
from nexcoder_security import MultiScannerEngine

engine = MultiScannerEngine()
result = engine.scan(".", force_offline=True, owned_target=True, authorized_by="sec-engineer")

print(f"Total findings: {result.total_findings()}")
for finding in result.findings:
    print(f"[{finding.severity.upper()}] {finding.title} ({finding.scanner})")
```

### Security Release Gate

```python
from nexcoder_security import GatePolicy, MultiScannerEngine, SecurityGateEvaluator

engine = MultiScannerEngine()
scan_result = engine.scan(".", force_offline=True, owned_target=True, authorized_by="sec-engineer")

policy = GatePolicy(max_critical=0, max_high=0)
evaluator = SecurityGateEvaluator(default_policy=policy)
verdict = evaluator.evaluate(scan_result)

if not verdict.passed:
    print(f"Release blocked: {verdict.summary}")
    for reason in verdict.reasons:
        print(f"  - {reason}")
```

### Specialist Security Agents

```python
from nexcoder_security.agents import ThreatModelAgent, SecurityFixerAgent

# Threat Modeling
tm = ThreatModelAgent()
report = tm.analyze(
    {
        "name": "OrderAPI",
        "components": ["Web Client", "Order Service", "PostgreSQL"],
        "flows": ["Client -> Service", "Service -> PostgreSQL"],
    }
)
print(f"Identified {len(report.threats)} threats.")

# Surgical Fixer
fixer = SecurityFixerAgent()
fix_report = fixer.analyze(scan_result.findings)
for patch in fix_report.patches:
    print(patch.diff_patch)
```

### CLI Commands

```bash
# Run scanners over an owned directory
nexcoder-security scan ./src --offline --owned-target --authorized-by sec-engineer

# Run scanners with a cryptographically signed authorization document
nexcoder-security scan https://api.example.com --offline --auth-doc ./auth_doc.yaml

# Evaluate the security release gate
nexcoder-security gate . --max-critical 0 --max-high 0 --offline --owned-target

# Generate CycloneDX SBOM
nexcoder-security sbom . --format cyclonedx-json --offline --owned-target

# Scaffold security baseline assets
nexcoder-security init-app-security . --name "MyService" --email "security@example.com"

# Run responsible-disclosure security review (prompt injection, SQLi, data leakage, general security)
nexcoder-security review ./src --owned-target --authorized-by sec-engineer --enable-monitor

# Generate Nginx reverse proxy and TLS configuration
nexcoder-security server nginx --domain app.example.com --upstream 127.0.0.1:8000 --output nginx.conf --owned-target

# Generate idempotent OS hardening scripts (Bash and PowerShell)
nexcoder-security server hardening --profile basic --output-bash hardening.sh --output-ps1 hardening.ps1 --owned-target

# Audit and remediate Docker Compose port exposure
nexcoder-security server isolate ./docker-compose.yml --remediate --owned-target

# Mask PII in SQL database dump
nexcoder-security server mask ./backup.sql --format sql --strategy placeholder --output ./backup_masked.sql --owned-target
```

## Origin

Security and vulnerability scanning automation with standardized pipelines.
