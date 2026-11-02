# faccoder-interfaces

Unified CLI, Model Context Protocol (MCP) server, and REST API for the faccoder platform.

## Features

- **MCP Server**: Stdio and streamable HTTP / Server-Sent Events (SSE) server exposing tools from modules in develop:
  - Ideation: `research_idea`, `judge_idea`
  - Planning: `plan_sprints`, `sync_board`
  - Code Intelligence: `search_code`, `impact_analysis`, `generate_docs`
  - Security: `security_scan`
  - Agents and Pipelines: `run_agent`, `run_pipeline`, `approve_step`
  - Graceful informative messaging for modules not yet in develop (`capture`, `serving`, `control`, `continuous-improvement`).
- **REST API /v1**: FastAPI application with `/v1/capabilities`, `/v1/health`, direct endpoints for all module capabilities, and SSE streaming for pipeline execution.
- **Unified CLI**: `faccoder` CLI with subcommands: `init`, `idea`, `judge`, `plan`, `index`, `docs`, `run`, `export`, and `serve`.
- **Claude Code Plugin**: Config helper generating `.mcp.json` and exporting Claude Code skills/agents.
- **100% Offline Ready**: Fully functional with mock/fake presets and in-memory execution.
