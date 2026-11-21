---
name: oss-contribution
description: Analyze open-source repositories in read-only mode, index with RAG/GraphRAG, detect language-specific bugs and smells, and prepare upstream contribution reports following CONTRIBUTING.md.
user-invocable: true
---

# Open-Source Contribution Mode

Structured workflow for analyzing open-source repositories and preparing high-signal contributions without executing untrusted third-party code.

## Read-Only Analysis Principles

1. **Zero Execution of Third-Party Code**
   - Inspect target repositories exclusively through static file reading, AST parsing (`nexcoder-code-intel`), and offline heuristic security scanning (`nexcoder-security`).
   - Never run target test suites, build scripts, hooks, or dynamic code evaluation on unverified third-party repositories.

2. **Multi-Language Code Intelligence (RAG & GraphRAG)**
   - Index source files into `CodeSearchIndex` using hybrid BM25 + vector retrieval.
   - Build a `CodeGraph` across supported languages (Python, TypeScript/JavaScript, Go, Rust, Java, C/C++, Delphi) and cluster subsystems via Louvain community detection (`CommunityDetector`).
   - Compute reverse-dependency blast radius (`impact_analysis`) for every affected symbol.

3. **Prioritization Taxonomy**
   - **Security (`security`)**: SAST findings, hardcoded secrets, injection sinks, and vulnerable dependencies (`pip-audit`, `osv-scanner`, `semgrep`, `bandit`). Routed strictly to private disclosure channels.
   - **Bug (`bug`)**: Logic defects, mutable default arguments, off-by-one boundaries, resource leaks, swallowed exceptions, ignored error returns, and statically broken test assertions.
   - **Performance (`performance`)**: Quadratic loops, string concatenation in loops, N+1 query patterns, and blocking I/O in async routines.
   - **Readability (`readability`)**: High cyclomatic complexity, excessive parameter lists, and missing public contracts or docstrings.

4. **Upstream Etiquette (`CONTRIBUTING.md`)**
   - Parse `CONTRIBUTING.md`, `SECURITY.md`, and `LICENSE` before proposing changes.
   - Include minimal before/after code snippets, clear technical justification, and conventional commit titles.
