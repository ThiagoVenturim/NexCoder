# faccoder-serving

Serving orchestration, RAG evaluation, and RAFT dataset building for faccoder.

## Features

- **Serving Compose**: Docker Compose profiles for `vllm` (GPU accelerated OpenAI-compatible endpoint) and `ollama`.
- **RAG Evaluation**: LLM judge and heuristic metrics for faithfulness, answer relevance, context precision, and context recall.
- **RAFT Dataset Builder**: Retrieval Augmented Fine-Tuning dataset generator with chain-of-thought, oracle, distractors, and PII anonymization.
