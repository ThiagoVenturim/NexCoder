---
name: ai-feature-recipes
description: Standardized parameterized pipeline recipes for implementing classification, extraction, semantic search/RAG, recommendation, summarization, and chatbots in user projects.
user-invocable: false
---

# AI Feature Recipes

This skill defines parameterized pipeline recipes that NexCoder agents apply when scaffolding AI capabilities into target codebases.

## Catalog of Standard Recipes

### 1. Classification (`classification`)
- **Purpose**: Assigns labels or categories to text inputs or tabular records (e.g., ticket triage, sentiment, spam filter).
- **Core Components**:
  - Preprocessing and tokenization / feature vectorization.
  - Predictor (linear model, gradient boosted trees, or prompt-based classification).
  - Confidence scoring and threshold gating.
  - Unit tests verifying canonical classes and ambiguous input fallback.

### 2. Information Extraction (`extraction`)
- **Purpose**: Extracts typed entities, key-value pairs, or structured JSON payloads from unstructured text.
- **Core Components**:
  - Pydantic schema validation for strict output typing.
  - Few-shot prompt formatting with JSON schema instructions.
  - Parsing fallback and sanitization handlers.
  - Unit tests verifying field coverage and malformed input handling.

### 3. Semantic Search and RAG (`rag`)
- **Purpose**: Retrieves relevant knowledge chunks and generates grounded answers with source citations.
- **Core Components**:
  - Text chunking and embedding generation.
  - Vector similarity search or hybrid SQLite/BM25 retrieval.
  - Grounded answer prompt with strict anti-hallucination constraints.
  - Unit tests measuring context retrieval precision and answer faithfulness.

### 4. Recommendation (`recommendation`)
- **Purpose**: Ranks items or actions according to user preferences, collaborative similarity, or content vectors.
- **Core Components**:
  - Feature scoring matrix or cosine similarity lookup.
  - Top-K ranking with cold-start heuristics.
  - Diversity and deduplication filters.
  - Unit tests verifying ranking order and empty history fallback.

### 5. Summarization (`summarization`)
- **Purpose**: Condenses documents, transcripts, or code changes into concise executive summaries or bullet points.
- **Core Components**:
  - Context chunking for long documents.
  - Length constraint enforcement (word/sentence targets).
  - Key takeaway extraction prompt.
  - Unit tests verifying length limits and coverage of critical facts.

### 6. Conversational Chatbot (`chatbot`)
- **Purpose**: Multi-turn conversational interface with session memory, persona instructions, and tool calling.
- **Core Components**:
  - Rolling conversation buffer with token compaction.
  - System prompt defining role and safety boundary.
  - Graceful refusal for off-topic or policy-violating queries.
  - Unit tests checking multi-turn coherence and prompt injection resistance.
