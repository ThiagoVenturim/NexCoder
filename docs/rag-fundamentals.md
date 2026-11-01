# RAG Fundamentals: Retrieval-Augmented Generation for Code

Retrieval-Augmented Generation (RAG) grounds language models in an external knowledge repository, eliminating hallucinations and enabling agents to navigate large codebases.

However, applying text-based RAG directly to source code often produces poor results if lexical precision and syntactic structure are ignored. This guide explains the core concepts of code RAG and how `faccoder` implements them.

---

## The Code RAG Problem

Traditional document RAG relies on:
1. Fixed character or token sliding windows (e.g. 500 characters with 50-character overlap).
2. Pure dense vector cosine similarity.
3. Top-k passage injection into the LLM context.

When applied to code, this breaks down:
- **Boundary Fragmentation**: A fixed chunk boundary cuts a function in half, severing variable declarations from their usages.
- **Exact Identifier Misses**: Vector embeddings are trained on semantic proximity. A search for exact symbol `verify_jwt_token` may return `validate_oauth_bearer` because they share semantic embedding space, while missing the exact function call needed.
- **Lost Scoping Context**: A method inside a class loses its class name, imports, decorators, and inheritance declarations when extracted as raw tokens.

---

## 1. Syntactic Symbol Chunking

Instead of fixed-length character windows, `faccoder-code-intel` chunks code along **Abstract Syntax Tree (AST)** symbol boundaries using Tree-sitter and Object Pascal parsers:

```
+--------------------------------------------------------------+
| File: auth_service.py                                        |
|                                                              |
| import jwt, os                                               |
|                                                              |
| class AuthenticationManager:                                 |
|   +--------------------------------------------------------+ |
|   | Chunk 1: Class Definition & Header                     | |
|   | class AuthenticationManager: ...                       | |
|   +--------------------------------------------------------+ |
|   | Chunk 2: Method verify_token                           | |
|   |   Context: class AuthenticationManager                 | |
|   |   Signature: def verify_token(self, token: str) -> bool| |
|   |   Body: ...                                            | |
|   +--------------------------------------------------------+ |
+--------------------------------------------------------------+
```

Every chunk preserves its enclosing lexical context:
- File path
- Enclosing namespace/class
- Full typed signature
- Associated docstring and decorator declarations

---

## 2. Hybrid Retrieval: Combining Lexical and Dense Search

No single search algorithm handles all code queries:
- **Lexical BM25 (SQLite FTS5)** excels at exact identifier lookups (`UserRepository`, `HTTP_401_UNAUTHORIZED`, error codes).
- **Dense Vector Search (`sqlite-vec`)** excels at natural language intent ("how are customer payments refunded?").

`faccoder-core` integrates both through `HybridStore`:

```
               [User Query: "find customer charge method"]
                                   |
                  +----------------+----------------+
                  |                                 |
                  v                                 v
        [SQLite FTS5 BM25]                 [Dense Embeddings]
        Exact symbol match                 Semantic similarity
                  |                                 |
                  +----------------+----------------+
                                   |
                                   v
                    [Reciprocal Rank Fusion (RRF)]
                                   |
                                   v
                         [Top Ranked Results]
```

---

## 3. Reciprocal Rank Fusion (RRF)

Standard score normalization across different scoring algorithms (e.g. BM25 unbounded scores vs cosine [-1, 1]) is notoriously fragile.

`faccoder` fuses ranked lists using **Reciprocal Rank Fusion (RRF)**:

$$RRF\_Score(d) = \sum_{m \in M} \frac{1}{k + rank_m(d)}$$

Where:
- $M$ is the set of retrieval systems (FTS5 and Vector).
- $rank_m(d)$ is the position of document $d$ in system $m$ (1-indexed).
- $k$ is a smoothing constant (standard default: 60).

Items appearing near the top of both lists receive massive score boosts, while items appearing exclusively in one system still contribute meaningfully.

---

## Practical Example in faccoder

```python
from faccoder_code_intel import CodeSearchIndex
from faccoder_core.retrieval.embeddings import HashEmbedder

# 1. Initialize hybrid index
embedder = HashEmbedder(dimensions=256)
index = CodeSearchIndex("codebase.db", embedder=embedder)

# 2. Index symbol chunks
index.index_code(
    file_path="service/payment.py",
    content="class PaymentService:\n    def charge(self, amount: float): pass",
    language="python"
)

# 3. Query using hybrid retrieval with RRF
results = index.search("charge credit card", top_k=5)
for hit in results:
    print(f"Score: {hit['score']:.4f} | Chunk: {hit['id']}")
```
