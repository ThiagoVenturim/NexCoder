# faccoder Architecture

This document describes the architectural principles, module boundaries, data flows, and design patterns governing `faccoder`.

---

## Architectural Principles

1. **Vendor Agnosticism**: No package or agent may hardcode a vendor-specific model or proprietary API call. All LLM interactions route through `faccoder_core.get_chat_model(tier)` or `call_structured()`.
2. **Deterministic Fallbacks and Circuit Breakers**: Observability, vector search, and model backends must fail gracefully. If Langfuse is down, telemetry becomes a zero-cost no-op. If a vector index lacks GPU embeddings, lexical FTS5 and reciprocal rank fusion maintain operational capability.
3. **Hermetic Testability**: Every component can be executed and tested offline with zero network connectivity using `preset="offline"` and deterministic mock models.
4. **Idempotence Across Trackers**: External side-effects (creating GitHub issues, syncing project boards, updating tasks) use deterministic markers (`<!-- faccoder-id: <uuid> -->`) preventing duplicate mutations.
5. **Human Governance for Risky Actions**: Code modifications, production releases, database schema changes, and external writes are gated by human approval tokens and dry-run simulations.

---

## Monorepo Package Topology

```
                  +--------------------------------+
                  |         faccoder-core          |
                  |  - Tiered Model Registry       |
                  |  - Langfuse Tracing & Breaker  |
                  |  - HybridStore (SQLite+vec)    |
                  |  - Usage & Cost Metering       |
                  +---------------+----------------+
                                  |
         +------------------------+------------------------+
         |                                                 |
         v                                                 v
+------------------------+                        +------------------------+
|  faccoder-code-intel   |                        |    faccoder-agents     |
|  - Tree-sitter & Delphi|                        |  - Persona Catalog     |
|  - Symbol Chunking     |                        |  - LangGraph Blocks    |
|  - CodeGraph & RAG     |                        |  - Guardrails & DryRun |
|  - GraphRAG Communities|                        |  - Committee & Quorum  |
+------------------------+                        +------------------------+
         |                                                 |
         +------------------------+------------------------+
                                  |
                                  v
                  +--------------------------------+
                  |       faccoder-planning        |
                  |  - PRD Decomposer              |
                  |  - Sprint Capacity & Velocity  |
                  |  - Kanban Board Synchronizer   |
                  |  - GitHub / GitLab / ADO Sync  |
                  +--------------------------------+
```

---

## Layer Responsibilities

### 1. `faccoder-core`

The foundational layer providing infrastructure services:

- **Model Registry (`faccoder_core.models`)**:
  - `ChatModelRegistry`: Maps `(tier, provider)` pairs to LangChain base chat models.
  - `RotatingChatModel`: Round-robin key rotation across provider credentials with automatic cool-down on rate-limit errors (HTTP 429).
  - `FakeChatModel`: Deterministic mock model for testing and offline development.
- **Observability (`faccoder_core.observability`)**:
  - `LangfuseCallbackHandler`: Emits traces, execution spans, prompt tokens, and completion metrics.
  - Circuit Breaker: Automatically halts network attempts if consecutive errors exceed threshold, preserving latency and preventing crashes.
- **Retrieval Infrastructure (`faccoder_core.retrieval`)**:
  - `HybridStore`: Local SQLite storage combining FTS5 full-text search with `sqlite-vec` embeddings.
  - Rank Fusion: Reciprocal Rank Fusion (`rrf_fuse`) and Maximal Marginal Relevance (`mmr_select`).
  - Embedding Registry: Hash-based offline embeddings, HuggingFace sentence-transformers, Ollama, and OpenAI-compatible vector endpoints.
- **Safety and Utilities (`faccoder_core.utils`)**:
  - `call_structured()`: Validates LLM responses against Pydantic schemas with automatic self-correcting retry.
  - `resolve_inside()`: Enforces directory sandboxing to block directory traversal attacks (`../`).
  - `UsageMeter`: Tracks token consumption and costs against configurable user and pipeline budgets.

### 2. `faccoder-code-intel`

The comprehension engine for source code repositories:

- **AST Parsers**:
  - Modular parser architecture leveraging Tree-sitter for modern languages (Python, Go, JavaScript, TypeScript, Java, C, C++, Rust).
  - Custom Object Pascal parser extracting Delphi units, interface/implementation declarations, classes, methods, and DFM form components.
- **Symbol Chunking**:
  - Rather than arbitrary token or character windows, code is chunked along semantic symbol boundaries (functions, classes, methods) with enclosing context preserved.
- **CodeGraph**:
  - Directed multigraph representing syntactic and semantic relationships: `calls`, `inherits`, `implements`, `references`, and `binds_ui`.
  - Impact Analysis: Calculates transitive blast radiuses, cycle risks, and architectural coupling scores.
- **GraphRAG Communities**:
  - Louvain modularity clustering on the code graph discovering structural community hierarchies.
  - Summarizes architectural domains to answer high-level questions without exhaustive file scans.

### 3. `faccoder-agents`

The catalog and execution engine for autonomous personas:

- **Persona Catalog**:
  - Markdown-based specifications (`agents/<sector>/<slug>.md`) with YAML frontmatter.
  - Sectors: `direction`, `requirements`, `product`, `engineering`, `ui-ux`, `qa`, `security`, `data-ai`, `support`, `marketing-gtm`.
- **Pipeline Orchestration**:
  - Built on LangGraph statecharts.
  - Blocks:
    - `ValidatorBlock`: Validates state payloads against required contracts.
    - `PromptBlock`: Formats parameterized prompt templates and calls the designated model tier.
    - `ConditionBlock`: Evaluates routing conditions to direct workflow branches.
    - `HumanApprovalBlock`: Issues cryptographically signed, short-lived tokens and executes safe dry runs before sensitive mutations.
- **Committee and Quorum**:
  - Multi-agent deliberation and weighted voting for architectural decisions, PRD reviews, and release gating.

### 4. `faccoder-planning`

The translation layer between product specifications and technical execution:

- **PRD Decomposition**:
  - Converts freeform or structured PRDs into hierarchical backlogs: `Epic` -> `User Story` -> `Task`.
  - Generates Given/When/Then acceptance criteria, technical layer tags, and estimated hours/points.
- **Capacity Calculator**:
  - Models realistic team capacity factoring in work schedules, reserves/buffers (default 15-20%), and historical team velocity.
- **Idempotent Trackers**:
  - Adapters for GitHub (REST + GraphQL Projects v2), GitLab, and Azure DevOps.
  - Embeds unique tracking markers into descriptions to guarantee re-running sync loops will update rather than duplicate issues.
- **Kanban Sync Loop**:
  - Detects active sprint slippage, updates board columns, and dynamically recommends scope deferrals to future milestones.

---

## Data Flow: From Idea to Working Code

```
[Idea / Intake]
       |
       v
[faccoder-ideation]  --> Research Squad (Market, Competitors, Gaps)
       |             --> Architectural Jury (Go / Pivot / No-Go)
       v
   [PRD Draft]
       |
       v
[faccoder-planning]  --> Decomposition (Epics, Stories, Tasks)
       |             --> Capacity Planning & Git Issue Sync
       v
[faccoder-code-intel]--> Code Graph Indexing & Impact Analysis
       |             --> Multi-hop GraphRAG Retrieval
       v
 [faccoder-agents]   --> Specialized Engineer Personas
       |             --> Guarded LangGraph Pipelines
       v
  [Working PR]       --> Human Approval & Automated Test Verification
```
