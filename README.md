# faccoder

An open-source, modular platform for automated software development from idea to deployment.

`faccoder` orchestrates the complete software delivery lifecycle: intake and market research, architectural jury review, Product Requirement Document (PRD) generation, sprint capacity planning, task creation in issue trackers, AST-based code intelligence, multi-hop GraphRAG, agentic pipeline execution, automated test generation, and continuous improvement.

---

## Package Status

| Package / Module | Status | Tracking Issue |
| :--- | :--- | :--- |
| `faccoder-core` | Available | Merged in `develop` |
| `faccoder-code-intel` | Available | PR [#33](https://github.com/ThiagoVenturim/faccoder/pull/33) |
| `faccoder-agents` | Available | Issue [#3](https://github.com/ThiagoVenturim/faccoder/issues/3) / [#31](https://github.com/ThiagoVenturim/faccoder/issues/31) |
| `faccoder-planning` | Available | Issue [#4](https://github.com/ThiagoVenturim/faccoder/issues/4) |
| `faccoder-ideation` | Available | Issue [#5](https://github.com/ThiagoVenturim/faccoder/issues/5), PR [#29](https://github.com/ThiagoVenturim/faccoder/pull/29) |
| `faccoder-security` | Available | Issue [#7](https://github.com/ThiagoVenturim/faccoder/issues/7), PR [#30](https://github.com/ThiagoVenturim/faccoder/pull/30) |
| `faccoder-capture` | Available | Issue [#6](https://github.com/ThiagoVenturim/faccoder/issues/6), PR [#38](https://github.com/ThiagoVenturim/faccoder/pull/38) |
| `faccoder-control` | Available | Issue [#9](https://github.com/ThiagoVenturim/faccoder/issues/9) |
| `faccoder-interfaces` | Available | Issue [#10](https://github.com/ThiagoVenturim/faccoder/issues/10) |
| `faccoder-serving` | Available | Issue [#11](https://github.com/ThiagoVenturim/faccoder/issues/11) |
| `faccoder-continuous-improvement` | Available | Issue [#8](https://github.com/ThiagoVenturim/faccoder/issues/8) |

---

## Architecture Overview

`faccoder` is organized as a modular Python monorepo with installable packages in `packages/`:

```
faccoder/
├── packages/
│   ├── core/           # LLM registry, Langfuse tracing, hybrid retrieval, sqlite-vec
│   ├── code-intel/     # AST parsers (tree-sitter, Delphi), CodeGraph, GraphRAG, HyDE
│   ├── agents/         # Persona catalog (40 agent personas, 9 skills and 6 ready pipelines), LangGraph pipeline engine
│   └── planning/       # PRD decomposition, capacity planning, idempotent tracker sync
├── docs/               # In-depth architectural guides and reference documentation
└── scripts/            # Linting and quality assurance utilities
```

### Core Packages (Merged in Develop)

1. **`faccoder-core`**: The shared foundation across all packages.
   - Tiered model registry (`small`, `medium`, `large`) abstracting paid APIs (Anthropic, OpenAI, Google Gemini, Azure, Bedrock) and open-source models (Ollama, vLLM, LM Studio, llama.cpp).
   - Resilient Langfuse tracing with an automatic circuit breaker that degrades safely to a no-op if the telemetry backend is unreachable.
   - Usage and cost metering per agent, pipeline, and run, with configurable budget caps.
   - Structured outputs (`call_structured`) with corrective retry on schema validation failures.
   - Local hybrid search store combining SQLite FTS5 (BM25 lexical search) with `sqlite-vec` (dense vector embeddings), reciprocal rank fusion (RRF), and cross-encoder reranking.
   - Path sandboxing to prevent directory traversal across agent tools.

2. **`faccoder-code-intel`**: Code intelligence and semantic comprehension for any codebase.
   - Multi-language AST parsing via Tree-sitter (Python, Go, JavaScript, TypeScript, Java, C, C++, Rust) and dedicated Object Pascal/Delphi parsers.
   - Syntactic symbol-level chunking preserving lexical enclosing context.
   - `CodeGraph` modeling relationships: calls, inheritance, implementations, and UI form bindings.
   - GraphRAG community detection via Louvain modularity clustering for hierarchical architectural summaries.
   - HyDE (Hypothetical Document Embeddings) query transformation and bottom-up recursive documentation generation.

3. **`faccoder-agents`**: Agent persona catalog and execution engine.
   - Frontmatter-driven agent specification catalog (`agents/<sector>/<slug>.md`) covering 10 organizational sectors (direction, requirements, product, engineering, UI/UX, QA, security, data-AI, support, marketing).
   - Reusable LangGraph pipeline building blocks: `ValidatorBlock`, `ConditionBlock`, `PromptBlock`, and `HumanApprovalBlock`.
   - Safe execution guarantees: dry-run simulations, time-bounded approval tokens, tool execution caps, and committee quorum votes.
   - Export adapters for Claude Code subagents and tool manifests.

4. **`faccoder-planning`**: Agentic sprint planning and task synchronization.
   - Hierarchical PRD decomposition into Epics, User Stories, and Tasks with Given/When/Then acceptance criteria.
   - Sprint capacity calculator factoring in team work schedules, reserve buffers, and historical velocity.
   - Automated Kanban synchronization loop detecting workload slippage and recommending task deferrals.
   - Idempotent platform adapters for GitHub (Issues, Milestones, Projects v2 GraphQL), GitLab, and Azure DevOps using invisible tracking markers (`<!-- faccoder-id: <uuid> -->`).
   - Automated Git helpers for branch creation, conventional commit formatting, and pull request assembly.

---

## Quick Start

### Installation

Install the core workspace packages in editable mode:

```bash
# Clone the repository
git clone https://github.com/ThiagoVenturim/faccoder.git
cd faccoder

# Create and activate a virtual environment
python -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install the packages
pip install -e packages/core
pip install -e packages/code-intel
pip install -e packages/agents
pip install -e packages/planning
```

### Try it in 2 minutes (End-to-End Offline Quickstart)

Run the full six-stage delivery lifecycle (ideation jury, PRD, sprint planning with local git repository, AST code search, agent pipeline, security gate) offline with zero API keys:

```bash
python examples/quickstart/run_quickstart.py
```

See [examples/quickstart/README.md](examples/quickstart/README.md) for full details, expected output, and artifact descriptions.

### Basic Model Invocation

```python
from faccoder_core import get_chat_model, load_config

# Load configuration from environment or config file
config = load_config()

# Retrieve a configured model for the 'medium' tier
model = get_chat_model("medium", config=config)

response = model.invoke("Summarize the key requirements for a production RAG system.")
print(response.content)
```

### Code Indexing and Hybrid Search

```python
from faccoder_code_intel import CodeSearchIndex
from faccoder_core.retrieval.embeddings import HashEmbedder

# Initialize index with dense embeddings and SQLite FTS5 lexical index
embedder = HashEmbedder(dimensions=256)
index = CodeSearchIndex("code_index.db", embedder=embedder)

# Index code snippets or files
index.index_code("auth_service.py", "def authenticate_user(token): ...", language="python")

# Query with HyDE and reciprocal rank fusion
hits = index.search("validate authentication token", top_k=3, hyde=True)
for hit in hits:
    print(f"[{hit['score']:.3f}] {hit['id']}: {hit['text']}")
```

---

## Presets and Serving Modes

`faccoder` configures model providers via runtime presets in `FaccoderConfig`:

- `offline`: Uses `FakeChatModel` and deterministic hash embeddings for hermetic testing without network access.
- `all-open-source`: Routes all tiers to local Ollama or vLLM instances without external API calls.
- `local-vllm`: Uses high-throughput local vLLM OpenAI-compatible endpoints with tensor parallelism.
- `all-paid`: Uses Anthropic Claude, OpenAI, and Google Gemini across appropriate capability tiers.
- `hybrid`: Routes high-volume small-tier tasks (chunking, classification, extraction) to local models and complex reasoning (jury, architecture, synthesis) to frontier paid models.

---

## Documentation Directory

Documentation guides are available in the [docs/](docs/) directory:

- **Foundations & Infrastructure**:
  - [Getting Started](docs/getting-started.md): Installation, environment configuration, and workspace setup.
  - [Architecture](docs/architecture.md): Monorepo structure, data flow, package boundaries, and extension points.
  - [Models: Open-Source vs Paid](docs/models-open-vs-paid.md): Model evaluation, tier mapping, cost tradeoffs, and provider registry.
  - [Serving: vLLM vs Ollama](docs/serving-vllm-vs-ollama.md): Hardware sizing, concurrency benchmarks, Docker setups, and local LLM serving.
  - [Observability with Langfuse](docs/observability-langfuse.md): Tracing, cost tracking, circuit breaker configuration, and evaluation metrics.
  - [Control Plane](docs/control-plane.md): API key budgeting, rate limiting, audit logging, and human-in-the-loop governance.

- **Ideation, Planning & Agents**:
  - [Ideation and Jury](docs/ideation-and-jury.md): Research squad analysis, competitive matrices, and multi-persona jury quorum voting.
  - [Agentic Planning](docs/agentic-planning.md): PRD transformation, capacity planning, Git automation, and idempotent tracker synchronization.
  - [Agents Catalog](docs/agents-catalog.md): Agent taxonomy, frontmatter schema, sector coverage, and specialized technology packs.
  - [Pipelines](docs/pipelines.md): LangGraph workflow orchestration, reusable blocks, human approval gates, and dry-run guarantees.

- **Code Intelligence, Retrieval & Case Studies**:
  - [RAG Fundamentals](docs/rag-fundamentals.md): Lexical search, vector representations, chunking strategies, and hybrid fusion.
  - [Advanced RAG](docs/advanced-rag.md): Query expansion, HyDE, MMR diversification, context compression, and reciprocal rank fusion (RRF).
  - [GraphRAG](docs/graphrag.md): Code relationship graphs, Louvain community detection, and multi-hop architectural synthesis.
  - [Reranking](docs/reranking.md): Cross-encoders, bi-encoders, inference latency, and two-stage retrieval pipelines.
  - [Choosing Embedding Models](docs/choosing-embedding-models.md): Benchmark comparison (BGE-M3, Nomic, Voyage, OpenAI) and dimensionality considerations.
  - [Language Support](docs/languages.md): Tree-sitter grammars, Delphi / Object Pascal AST parsing, and cross-language symbol extraction.
  - [Case Study](docs/case-study.md): How a 20-year legacy monolithic enterprise codebase was fully mapped and documented in three weeks.

---

## Repository Standards

Every contribution to `faccoder` adheres to strict automated repository standards:

1. **Zero Emojis**: Emojis are strictly disallowed across all code, docstrings, commit messages, Markdown documents, and UI strings. Enforced via `scripts/check_no_emoji.py` and pre-commit hooks.
2. **Zero AI Attribution Trailers**: Commit messages must not include AI co-author trailers (`Co-Authored-By:`). Enforced via `.githooks/commit-msg`.
3. **Clean Conventional Commits**: Commit messages follow the Conventional Commits specification in English (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
4. **Offline Testing**: Automated test suites pass without network dependencies or paid credentials using `preset="offline"` and local mock models.
5. **Linting and Formatting**: Code formatting and typing pass Ruff checks with strict rules.

---

## Origin

`faccoder` originated from field-tested enterprise artificial intelligence systems developed by Thiago Venturim across large-scale production environments:

- **Enterprise Autonomous Agents Platform**: Proven in production across autonomous agent teams, specialized skills catalog, and legacy multi-million line codebases.
- **Engineering Delivery Framework**: Covering 70+ specialized engineering personas, capacity models, and automated development synchronization.

The techniques, retrieval mechanisms, and governance patterns forged in these systems have been synthesized into `faccoder` as a vendor-neutral, generic, open-source software delivery framework.

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).
