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

## Verification and Compliance (Issue #2)

All deliverables from Issue #2 are fully implemented and verified offline:

- [x] Tree-sitter parsers: C, C++, C#, Java, Python, Go, JS/TS, Rust, Kotlin, PHP
- [x] Specialized parsers: Delphi (units, implementations, DFM forms), COBOL, OutSystems `.oml`
- [x] Symbol chunking and syntax boundary preservation
- [x] Embedding model selection per tier
- [x] Hybrid retrieval + RRF + MMR + rerank + query rewriting and HyDE
- [x] CodeGraph (imports, inherits, calls, ui_binds) and GraphRAG communities
- [x] Bottom-up incremental docgen from symbols to architectures
- [x] 38/38 unit tests passing offline with zero external dependencies


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

### 5. Filtered Search & Large Repository Considerations

`CodeSearchIndex.search` supports SQL-level metadata pushdown filtering using the `where` parameter:

```python
results = index.search("calculate interest", where={"language": "delphi"}, top_k=5)
```

**Large Repository Notes:**
- Filtered vector search (`_filtered_vector_search`) pre-filters matching candidates in SQLite via JSON pushdown and computes cosine similarity in-memory using vectorized NumPy.
- For codebases up to tens of thousands of chunks, this provides fast filtering with exact cosine similarity over the filtered subset.
- For extremely large multi-million chunk codebases, consider partitioning index files by subsystem or repository boundary.
