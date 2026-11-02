# faccoder-security

Security scanners, specialist agents, and release gate for the faccoder platform.

## Overview

`faccoder-security` provides automated vulnerability scanning, specialist security intelligence agents, and a release gating engine designed to protect software throughout the development pipeline:

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

3. **Release Security Gate & Configuration**:
   - `security-gate`: Configurable release blocker preventing deployments with unresolved high or critical vulnerabilities.
   - `app_config`: Secure defaults scaffolding including Content Security Policy (CSP) headers, `SECURITY.md` responsible disclosure documentation, and deterministic dependency pinning.

## Installation

```bash
pip install faccoder-security
```

Or install with CLI support:

```bash
pip install "faccoder-security[cli]"
```

## Quick Start

### Multi-Scanner Engine

```python
from faccoder_security import MultiScannerEngine

engine = MultiScannerEngine()
result = engine.scan(".", force_offline=True)

print(f"Total findings: {result.total_findings()}")
for finding in result.findings:
    print(f"[{finding.severity.upper()}] {finding.title} ({finding.scanner})")
```

### Security Release Gate

```python
from faccoder_security import GatePolicy, MultiScannerEngine, SecurityGateEvaluator

engine = MultiScannerEngine()
scan_result = engine.scan(".", force_offline=True)

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
from faccoder_security.agents import ThreatModelAgent, SecurityFixerAgent

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
# Run scanners over a directory
faccoder-security scan ./src --offline

# Evaluate the security release gate
faccoder-security gate . --max-critical 0 --max-high 0 --offline

# Generate CycloneDX SBOM
faccoder-security sbom . --format cyclonedx-json --offline

# Scaffold security baseline assets
faccoder-security init-app-security . --name "MyService" --email "security@example.com"
```

## Origin

Ported and generalized from internal security and vulnerability scanning automation developed within the ApoIA platform and lochome, standardizing security pipelines across multi-tenant cloud ecosystems.
