---
name: model-serving-integration
description: Integrates implemented AI features with nexcoder-serving Docker Compose profiles (Ollama, vLLM) and nexcoder-core LLM model registry tiers.
user-invocable: false
---

# Model Serving Integration

This skill defines how NexCoder agents connect generated features to inference runtime environments, prioritizing reproducible local serving over external cloud dependencies.

## Inference Infrastructure Mapping

1. **Local Open Models (Ollama)**:
   - Default serving target for developer workstations and lightweight self-hosted deployments.
   - Profile `ollama`: launches containerized Ollama serving Qwen, Llama, or Mistral models.
   - Configuration generated via `nexcoder_serving.compose.generate_compose_config`.

2. **High-Throughput Serving (vLLM)**:
   - Production target for multi-GPU environments requiring continuous batching and PagedAttention.
   - Profile `vllm`: launches OpenAI-compatible vLLM server with FP16/AWQ quantization.

3. **Core Model Registry Integration**:
   - Client code in target projects queries `nexcoder_core.llm.registry.build_chat_model` or tier abstractions (`small`, `medium`, `large`).
   - Configuration maps model tiers to local Ollama endpoints or vLLM endpoints via standard `nexcoder.yaml`.

4. **Zero-Dependency Offline Fallback**:
   - For continuous integration and deterministic local test runs, agents configure `FakeChatModel` or rule-based mock predictors.
   - Guarantees 100% test pass rates without network calls or external GPU daemons.
