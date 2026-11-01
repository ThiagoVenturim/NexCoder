# Control Plane: Governance, Budgets and Security

> **Status**: This module is currently Planned ([Issue #9](https://github.com/ThiagoVenturim/faccoder/issues/9)). Code examples illustrate the upcoming release API.

Autonomous coding agents possess significant capabilities: editing files, running test scripts, invoking LLM reasoning engines, and interacting with remote issue trackers.

The `faccoder` **Control Plane** establishes governance boundaries: API key budgeting, per-tool rate limiting, immutable audit logging, path sandboxing, and human approval gates.

---

## Architectural Pillars

```
+-------------------------------------------------------------+
|                      faccoder Control                       |
+-------------------------------------------------------------+
|  1. Key & Budget Caps   |  Monthly USD limits & token quotas|
|  2. Tool Middleware     |  Per-tool rate limiting & audit   |
|  3. Path Sandbox        |  Directory traversal prevention   |
|  4. Human Approval Gate |  Cryptographic tokens & dry runs  |
|  5. Audit Log           |  Tamper-evident JSONL audit stream|
+-------------------------------------------------------------+
```

---

## 1. Budget and Token Caps

Autonomous agent loops can accidentally consume extensive token budgets if unbounded recursive loops or repetitive retries occur.

`faccoder-core` incorporates a central `UsageMeter` and `BudgetGuard`:

- **Per-Execution Budget**: Enforces maximum dollar spend per pipeline run (e.g. `$2.00`).
- **Monthly Project Cap**: Restricts cumulative consumption per tenant or project.
- **Circuit Trip**: When budget reaches 100%, subsequent model calls are rejected with `BudgetExceededError`, terminating recursive execution safely.

```python
from faccoder_core.observability.usage import BudgetExceededError, usage_scope

# Enforce budget scope during pipeline or agent execution
try:
    with usage_scope(max_cost_usd=1.50, max_tokens=100_000) as meter:
        # Agent execution steps...
        print(f"Current spend: ${meter.cost_usd:.4f}")
except BudgetExceededError as err:
    print(f"Run halted safely: {err}")
```

---

## 2. Path Sandboxing

Agents equipped with file system access must be strictly prohibited from modifying files outside the designated workspace or accessing sensitive host configuration (e.g. `~/.ssh`, `/etc/passwd`, `C:\Windows`).

`faccoder_core.sandbox` provides path containment validation:

```python
from faccoder_core.sandbox import PathOutsideSandboxError, resolve_inside

workspace_root = "/path/to/project"

# Safe resolution
safe_path = resolve_inside(workspace_root, "src/billing/service.py")
# Returns: /path/to/project/src/billing/service.py

# Malicious path traversal
try:
    unsafe_path = resolve_inside(workspace_root, "../../.env")
except PathOutsideSandboxError as err:
    print(f"Blocked directory traversal: {err}")
```

---

## 3. Human Approval Gates (b85 Guard)

For destructive, costly, or externally-visible actions (e.g. deleting tables, opening pull requests, running database migrations, or executing shell scripts), `faccoder` requires human-in-the-loop authorization.

The `HumanApprovalBlock` in `faccoder-agents` implements this pattern:

1. **Dry-Run Simulation**: The agent executes a dry run first, producing a diff or summary of intended mutations.
2. **Approval Request**: The block suspends pipeline execution and issues a short-lived, cryptographically signed approval token.
3. **Interactive or Automated Resolution**:
   - A human reviewer reviews the diff and approves via CLI or web UI.
   - If unapproved within the time limit (e.g. 30 minutes), the token expires and the pipeline aborts cleanly without making modifications.

```python
from faccoder_agents.engine.blocks import HumanApprovalBlock

approval_block = HumanApprovalBlock(
    name="approve-pr-creation",
    action_description="Create draft pull request on GitHub",
    timeout_minutes=30,
    require_dry_run=True,
)
```

---

## 4. MCP Middleware and Tool Rate Limiting

When exposing tools via the Model Context Protocol (MCP), middleware meters invocation frequency per tool to protect against resource exhaustion:

- **Read Tools (`search_code`, `get_symbol`)**: High throughput, cached responses.
- **Write Tools (`edit_file`, `write_file`)**: Strictly rate-limited and logged.
- **Execution Tools (`run_test`)**: Restricted to containerized or virtual environment sandboxes.

---

## 5. Audit Logging

Every critical decision, tool execution, model call, and human approval is logged as a structured JSON record:

```json
{
  "timestamp": "2026-11-01T14:40:00Z",
  "actor": "agent:lead-architect",
  "action": "git_commit",
  "target": "packages/core",
  "status": "approved",
  "approver": "user:developer",
  "tokens": { "input": 1540, "output": 380 },
  "cost_usd": 0.0094
}
```

Audit streams can be piped to central security information and event management (SIEM) systems or stored as local append-only log files.
