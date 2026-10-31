# faccoder-code-intel

Code intelligence package for `faccoder`: AST and symbol parsing across languages, symbol-level chunking, and semantic code search.

## Features

- **Symbol Extraction**: Structured symbol models (`Symbol`, `SymbolType`, `SymbolLocation`, `SymbolSignature`, and relationships).
- **Tree-sitter Parsers**: Robust AST-based parsers for Python, Go, JavaScript, TypeScript, Java, C, C++, and Rust.
- **Delphi Parser**: Generic Object Pascal and Delphi form parser supporting units, interfaces, implementations, classes, methods, and DFM form components.
- **Symbol Chunker**: Chunks source code along syntactic symbol boundaries, preserving context for RAG.
- **Code Retrieval**: Integrated with `faccoder-core`'s `HybridStore` (BM25 + vector search), `rrf_fuse`, and `mmr_select` for diverse symbol retrieval.

## Installation

```bash
pip install -e packages/code-intel
```

## Quick Start

```python
from faccoder_code_intel import parse_file, SymbolChunker, CodeSearchIndex
from faccoder_core.retrieval.embeddings import HashEmbedder

# 1. Parse symbols from code
symbols = parse_file("example.py")
for sym in symbols:
    print(f"{sym.symbol_type.value}: {sym.qualified_name} (lines {sym.location.start_line}-{sym.location.end_line})")

# 2. Chunk source code by symbol boundaries
chunker = SymbolChunker()
chunks = chunker.chunk_content(content, file_path="example.py", language="python")

# 3. Index and search code with hybrid retrieval and MMR
embedder = HashEmbedder(dimensions=256)
index = CodeSearchIndex("code_index.db", embedder=embedder)
index.index_code("example.py", content)

results = index.search("calculate invoice total", top_k=5, mmr=True)
for hit in results:
    print(hit["id"], hit["score"], hit["text"])
```
