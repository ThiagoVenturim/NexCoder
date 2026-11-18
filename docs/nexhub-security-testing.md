# NexHub Quality & Security Testing Integration

## Overview

The NexHub testing integration enables users to trigger, monitor, and visualize extreme quality and security testing suites for their applications directly from the NexHub desktop workspace canvas.

NexHub coordinates with the NexCoder control and interface plane over REST and Model Context Protocol (MCP) to:
1. Validate explicit target authorization before any test suite executes.
2. Partition selected test types (`unit`, `system`, `process`, `dom`, `api`, `security`) across `N` parallel specialist agents.
3. Track execution progress and budget spending in real time.
4. Render test agents as live terminal cards on the NexHub infinite canvas with ring-buffer logs and states.
5. Export consolidated findings and remediation recommendations back to the canvas as interconnected note cards.

## Target Authorization Gate

In strict alignment with `USAGE_POLICY.md`, testing suites only execute against targets that the user has verified as owned or explicitly authorized:
- **Owned Target Flag**: `owned_target=True` confirms that the targeted codebase or local application belongs to the user.
- **Audit Logging**: Every authorization check (granted or rejected) is recorded in `AppendOnlyAuditLog` with secret tokens redacted.
- **Preflight Verification**: NexHub queries `/v1/security-tests/preflight` (or MCP tool `verify_security_test_target`) to display target status, disclaimer, and require explicit confirmation prior to launch.
- **Hard Rejection**: If an unmarked target is submitted without an approval token or registration, the engine aborts with status `rejected` and gate verdict `BLOCKED`.

## Test Suites

The engine supports 6 specialized testing dimensions:
- `unit`: Source code AST analysis, test suite discovery, and assertion safety verification.
- `system`: Manifest analysis (`pyproject.toml`, `package.json`), entrypoints, and environment boundaries.
- `process`: Process lifecycle checks, abrupt termination detection (`os._exit`), and signal cleanup.
- `dom`: Web markup inspection, interactive element selectors, and WCAG accessibility contracts.
- `api`: Endpoint schema conformance, dynamic code evaluation risks, and boundary parameter validation.
- `security`: Defensive security scans for SQL injection patterns, prompt injection risks, and secret leakage in logs.

## Canvas Representation

When dispatched, NexCoder returns an infinite canvas layout formatted for NexHub:
- **Orchestrator Card**: Terminal card (`card-orchestrator-{run_id}`) displaying execution orchestrator logs, budget tracking, and milestones.
- **Agent Terminal Cards**: Worker agent cards (`card-agent-{agent_id}`) displaying real-time agent status (`idle`, `running`, `completed`), assigned suites, and terminal log streams.
- **Report Note**: Markdown note card (`note-report-{run_id}`) summarizing suite results, agent metrics, and findings overview.
- **Remediation Note**: Markdown note card (`note-remediations-{run_id}`) listing reproduction steps and suggested fixes.
- **Canvas Connections**: Directed edges connecting the orchestrator card to worker agents, and worker agents to canvas notes.

## API & MCP Specifications

### REST Endpoints

- `POST /v1/security-tests/preflight`: Preflight authorization verification.
- `POST /v1/security-tests/run`: Dispatch test run with target path, test types, agent count, and budget.
- `GET /v1/security-tests/runs/{run_id}`: Query status, agent logs, and progress.
- `GET /v1/security-tests/runs/{run_id}/canvas`: Retrieve full canvas payload (cards, notes, connections).
- `GET /v1/security-tests/runs/{run_id}/report`: Export report as Markdown or JSON.
- `GET /v1/security-tests/runs/{run_id}/stream`: Stream execution progress over Server-Sent Events (SSE).
- `POST /v1/security-tests/runs/{run_id}/cancel`: Cancel an ongoing test run.

### MCP Tools

- `trigger_security_tests`: Dispatch multi-agent test run against an authorized target.
- `get_security_test_status`: Query active or completed test run progress.
- `get_security_test_canvas`: Retrieve NexHub canvas payload.
- `verify_security_test_target`: Preflight check for target ownership and disclaimer.
- `cancel_security_test`: Terminate an active test run.
- `export_security_test_report`: Export test findings as Markdown or JSON.

### CLI Usage

```bash
# Verify target authorization
nexcoder test preflight --path ./sample-app --owned-target --authorized-by dev-lead

# Dispatch testing across 4 agents
nexcoder test run --path ./sample-app --types unit,system,process,dom,api,security --num-agents 4 --budget 50.0 --owned-target --authorized-by dev-lead

# Inspect status
nexcoder test status testrun-xxxxxxxxxx

# Inspect canvas payload
nexcoder test canvas testrun-xxxxxxxxxx
```
