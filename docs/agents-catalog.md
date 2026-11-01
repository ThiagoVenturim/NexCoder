# Agents Catalog: Personas, Sectors and Packs

`faccoder-agents` manages a structured catalog of specialized autonomous personas, organizing roles across organizational sectors and technology stacks.

---

## Agent Specification Format

Every agent persona is stored as a Markdown file with structured YAML frontmatter under `agents/<sector>/<slug>.md`:

```yaml
---
name: "Lead Systems Architect"
slug: "lead-architect"
sector: "engineering"
tier: "large"
description: "Evaluates architectural trade-offs, system boundaries, and cross-package contracts."
tools:
  - "code_graph_impact"
  - "search_code"
  - "resolve_inside"
skills:
  - "distributed-systems"
  - "domain-driven-design"
---

# Role and Purpose

You are the Lead Systems Architect responsible for maintaining modularity, clean boundaries,
and high cohesion across packages.

## Guidelines
- Never introduce circular dependencies between packages.
- All inter-package communication must occur via public interfaces.
- Preserve backward compatibility across public library APIs.
```

### Frontmatter Schema Fields
- `name`: Human-readable display title.
- `slug`: Unique kebab-case identifier (used for CLI invocation and pipeline references).
- `sector`: Departmental organizational sector.
- `tier`: Required LLM capability tier (`small`, `medium`, `large`).
- `description`: Concise summary of responsibilities.
- `tools`: Whitelist of MCP or system tools the agent is authorized to invoke.
- `skills`: Specialized domain playbooks loaded dynamically into the context.

---

## The 10 Core Organizational Sectors

The seed catalog covers 10 primary organizational departments:

| Sector | Primary Personas | Key Responsibilities |
|---|---|---|
| **`direction`** | `executive-sponsor`, `portfolio-manager` | Strategic alignment, capital allocation, high-level roadmaps |
| **`requirements`** | `business-analyst`, `intake-analyst` | Stakeholder interviews, business rules, compliance constraints |
| **`product`** | `product-manager`, `user-advocate` | PRDs, user stories, feature prioritization, acceptance criteria |
| **`engineering`** | `lead-architect`, `backend-dev`, `frontend-dev` | System design, API contracts, code implementation, refactoring |
| **`ui-ux`** | `ux-designer`, `accessibility-auditor` | Wireframes, accessibility compliance (WCAG), user workflows |
| **`qa`** | `qa-lead`, `test-engineer`, `e2e-specialist` | Test plans, unit tests, integration testing, visual regression |
| **`security`** | `sec-threat-model`, `sec-sast-triage`, `sec-fixer` | Threat modeling, SAST scan analysis, vulnerability remediation |
| **`data-ai`** | `data-engineer`, `mcp-builder`, `eval-analyst` | Data schemas, vector pipelines, MCP tool creation, model evaluation |
| **`support`** | `support-triage`, `incident-responder` | Ticket diagnostics, root cause analysis, patch validation |
| **`marketing-gtm`** | `gtm-strategist`, `technical-writer` | Release notes, developer documentation, product positioning |

---

## Technology Stack Packs

Beyond general engineering personas, `faccoder` provides specialized **Stack Packs** with deep language-specific heuristics:

- **`pack-python`**: Asyncio patterns, Pydantic v2 schemas, SQLAlchemy 2.0 mapped relationships, Ruff formatting, and pytest fixtures.
- **`pack-delphi`**: Object Pascal AST conventions, memory leak prevention (`try..finally Free`), DFM form visual event decoupling, CP1252/AnsiString handling, and ADO/SQLOLEDB SQL Server 2008 queries.
- **`pack-csharp`**: .NET 8/9 Minimal APIs, Entity Framework Core, dependency injection lifetimes, and xUnit patterns.
- **`pack-java`**: Spring Boot, virtual threads, Gradle/Maven conventions, and SpotBugs rules.
- **`pack-node-ts`**: TypeScript strict typing, Fastify/Express, ESLint, and vitest testing.
- **`pack-outsystems`**: Service Studio conventions, 4LC architecture, OutSystems Action optimization, and SQL Node safeguards.

---

## Loading and Using the Catalog in Code

```python
from faccoder_agents.catalog import AgentCatalog

# Load catalog from the agents directory
catalog = AgentCatalog.from_directory("agents")

# Retrieve an agent by slug
qa_engineer = catalog.get("test-engineer")
print(f"Loaded: {qa_engineer.name} [Tier: {qa_engineer.tier}]")

# Render parameterized prompt
prompt = qa_engineer.render_prompt(module_name="billing", coverage_target="85%")
```

### Exporting for Claude Code and External Agents

The catalog can be exported to subagent folders or JSON configurations compatible with Claude Code:

```bash
faccoder-agents export --format claude-subagents --out .claude/agents/
```
