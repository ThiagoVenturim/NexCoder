# faccoder-code-intel

Code intelligence package for `faccoder`: AST and symbol parsing across languages, symbol-level chunking, CodeGraph, GraphRAG community detection, HyDE retrieval, and bottom-up documentation generation.

## Features

- **Symbol Extraction**: Structured symbol models (`Symbol`, `SymbolType`, `SymbolLocation`, `SymbolSignature`, and relationships).
- **Tree-sitter Parsers**: Robust AST-based parsers for Python, Go, JavaScript, TypeScript, Java, C, C++, and Rust.
- **Delphi Parser**: Generic Object Pascal and Delphi form parser supporting units, interfaces, implementations, classes, methods, and DFM form components.
- **Symbol Chunker**: Chunks source code along syntactic symbol boundaries, preserving context for RAG.
- **Code Graph & Impact Analysis**: Directed multirelational graph modeling calls, inheritance, implementation, and UI bindings with blast radius and risk scoring.
- **GraphRAG Communities**: Multi-resolution Louvain community detection with hierarchical architectural summaries and multi-hop query context assembly.
- **Advanced Retrieval & HyDE**: Query rewriting, Hypothetical Document Embeddings (HyDE), RRF rank fusion, and second-stage reranker integration.
- **Bottom-up Documentation**: Hierarchical documentation generator synthesizing docstrings from leaf routines up to classes, modules, and system architecture.

## Installation

```bash
pip install -e packages/code-intel
```

## Quick Start

### 1. Code Search with HyDE and Reranking

```python
from faccoder_code_intel import CodeSearchIndex
from faccoder_core.retrieval.embeddings import HashEmbedder

embedder = HashEmbedder(dimensions=256)
index = CodeSearchIndex("code_index.db", embedder=embedder)
index.index_code("billing.py", content, language="python")

# Hybrid search with HyDE query synthesis and MMR diversification
results = index.search("process customer refund", top_k=5, hyde=True, mmr=True)
for hit in results:
    print(hit["id"], hit["score"], hit["text"])
```

### 2. CodeGraph & Structural Impact Analysis

```python
from faccoder_code_intel import CodeGraph, parse_file

graph = CodeGraph()
symbols = parse_file("service.py") + parse_file("repo.py")
graph.add_symbols(symbols)

# Blast radius impact analysis
report = graph.impact_analysis("UserRepository", max_depth=3)
print(f"Risk: {report.risk_level}, Score: {report.impact_score}")
for affected in report.affected_symbols:
    print(f"  Dependent: {affected.name} via {affected.relationship} (depth {affected.depth})")
```

### 3. GraphRAG Community Detection

```python
from faccoder_code_intel import CommunityDetector, GraphRAGContext

detector = CommunityDetector()
communities = detector.detect_communities(graph, resolutions=[1.0])

rag = GraphRAGContext(code_graph=graph, communities=communities)
context = rag.assemble_query_context(["UserRepository", "InvoiceService"])
print("Discovered Subsystems:", [c["title"] for c in context["communities"]])
```

### 4. Bottom-up Documentation Generation

```python
from faccoder_code_intel import BottomUpDocEngine

engine = BottomUpDocEngine()
doc_tree = engine.generate_tree(symbols, communities=communities)
print(doc_tree["system::architecture"].markdown)
```
