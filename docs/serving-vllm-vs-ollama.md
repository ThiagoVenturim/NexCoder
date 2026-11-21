# Serving: vLLM vs Ollama

> **Status**: This module is currently Planned ([Issue #11](https://github.com/ThiagoVenturim/nexcoder/issues/11)). Code examples illustrate the upcoming release API.

When running open-source models locally or on private cloud infrastructure, selecting the proper inference engine is critical for latency, throughput, and GPU utilization.

This guide provides a comparative evaluation between **vLLM** and **Ollama**, including Docker Compose configurations and hardware recommendations.

---

## Architectural Comparison

| Feature | Ollama | vLLM |
|---|---|---|
| **Core Engine** | llama.cpp (C/C++ runtime with CPU/GPU offload) | Python / CUDA with PagedAttention and continuous batching |
| **Primary Target** | Local developer laptops, single GPUs, mixed CPU+GPU environments | High-concurrency production servers, multi-GPU clusters |
| **Memory Management** | Static memory allocation; context window pre-allocated | Dynamic KV-cache memory allocation via PagedAttention |
| **Tensor Parallelism** | Limited / single-process multi-GPU | Native multi-GPU tensor parallelism (`--tensor-parallel-size`) |
| **API Format** | Custom REST API + OpenAI-compatible wrapper (`/v1`) | Full OpenAI-compatible REST API (`/v1/chat/completions`) |
| **Quantization Support** | GGUF (Q4_K_M, Q5_K_M, Q8_0) | AWQ, GPTQ, FP8, INT4, BitsAndBytes |
| **Concurrency & Throughput** | Best for 1 to 4 sequential requests | 10x-30x higher throughput under multi-agent concurrent workloads |

---

## When to Choose Which

### Choose Ollama If:
- You are developing locally on a developer workstation or laptop (macOS with Apple Silicon, or desktop with a single NVIDIA RTX 3060/4070/4090).
- You want a one-click setup (`ollama run qwen2.5-coder:14b`) without managing CUDA environments.
- You need efficient mixed CPU/GPU RAM offloading for models that slightly exceed your VRAM.

### Choose vLLM If:
- You are deploying `nexcoder` in a shared team environment or running multiple concurrent autonomous agents.
- You have dedicated GPU infrastructure (NVIDIA A10G, A100, H100, or multi-RTX 4090).
- You require continuous batching so that slow reasoning prompts do not block fast small-tier extraction requests.

---

## Production Docker Compose Setup

### Option 1: High-Throughput vLLM Stack

Create a `docker-compose.vllm.yml`:

```yaml
services:
  vllm-coder:
    image: vllm/vllm-openai:latest
    container_name: vllm-coder
    restart: unless-stopped
    runtime: nvidia
    environment:
      - HUGGING_FACE_HUB_TOKEN=${HF_TOKEN:-}
    ports:
      - "8000:8000"
    volumes:
      - ~/.cache/huggingface:/root/.cache/huggingface
    ipc: host
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    command: >
      --model Qwen/Qwen2.5-Coder-32B-Instruct
      --host 0.0.0.0
      --port 8000
      --max-model-len 16384
      --tensor-parallel-size 2
      --gpu-memory-utilization 0.90
```

Connect `nexcoder` to vLLM:

```bash
export VLLM_BASE_URL="http://localhost:8000/v1"
export VLLM_MODEL_MEDIUM="Qwen/Qwen2.5-Coder-32B-Instruct"
```

### Option 2: Lightweight Ollama Stack

Create a `docker-compose.ollama.yml`:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ~/.ollama:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

Pull the recommended models:

```bash
# Start Ollama
docker compose -f docker-compose.ollama.yml up -d

# Pull recommended tiers
docker exec -it ollama ollama pull qwen2.5:7b           # small tier
docker exec -it ollama ollama pull qwen2.5-coder:14b     # medium tier
docker exec -it ollama ollama pull qwen2.5-coder:32b     # medium/large tier
```

Connect `nexcoder` to Ollama:

```bash
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL_SMALL="qwen2.5:7b"
export OLLAMA_MODEL_MEDIUM="qwen2.5-coder:14b"
```

---

## Hardware Sizing Guidelines

| Model Architecture | Quantization | Minimum VRAM Required | Recommended GPU Setup |
|---|---|---|---|
| **Qwen 2.5 7B** (Small tier) | FP16 or INT8 | 8 GB - 16 GB | 1x RTX 3060/4060 or Apple Silicon 16GB |
| **Qwen 2.5 Coder 14B** (Medium tier) | INT4 (AWQ/GGUF) / FP16 | 12 GB - 28 GB | 1x RTX 4080/4090 or Apple Silicon 32GB |
| **Qwen 2.5 Coder 32B** (Medium/Large) | INT4 (AWQ) / FP16 | 20 GB - 64 GB | 1x RTX 4090 (AWQ) or 2x A10G / Apple Silicon 64GB |
| **Llama 3.3 70B** (Large tier) | INT4 (AWQ/GGUF) | 40 GB - 48 GB | 2x RTX 4090 or 1x A100 80GB |
