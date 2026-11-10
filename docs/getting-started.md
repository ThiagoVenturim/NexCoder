# Getting Started with nexcoder

This guide walks through setting up `nexcoder`, configuring execution presets, and running your first agentic pipelines and code intelligence tasks.

---

## Prerequisites

- **Python**: Python 3.11 or 3.12 (Python 3.13 is supported for core execution; 3.11/3.12 recommended for complete Tree-sitter and PyTorch compatibility).
- **Git**: Configured with standard line endings (`core.autocrlf=input` on Unix/macOS or `.gitattributes` checkout on Windows).
- **Optional Serving Engines**:
  - [Ollama](https://ollama.ai) or [vLLM](https://github.com/vllm-project/vllm) for local model execution.
  - SQLite 3.38+ with FTS5 and vector extension support (provided via `sqlite-vec`).

---

## Installation

### 1. Clone Repository and Create Virtual Environment

```bash
git clone https://github.com/ThiagoVenturim/nexcoder.git
cd nexcoder

python -m venv .venv

# On Linux / macOS:
source .venv/bin/activate

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
```

### 2. Configure Repository Githooks

The repository includes githooks that enforce zero emojis and strip automated AI co-author trailers:

```bash
git config core.hooksPath .githooks
```

### 3. Install Monorepo Packages

Install the core foundation and feature packages in editable mode:

```bash
# Foundation packages (required by dependent packages)
pip install -e packages/core
pip install -e packages/control

# Feature packages
pip install -e packages/code-intel
pip install -e packages/agents
pip install -e packages/planning
pip install -e packages/ideation
pip install -e packages/security
pip install -e packages/capture
pip install -e packages/interfaces
pip install -e packages/serving
pip install -e packages/continuous-improvement

# Tooling and quality verification
pip install pytest ruff
```

---

## Try it in 2 minutes (Quickstart)

Experience nexcoder's end-to-end automated lifecycle immediately without needing any API keys or network connection:

```bash
python examples/quickstart/run_quickstart.py
```

This single command runs all six pipeline stages offline against an included sample project:
1. **Ideation & Architectural Jury**: Evaluates an idea hypothesis and returns a quorum consensus verdict.
2. **PRD Generation**: Creates a structured Product Requirements Document.
3. **Sprint & Backlog Planning**: Breaks down tasks and initializes a local Git repository.
4. **Code Intelligence**: Indexes AST symbols and queries code via GraphRAG.
5. **Multi-Agent Pipeline**: Dispatches the catalog `bugfix-delivery` workflow.
6. **Security Gate**: Executes SAST vulnerability checks and verifies release readiness.

For detailed breakdown, artifact descriptions, and instructions on connecting real models, see the [Quickstart Example Guide](../examples/quickstart/README.md).

---

To install optional provider dependencies (e.g. Anthropic, OpenAI, Google Gemini, Ollama, Langfuse):

```bash
pip install -e "packages/core[all]"
```

---

## Configuration and Presets

`nexcoder` manages provider configurations through environment variables and the `NexcoderConfig` model.

### Environment Setup

Copy `.env.example` to `.env` or set environment variables in your active shell:

```bash
# Model Provider API Keys (optional if running offline or local-only)
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="AIza..."

# Local Inference Endpoints
export OLLAMA_BASE_URL="http://localhost:11434"
export VLLM_BASE_URL="http://localhost:8000/v1"

# Langfuse Telemetry
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_SECRET_KEY="sk-lf-..."
export LANGFUSE_HOST="http://localhost:3000"
```

### Runtime Presets

`nexcoder` provides five execution presets out of the box:

| Preset | Description | Network Needed |
|---|---|---|
| `offline` | Deterministic fake models and hash embeddings for tests and CI | No |
| `all-open-source` | Directs all model tiers to Ollama or local vLLM instances | Localhost only |
| `local-vllm` | High-throughput local vLLM serving with GPU tensor parallelism | Localhost only |
| `all-paid` | Anthropic Claude, OpenAI, and Google Gemini across tiers | Yes |
| `hybrid` | High-volume routines run locally; synthesis and jury run on paid frontier APIs | Mixed |

Specify the preset programmatically or via environment:

```python
from nexcoder_core import NexcoderConfig, load_config

# Load default config and override preset
config = load_config()
config.preset = "offline"
```

---

## First Steps

### 1. Tiered Model Invocation

`nexcoder` avoids vendor lock-in by routing model requests to three capability tiers:
- `small`: High-throughput extraction, classification, query rewriting, and chunk tagging.
- `medium`: Code generation, unit testing, structural analysis, and documentation.
- `large`: Architectural evaluation, multi-persona jury debate, and PRD generation.

```python
from nexcoder_core import get_chat_model, load_config

# Load default config and set offline preset for hermetic execution
config = load_config()
config.preset = "offline"

model = get_chat_model("medium", config=config)

response = model.invoke("Draft a unit test plan for an authentication service.")
print(response.content)
```

### 2. Code Indexing and Symbol Retrieval

Index source code and query semantic relationships:

```python
from nexcoder_code_intel import CodeSearchIndex
from nexcoder_core.retrieval.embeddings import HashEmbedder

embedder = HashEmbedder(dimensions=256)
index = CodeSearchIndex("code_index.db", embedder=embedder)

code = """
class BillingService:
    def __init__(self, gateway):
        self.gateway = gateway

    def charge_invoice(self, invoice_id: str, amount_cents: int) -> bool:
        return self.gateway.process_charge(invoice_id, amount_cents)
"""

index.index_code("billing.py", code, language="python")

# Hybrid lexical + dense search with HyDE
results = index.search("process customer charge", top_k=2, hyde=True)
for r in results:
    print(f"[{r['score']:.3f}] {r['id']}")
```

### 3. Agent Execution with LangGraph Pipeline

Load an agent persona from the catalog and construct an execution pipeline:

```python
from nexcoder_agents.catalog import AgentCatalog
from nexcoder_agents.engine import PipelineBuilder
from nexcoder_agents.engine.blocks import PromptBlock, ValidatorBlock

# Load catalog from packages/agents/agents
catalog = AgentCatalog.from_directory("packages/agents/agents")
architect = catalog.get("lead-architect")

# Construct pipeline blocks
validator = ValidatorBlock(name="input-validator", required_keys=["prd_content"])
prompt_block = PromptBlock(
    name="generate-architecture",
    user_prompt_template=architect.prompt if architect else "{prd_content}",
)

builder = PipelineBuilder("architecture-review")
builder.add_sequence([validator, prompt_block])

pipeline = builder.compile()
```

---

## Running Quality Checks

Ensure your environment passes all repository standards:

```bash
# Verify no emojis in codebase or documentation
python scripts/check_no_emoji.py

# Lint codebase with Ruff
ruff check packages scripts

# Run test suite hermetically (offline)
python -m pytest packages
```
