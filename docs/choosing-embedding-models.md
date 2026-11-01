# Choosing Embedding Models for Code

Selecting the right embedding model is the foundation of dense vector retrieval. Code embeddings differ substantially from standard natural language embeddings: they must represent programming language grammars, abstract symbol relationships, camelCase/snake_case tokens, and cross-language concepts.

This guide benchmarks and evaluates embedding model options supported in `faccoder`.

---

## Benchmark Matrix

| Model | Dimensions | Context Window | Hosting | Code Performance | Recommended Use Case |
|---|---|---|---|---|---|
| **BAAI/bge-m3** | 1024 | 8192 | Self-hosted (local GPU/CPU) | Outstanding | Best overall open-source model; native multi-lingual and code support |
| **nomic-ai/nomic-embed-text-v1.5** | 768 / 512 | 8192 | Self-hosted / API | Very Good | Resource-constrained workstations; Matryoshka dimension truncation |
| **voyage-code-3** | 1536 / 1024 | 16384 | Commercial API | State-of-the-art | Maximum retrieval accuracy for enterprise cloud deployments |
| **text-embedding-3-large** | 3072 / 1536 | 8192 | OpenAI API | Strong | Existing OpenAI infrastructure; Matryoshka support |
| **text-embedding-004** | 768 | 2048 | Google Cloud API | Strong | Google Cloud / Vertex AI ecosystem |
| **HashEmbedder (faccoder internal)** | 256 | N/A | Local CPU (Zero model) | Deterministic mock | Hermetic offline testing and automated CI pipelines |

---

## Key Selection Criteria

### 1. Context Window Size
Code routines (especially classes or complete interface definitions) often exceed 512 tokens. Models with an 8192+ token context window (such as `bge-m3` and `nomic-embed-text`) eliminate arbitrary chunk truncation.

### 2. Matryoshka Representation Learning (MRL)
Models supporting MRL allow truncating embedding dimensions (e.g. from 1024 down to 256 or 512) with minimal loss in accuracy. This reduces vector database RAM consumption by 50% to 75% and speeds up cosine similarity calculations.

### 3. Asymmetric Code Retrieval
Models specifically trained for code (such as `voyage-code-3` or `bge-m3` with instruction prefixes) handle the asymmetric mapping between natural language problem statements and programmatic implementations.

---

## Configuring Embeddings in faccoder

`faccoder-core` supports multiple embedding backends via `build_embedder`:

### 1. Local BGE-M3 (Sentence-Transformers)

```python
from faccoder_core.retrieval.embeddings import build_embedder

embedder = build_embedder(provider="sentence-transformers", model_name="BAAI/bge-m3", dimensions=1024)
vectors = embedder.embed_documents(["def calculate_tax(subtotal): return subtotal * 0.08"])
```

### 2. Ollama Embeddings

```python
embedder = build_embedder(provider="ollama", model_name="nomic-embed-text", base_url="http://localhost:11434")
```

### 3. Commercial API (OpenAI / Voyage)

```python
embedder = build_embedder(
    provider="openai",
    model_name="text-embedding-3-small",
    dimensions=512,  # MRL dimension truncation
)
```

### 4. Hermetic Offline Testing

```python
from faccoder_core.retrieval.embeddings import HashEmbedder

# Zero network, instant startup, deterministic outputs for tests
embedder = HashEmbedder(dimensions=256)
```
