# Reranking: Second-Stage Precision

In production code retrieval, first-stage retrieval algorithms (BM25 lexical search and bi-encoder vector embeddings) prioritize **speed** over complex interaction modeling. They scan tens of thousands of code chunks in milliseconds.

However, bi-encoders cannot model cross-attention between the query tokens and code tokens. To achieve high precision, `faccoder` uses a **two-stage retrieval pipeline** with cross-encoder reranking.

---

## Bi-Encoder vs Cross-Encoder Architecture

```
Stage 1: Bi-Encoder (Fast, Approximate)
[Query] --------> [Encoder A] --------> [Query Vector] ----+
                                                           |-> Dot Product / Cosine
[Code Chunk] ---> [Encoder B] --------> [Doc Vector]   ----+
(Separate vectors computed independently; fast vector database indexing)

Stage 2: Cross-Encoder Reranker (Slower, Highly Accurate)
[Query + Code Chunk] ---> [Full Transformer Cross-Attention] ---> [Relevance Score (0-1)]
(Every query token attends directly to every code token simultaneously)
```

---

## The Two-Stage Retrieval Pipeline

```
[User Query]
     |
     v
+------------------------------------------------+
| Stage 1: Broad Retrieval (Candidate Gathering) |
| - SQLite FTS5 BM25       -> Top 50 candidates  |
| - Dense Vector Search    -> Top 50 candidates  |
| - Reciprocal Rank Fusion -> Combined Top 30    |
+-----------------------+------------------------+
                        |
                        v
+------------------------------------------------+
| Stage 2: Cross-Encoder Reranking               |
| - BGE-Reranker-v2-M3 / Cohere / Local Cross-Enc|
| - Evaluates all 30 (Query, Chunk) pairs        |
| - Re-sorts candidates by cross-attention score |
+-----------------------+------------------------+
                        |
                        v
+------------------------------------------------+
| Final Selection: Top 5 High-Precision Chunks   |
+------------------------------------------------+
```

---

## Latency vs Precision Tradeoffs

| Stage | Algorithm | Candidates Evaluated | Typical Latency | Precision (MRR@10) |
|---|---|---|---|---|
| **Stage 1 Only** | BM25 + Vector (RRF) | Entire repository (10k+ chunks) | 5 - 15 ms | ~0.65 - 0.72 |
| **Stage 1 + Stage 2** | RRF + Cross-Encoder Rerank | Top 20 - 30 candidates | 40 - 120 ms | **0.88 - 0.94** |

By restricting the computationally expensive cross-encoder to the top 20-30 candidates, `faccoder` achieves state-of-the-art precision while keeping retrieval latency well under 150 milliseconds.

---

## Using Reranking in faccoder

`faccoder-core` provides `CrossEncoderReranker` supporting HuggingFace sentence-transformers and local endpoints:

```python
from faccoder_core.retrieval import CrossEncoderReranker

# Initialize reranker (e.g. BGE-Reranker-v2-M3)
reranker = CrossEncoderReranker(model="BAAI/bge-reranker-v2-m3")

candidates = [
    {"id": "doc1", "text": "def process_payment(amount): ..."},
    {"id": "doc2", "text": "class PaymentLogger: ..."},
    {"id": "doc3", "text": "def refund_payment(transaction_id): ..."},
]

# Rerank candidates against the query
reranked = reranker.rerank(
    query="how to issue a refund to a customer",
    docs=candidates,
    top_k=2,
)

for hit in reranked:
    print(f"Score: {hit['_rerank_score']:.4f} | ID: {hit['id']}")
```

If cross-encoder libraries are not installed or offline testing is requested, `faccoder` gracefully falls back to normalized RRF ranks without raising exceptions.
