# faccoder Quickstart: End-to-End Offline Delivery Pipeline

This example demonstrates how faccoder orchestrates the complete software engineering lifecycle without requiring external API keys or network access.

## What This Example Demonstrates

The script runs a full pipeline on an included sample Python project (`sample_project/`):

1. **Idea Intake & Architectural Jury (`faccoder-ideation`)**:
   Processes a high-level proposal ("add due dates to tasks") and evaluates market viability, architecture, and alignment across six automated juror personas returning a consensus verdict (GO / PIVOT / NO-GO).
2. **Product Requirement Document (`PRD.md`)**:
   Synthesizes the intake analysis, competitive research citations, architecture specs, and jury rubric into an actionable requirements document.
3. **Sprint & Backlog Planning (`faccoder-planning`)**:
   Decomposes the PRD into Epics, User Stories, and Tasks with acceptance criteria, computes team sprint capacity (hours, velocity, limits), and commits the initial sprint backlog into a local Git repository.
4. **Code Intelligence & GraphRAG (`faccoder-code-intel`)**:
   Parses the `sample_project/` codebase, extracts AST symbols into SQLite FTS5/vector store, and executes a code search answering architectural questions about existing implementations.
5. **Multi-Agent Delivery Pipeline (`faccoder-agents`)**:
   Runs the `bugfix-delivery` workflow from the agent catalog with a deterministic fake model, identifying a subtle bug in the sample project and preparing a validated patch.
6. **Security Gate (`faccoder-security`)**:
   Scans the codebase with offline SAST analyzers (Semgrep and Bandit rule engines) and evaluates release policies against severity thresholds.

## How to Run

Ensure the repository virtual environment is activated and monorepo packages are installed in editable mode:

```bash
# Run the end-to-end quickstart
python examples/quickstart/run_quickstart.py
```

To write artifacts to a custom directory instead of `.quickstart_artifacts`:

```bash
python examples/quickstart/run_quickstart.py --output-dir /path/to/artifacts
```

## What to Expect in the Output

The script outputs each stage with clear execution metrics:

```text
======================================================================
faccoder Offline Quickstart: End-to-End Delivery Pipeline
======================================================================

[1/6] Ideation & Architectural Jury
----------------------------------------------------------------------
Idea Title:    Add due dates and deadline tracking to task management library
Jury Decision: GO (Consensus: True)
Votes:         5 GO / 1 PIVOT / 0 NO-GO (Total jurors: 6)

[2/6] PRD Generation
----------------------------------------------------------------------
PRD generated successfully from vetted architecture and jury rubric.
Total lines:   163

[3/6] Planning & Sprint Decomposition (Git Repository)
----------------------------------------------------------------------
Scheduled Sprint: Sprint-1
Planned Hours:    7.0h
Scheduled Tasks:  2
Git Repository:   .../planning_repo

[4/6] Code Intelligence Indexing & AST Code Search
----------------------------------------------------------------------
Source Files:     5 files indexed from sample_project
RAG Question:     How is overdue status evaluated in sample_project?
Retrieved Chunks: 2

[5/6] Multi-Agent Delivery Pipeline
----------------------------------------------------------------------
Pipeline:         bugfix-delivery
Execution Status: completed (dry_run mode)
Execution Steps:  5

[6/6] Security Release Gate Evaluation
----------------------------------------------------------------------
Target Scanned:   sample_project
Findings Count:   8
Gate Verdict:     PASSED
Summary:          Release APPROVED by security gate 'default-production-gate'.
```

At completion, all generated artifacts are available in the target artifacts directory:
- `jury_verdict.json`: Full jury votes, score breakdown, and dissenting notes.
- `prd.md`: Complete Markdown PRD.
- `planning_repo/`: Git repository containing `BACKLOG.md` and `sprint_1.json`.
- `code_intel.db`: SQLite index with parsed code symbols and full-text search.
- `rag_summary.txt`: Retrieved code context and analysis.
- `pipeline_run.json`: Execution trace and step history.
- `security_gate_verdict.json`: Detailed SAST findings and gate decision.

## Switching from Offline Mode to Real Models

By default, the script uses `MockSearchProvider` and `FakeChatModel` to run self-contained in seconds.

To connect real providers (Anthropic, OpenAI, Gemini, or local models via Ollama/vLLM):

1. **Set Environment Variables**:
   ```bash
   # For Anthropic Claude
   export ANTHROPIC_API_KEY="sk-ant-..."

   # For OpenAI
   export OPENAI_API_KEY="sk-..."

   # For Google Gemini
   export GEMINI_API_KEY="..."

   # For local Ollama
   export OLLAMA_BASE_URL="http://localhost:11434"
   ```

2. **Use `get_chat_model`**:
   Replace `FakeChatModel(...)` with `get_chat_model`:
   ```python
   from faccoder_core.llm.registry import get_chat_model

   # Tiers: 'small' (fast triage), 'medium' (standard coding), 'large' (deep reasoning)
   model = get_chat_model("medium")
   ```

3. **Enable Real Web Search in Ideation**:
   In `IdeationPipeline`, pass `allow_network=True` to use DuckDuckGo or configured search backends:
   ```python
   from faccoder_ideation.pipeline import IdeationPipeline

   pipeline = IdeationPipeline(allow_network=True, model=model)
   ```
