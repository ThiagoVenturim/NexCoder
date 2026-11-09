# nexcoder-control

Control plane for nexcoder: authentication, API keys, rate limits, per-tool metering, budgets, audit, approval tokens, and web panel.

## Overview

`nexcoder-control` provides security, cost governance, and operational policy enforcement for multi-tenant and agentic workflows:

1. **Pluggable Authentication**:
   - **Local Authenticator**: Username/password with PBKDF2 hashing, bearer tokens with permission scopes.
   - **OIDC Authenticator**: Standard JWT verification with JWKS caching and deterministic offline mock provider for test suites.
   - **LDAP / Active Directory Interface**: Extensible directory provider interface with in-memory offline implementation and group-to-role/scope mappings.

2. **API Keys and Rate Limits**:
   - High-entropy API keys with secret hashes stored via SHA-256.
   - Fail-closed spending cap (HTTP 403 on USD budget exceed).
   - Rate limiters using Token Bucket and Fixed Window algorithms (HTTP 429 on RPM / TPM exceed).
   - Granular permission scope checks.

3. **Per-Tool Metering & Cost Tracking**:
   - MCP middleware interceptor metering invocations, execution latencies (avg, p95), tokens, and dollar cost per tool.
   - Multi-dimensional cost attribution grouped by application, person/user, agent, and pipeline.
   - Multi-threshold budget alerting (e.g. at 80% and 100%) with optional hard limit execution blocks.
   - Tamper-evident, cryptographically chained (SHA-256) append-only audit ledger.

4. **Human Approval Tokens & CLI Governance**:
   - Short-lived, single-use, timing-safe human approval tokens with pre-flight dry-run simulation support.
   - Fail-closed CLI machine registration and administrative approval gate.

5. **Web Panel and Status API**:
   - Lightweight FastAPI metrics router and self-contained HTML/CSS operational dashboard with zero external dependencies and 100% offline capability.

## Installation

```bash
pip install nexcoder-control
```

Or install with optional web panel and CLI dependencies:

```bash
pip install "nexcoder-control[web,cli]"
```

## Quick Start

### API Keys and Rate Limiting

```python
from nexcoder_control import APIKeyCreate, APIKeyService

service = APIKeyService()

# Create key with $50.00 USD cap and 60 RPM rate limit
created = service.create_key(
    APIKeyCreate(
        name="CI Pipeline Key",
        owner="automation-team",
        usd_cap=50.0,
        rate_limit_rpm=60,
        scopes=["tools:execute", "metrics:read"],
    )
)

print(f"Issued Key: {created.raw_key}")

# Verify key during an execution request
verified = service.verify_key(
    raw_key=created.raw_key,
    required_scope="tools:execute",
    estimated_usd=0.01,
)
print(f"Authenticated Owner: {verified.owner}")
```

### Metering MCP Tools

```python
from nexcoder_control import MCPToolMeter

meter = MCPToolMeter()


def sample_tool(query: str) -> str:
    return f"Result for: {query}"


wrapped = meter.wrap_sync(
    tool_name="code_search",
    handler=sample_tool,
    caller="agent_developer_1",
    estimated_input_tokens=250,
    estimated_output_tokens=100,
)

result = wrapped("Find symbol Authenticator")
metrics = meter.get_tool_metrics("code_search")[0]
print(f"Invocations: {metrics.invocations}, Cost: ${metrics.total_cost_usd:.4f}")
```

### Cryptographic Append-Only Audit Log

```python
from nexcoder_control import AppendOnlyAuditLog

audit = AppendOnlyAuditLog()

audit.record_event(
    event_type="key.created",
    actor="admin",
    action="create",
    resource="key_12345",
    severity="info",
    details={"owner": "team-a"},
)

is_valid, message = audit.verify_integrity()
print(f"Audit log status: {message}")
```

## Origin

The control plane provides access keys, USD budget limits, and tool-level metering to govern LLM applications in production.
