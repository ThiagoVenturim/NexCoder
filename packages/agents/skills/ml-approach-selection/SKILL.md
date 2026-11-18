---
name: ml-approach-selection
description: Evaluates task requirements to select between deterministic rules, classical ML, and LLM/RAG architectures, favoring open-source models and cost efficiency.
user-invocable: false
---

# ML Approach Selection

This skill guides agents in determining the most appropriate technical approach for an AI/ML capability requested by a user or product team.

## Decision Matrix

Evaluate the feature against the following criteria:

| Criterion | Rule-Based | Classical ML | LLM / RAG |
| :--- | :--- | :--- | :--- |
| **Logic Nature** | Deterministic, known heuristics | Statistical patterns, correlations | Semantic reasoning, natural language |
| **Data Format** | Structured, boolean checks | Tabular, numerical, fixed vectors | Free-form text, multi-modal, docs |
| **Latency Budget** | Sub-millisecond (< 5ms) | Low latency (< 50ms) | Moderate latency (100ms - 2s) |
| **Compute Cost** | Negligible (CPU only) | Minimal (CPU or small instance) | GPU / VRAM or token costs |
| **Training Data** | None needed | Hundreds to thousands of rows | Few-shot prompts or pre-trained |
| **Interpretability** | 100% transparent | Feature importances, linear weights | Prompt traces, attention, embeddings |

## Selection Heuristics

1. **Rule-Based**:
   - Keyword matching, regex validation, business rule tables, deterministic scoring.
   - Use when exact correctness is required and edge cases are enumerable.

2. **Classical ML**:
   - Numerical classification, regression, tabular fraud detection, collaborative filtering.
   - Use when historical tabular or vector data exists and sub-50ms inference is required.

3. **LLM / RAG**:
   - Question answering over knowledge bases, open-domain summarization, multi-turn chatbots, unstructured text extraction.
   - Use when general natural language understanding and zero/few-shot synthesis are needed.

4. **Open-Weights Preference**:
   - Always favor local or open-weights models (e.g., Ollama or vLLM running Qwen, Llama, Mistral) over proprietary commercial APIs.
   - Only consider closed cloud APIs if the task demonstrably exceeds local hardware capacity and the budget policy explicitly permits it.
