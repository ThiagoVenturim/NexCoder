# faccoder-core

Foundation shared by every faccoder package and by the sibling projects
(askdash, Support Intelligence Engine).

- Model registry with tiers (`small`, `medium`, `large`) mapped to open source
  (Ollama, vLLM, LM Studio, llama.cpp) or paid providers (Anthropic, OpenAI,
  Gemini, Azure, Bedrock, OpenRouter) through LangChain.
- Key rotation with cooldown for providers with per-key quotas.
- Langfuse tracing that degrades to a no-op when Langfuse is unavailable.
- Usage and cost metering per owner and run, with budget enforcement.
- Structured LLM calls validated against Pydantic schemas, with a corrective retry.
- Retrieval: RRF fusion, MMR, cross-encoder reranking, embedding providers.
- Local hybrid store (sqlite-vec + FTS5 BM25) and a semantic cache.
- Path sandbox for file-access tools.

```bash
pip install "faccoder-core[all]"
```

```python
from faccoder_core import get_chat_model, load_config

model = get_chat_model("medium", config=load_config())
print(model.invoke("Explain RRF in one sentence.").content)
```
