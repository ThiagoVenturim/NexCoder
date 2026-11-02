# Models: Open-Source vs Paid

`faccoder` is designed to be provider-neutral. It supports both self-hosted open-source models (via Ollama, vLLM, LM Studio, llama.cpp) and paid commercial APIs (Anthropic, OpenAI, Google Gemini, AWS Bedrock, Microsoft Azure).

This guide explains how `faccoder` abstracts model selection, compares cost-to-performance tradeoffs, and provides configuration best practices.

---

## The Three-Tier Model Strategy

Rather than configuring individual model names (e.g. `gpt-4o`, `claude-3-5-sonnet`, `llama-3.1-70b`) throughout your code, `faccoder` maps workflows to three capability tiers:

| Tier | Capability Profile | Typical Open-Source Models | Typical Paid Commercial Models | Primary Workloads in faccoder |
|---|---|---|---|---|
| `small` | Fast, low latency, economical, high throughput | Llama 3.2 3B, Qwen 2.5 7B, Mistral 7B | Claude 3.5 Haiku, GPT-4o mini, Gemini 1.5 Flash | Query expansion, chunk tagging, routing, schema extraction, unit test drafting |
| `medium` | Strong reasoning, precise code generation, long context | Qwen 2.5 Coder 32B, Llama 3.3 70B, DeepSeek V2.5 | Claude 3.5 Sonnet, GPT-4o, Gemini 1.5 Pro | AST analysis, refactoring, feature implementation, pipeline validation |
| `large` | Frontier intelligence, complex debate, architectural judgment | DeepSeek R1, Llama 3.1 405B (quantized) | Claude 3 Opus, o1, Gemini 1.5 Pro (high-thinking) | Multi-persona jury review, PRD synthesis, security audit triage, system architecture |

---

## Provider Comparison Matrix

| Evaluation Dimension | Self-Hosted Open-Source (vLLM / Ollama) | Paid Commercial APIs (Anthropic / OpenAI / Google) |
|---|---|---|
| **Data Privacy & Compliance** | 100% on-premises; zero data egress; complies with strict air-gapped security policies | Requires vendor trust, DPA agreements, and zero data-retention options |
| **Inference Cost** | Fixed hardware CAPEX or GPU cloud lease; zero per-token incremental costs | Variable OPEX based on input/output tokens; cost scales directly with usage |
| **Latency and Throughput** | Highly deterministic with vLLM PagedAttention and continuous batching | Subject to provider rate limits, regional queuing, and network latency |
| **Setup & Maintenance Overhead** | Requires GPU provisioning, CUDA management, driver updates, and container orchestration | Zero operational infrastructure; immediate availability via API key |
| **Frontier Reasoning Peak** | Leading models (Qwen 2.5 Coder 32B, Llama 3.3 70B) approach frontier performance on code | Frontier commercial models maintain slight advantages in multi-step jury debates |

---

## Configuring Providers in faccoder

Providers are configured via environment variables and loaded through `FaccoderConfig`:

### 1. Paid Commercial Configuration

```bash
# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_MODEL_SMALL="claude-3-5-haiku-latest"
export ANTHROPIC_MODEL_MEDIUM="claude-3-5-sonnet-latest"
export ANTHROPIC_MODEL_LARGE="claude-3-5-sonnet-latest"

# OpenAI
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL_SMALL="gpt-4o-mini"
export OPENAI_MODEL_MEDIUM="gpt-4o"
export OPENAI_MODEL_LARGE="o1-preview"

# Google Gemini
export GOOGLE_API_KEY="AIza..."
export GOOGLE_MODEL_SMALL="gemini-1.5-flash"
export GOOGLE_MODEL_MEDIUM="gemini-1.5-pro"
export GOOGLE_MODEL_LARGE="gemini-1.5-pro"
```

### 2. Open-Source Local Configuration

```bash
# Ollama
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL_SMALL="qwen2.5:7b"
export OLLAMA_MODEL_MEDIUM="qwen2.5-coder:32b"
export OLLAMA_MODEL_LARGE="llama3.3:70b"

# vLLM (OpenAI-compatible server)
export VLLM_BASE_URL="http://localhost:8000/v1"
export VLLM_API_KEY="EMPTY"
export VLLM_MODEL_SMALL="Qwen/Qwen2.5-7B-Instruct"
export VLLM_MODEL_MEDIUM="Qwen/Qwen2.5-Coder-32B-Instruct"
export VLLM_MODEL_LARGE="meta-llama/Llama-3.3-70B-Instruct"
```

---

## The Hybrid Recommendation

For enterprise production deployments, `faccoder` recommends the `hybrid` preset:

1. **Volume Tier (Local / Open-Source)**:
   - Use local vLLM or Ollama for parsing, summarization, query generation, and symbol chunking.
   - Processing millions of lines of code or running high-frequency background watchers incurs zero API billing.
2. **Quality Tier (Commercial APIs)**:
   - Route architectural design reviews, security vulnerability triage, and executive jury voting to frontier models (Claude 3.5 Sonnet or Gemini 1.5 Pro).
   - This keeps overall project costs negligible (typically less than $1-2 per complete feature PRD) while ensuring top-tier code quality.
