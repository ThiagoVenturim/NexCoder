# Advanced RAG: HyDE, RRF, MMR and Context Compression

While basic hybrid RAG improves precision, complex developer queries require advanced techniques to resolve vocabulary mismatch, reduce context redundancy, and eliminate noise.

This guide details the advanced RAG mechanisms implemented in `faccoder-code-intel` and `faccoder-core`.

---

## 1. Hypothetical Document Embeddings (HyDE)

A major challenge in code retrieval is the **asymmetry** between query vocabulary and target code:
- Developer query: *"How do we handle expired authentication sessions?"*
- Source code: `def is_token_revoked(token_exp: int) -> bool:`

Natural language queries often embed far away from source code tokens in vector space.

### The HyDE Solution
Instead of embedding the user's raw question directly, `faccoder` calls a fast, small-tier LLM to synthesize a **Hypothetical Code Snippet**:

```
[User Question]
       |
       v
[Small LLM] -> "Generate hypothetical Python snippet implementing this"
       |
       v
[Hypothetical Code]
   "def check_session_expiry(session):
        if time.time() > session.expires_at:
            raise SessionExpiredError()"
       |
       v
[Dense Vector Embedder]
       |
       v
[Vector Search against Codebase Index]
```

Because the hypothetical document contains actual programming syntax, keyword patterns, and control flow, its dense vector matches real production functions with substantially higher recall.

In `faccoder-code-intel`:

```python
results = index.search(
    query="how do we handle expired authentication sessions?",
    top_k=5,
    hyde=True,  # Enables HyDE synthesis before vector lookup
)
```

---

## 2. Query Rewriting and Expansion

Developer queries frequently include colloquialisms, ticket numbers, or ambiguous shorthand.

Before issuing retrieval requests, `faccoder` expands the query into three complementary variations:
1. **Raw Semantic Query**: Preserved for general semantic matching.
2. **Identifier Extraction**: Extracts camelCase, snake_case, and uppercase constant names for FTS5 exact matching.
3. **Domain Synonyms**: Expands domain terms (e.g. `billing` -> `invoice`, `charge`, `payment`, `receipt`).

---

## 3. Maximal Marginal Relevance (MMR)

Standard vector search frequently suffers from **result redundancy**: if five overloaded methods or repetitive test fixtures share identical semantics, top-k retrieval fills the context window with five nearly identical variations of the same routine.

`faccoder-core` applies **Maximal Marginal Relevance (MMR)** to balance relevance with diversity:

$$MMR = \arg\max_{d_i \in R \setminus S} \left[ \lambda \cdot Sim_1(d_i, Q) - (1 - \lambda) \cdot \max_{d_j \in S} Sim_2(d_i, d_j) \right]$$

Where:
- $Q$ is the user query.
- $R$ is the candidate set of retrieved documents.
- $S$ is the set of already selected documents.
- $\lambda$ is the diversity tuning parameter (default: 0.70). A value of 1.0 is pure relevance; lower values penalize redundancy.

```python
from faccoder_core import mmr_select

# doc_embeddings: matrix/list of embedding vectors for candidate documents
# query_embedding: vector for the search query
selected_indices = mmr_select(
    doc_embeddings=candidate_vectors,
    query_embedding=query_vector,
    k=5,
    lambda_mult=0.70,
)
selected_docs = [candidate_docs[i] for i in selected_indices]
```

---

## 4. Context Compression and Scoping Filters

Shoving full source files into context windows degrades prompt attention and inflates token cost.

`faccoder-code-intel` compresses context by:
- **Signature Extraction**: For indirect dependencies, only extracting class definitions and method signatures rather than full implementations.
- **Path Sandboxing & Layer Filtering**: Filtering candidates to specific architectural layers (e.g. only searching `backend/` or `data/` based on agent persona role).
- **Enclosing Scope Stitching**: Injecting only the 2-3 enclosing scope lines above a matched symbol, providing complete context in minimal token space.
