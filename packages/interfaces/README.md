# nexcoder-interfaces

Unified CLI, Model Context Protocol (MCP) server, and REST API for the nexcoder platform.

## Features

- **MCP Server**: Stdio and streamable HTTP / Server-Sent Events (SSE) server exposing tools from modules in develop:
  - Ideation: `research_idea`, `judge_idea`
  - Planning: `plan_sprints`, `sync_board`, `estimate_product_cost`
  - Code Intelligence: `search_code`, `impact_analysis`, `generate_docs`
  - Security: `security_scan`, `security_review`, `security_report`
  - Testing & NexHub: `trigger_security_tests`, `get_security_test_status`, `get_security_test_canvas`, `verify_security_test_target`, `cancel_security_test`, `export_security_test_report`
  - Control & Email: `send_email`
  - Agents and Pipelines: `run_agent`, `run_pipeline`, `approve_step`
  - Informative messaging for upcoming modules (`capture`, `serving`, `continuous-improvement`).
- **REST API /v1**: FastAPI application with `/v1/capabilities`, `/v1/health`, direct endpoints for all module capabilities, SSE streaming for pipelines and test executions.
- **NexHub Quality & Security Testing Integration**:
  - Preflight authorization checking via `TargetAuthorizationGate` (`/v1/security-tests/preflight`).
  - Multi-agent test dispatch partitioning `unit`, `system`, `process`, `dom`, `api`, and `security` test suites across N agents (`/v1/security-tests/run`).
  - Live progress monitoring and SSE streaming (`/v1/security-tests/runs/{run_id}/stream`).
  - Native NexHub canvas export (`/v1/security-tests/runs/{run_id}/canvas`): renders orchestrator and worker agents as terminal cards with ring-buffer logs and real-time state, alongside markdown report and remediation notes.
- **Unified CLI**: `nexcoder` CLI with subcommands: `init`, `idea`, `judge`, `plan`, `index`, `docs`, `cost`, `test`, `run`, `export`, and `serve`.
- **Claude Code Plugin**: Config helper generating `.mcp.json` and exporting Claude Code skills/agents.
- **100% Offline Ready**: Fully functional with mock/fake presets and in-memory execution.

## NexHub Testing CLI Quickstart

```bash
# Check authorization before running tests
nexcoder test preflight --path ./my-app --owned-target --authorized-by dev-lead

# Dispatch multi-agent test execution across 4 parallel agents
nexcoder test run --path ./my-app --types unit,system,process,dom,api,security --num-agents 4 --budget 50.0 --owned-target --authorized-by dev-lead

# Inspect test run status and agent terminal logs
nexcoder test status testrun-xxxxxxxxxx

# Inspect canvas payload (cards, notes, connections)
nexcoder test canvas testrun-xxxxxxxxxx
```
