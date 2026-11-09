# Model Routing and Context Window Optimization

This guide covers model fallback chains, quota-based routing, context window budgeting, selective tool loading, pinned memory, and prompt compression in `nexcoder-core`.

---

## 1. Quota-Based Model Routing and Fallback Chains

Long-running pipelines and autonomous agents frequently encounter provider rate limits (HTTP 429), quota exhaustion, or context overflow on individual models. The `RotatingChatModel` in `nexcoder-core` resolves this by executing a prioritized fallback chain across providers.

### How it works:
1. **Error Classification**: Error messages are inspected for quota triggers (`429`, `resource_exhausted`, `rate limit`), context overflow (`context_length_exceeded`, `maximum context length`), model errors (`404`), and transient network blips (`500`, `503`, `timeout`).
2. **Dynamic Cooldown**: When a provider informs a reset duration (e.g., `retry in 10s` or `resets in 3h53m18s`), the exhausted model instance is placed into cooldown until the specified timestamp.
3. **Immediate Failover**: Calls automatically fail over to the next candidate in the fallback chain without failing the pipeline. Subsequent calls skip cooled-down models until their reset time arrives.
4. **Audit and Metering**: Every fallback event records `source_model`, `target_model`, `reason`, and `wait_seconds` in the active `UsageMeter` and emits a warning log trace.

### Configuration in `nexcoder.yaml`:
```yaml
preset: gemini
tiers:
  medium:
    provider: google
    model: gemini-2.5-flash
    api_keys_env: GOOGLE_API_KEYS
    fallbacks:
      - provider: anthropic
        model: claude-sonnet-5-5
        api_key_env: ANTHROPIC_API_KEY
      - provider: ollama
        model: qwen2.5-coder:32b
```

---

## 2. Context Window Budgeting and Automated Pruning

To keep token costs manageable and prevent prompt overflow, `ContextBudget` monitors the conversation history before each call and enforces a budget (default: 60% of the model window).

### Pruning Strategy:
- **System Prompts**: System messages at the head of the history are strictly preserved.
- **Recent Turns**: The last $N$ turns (configured by `keep_last_n`, default 2) remain fully intact to preserve immediate conversational context.
- **Middle Turns**: Older conversational messages in the middle are summarized into a concise summary block using the small tier model or deterministic extraction.
- **Tool Outputs**: Verbose tool outputs (e.g. large file reads or command traces) in middle turns are discarded once covered by the summary.

```python
from nexcoder_core.llm.context import ContextBudget
from langchain_core.messages import SystemMessage, HumanMessage

budgeter = ContextBudget(model_name="gemini-2.5-flash", budget_ratio=0.60)
pruned_messages, report = budgeter.prune_messages(messages)
if report.was_pruned:
    print(f"Saved {report.saved_tokens} tokens across {report.discarded_tool_messages} discarded tool messages.")
```

---

## 3. Pinned Memory

When context is compacted or summarized, critical architectural decisions, identifiers, and file paths must not be lost. `PinnedMemory` provides a thread-safe registry for essential facts that are injected directly into preserved system context.

```python
from nexcoder_core.llm.memory import PinnedMemory

memory = PinnedMemory()
memory.pin("architecture", "Clean Architecture with tiered fallback", category="decision")
memory.pin("active_pr", "#50", category="id")
memory.pin("target_file", "packages/core/src/nexcoder_core/llm/context.py", category="path")

# The rendered block survives any context summarization
print(memory.render_block())
# [PINNED MEMORY]
# - [decision] architecture: Clean Architecture with tiered fallback
# - [id] active_pr: #50
# - [path] target_file: packages/core/src/nexcoder_core/llm/context.py
```

---

## 4. Selective Tool and MCP Server Loading

Registering dozens of tool schemas and MCP servers inflates system prompts and consumes thousands of tokens per turn. `SelectiveToolLoader` tracks tool usage per agent:

- **Always Active**: A small core set (e.g. `read_file`, `request_tool`) is always loaded.
- **Usage-Based**: Tools that the agent has actually invoked across recent runs remain active.
- **On-Demand Manifest**: Unused tools are stripped of their verbose schemas and summarized into a lightweight name catalog. When an agent needs an on-demand tool, it invokes `request_tool(name)` to activate it.

```python
from nexcoder_core.llm.tool_loader import SelectiveToolLoader, ToolUsageTracker

tracker = ToolUsageTracker()
loader = SelectiveToolLoader(always_include={"read_file", "request_tool"}, tracker=tracker)

result = loader.load_tools(agent_id="code-reviewer", available_tools=all_tools)
# result.active_tools contains only active schemas
# result.manifest contains lightweight on-demand descriptions
```

---

## 5. Tool Result Caching

Repeated tool invocations (such as file reads or git status checks with identical inputs) are cached in `SemanticCache`:

- **Deterministic Hash**: Tool name and sorted JSON arguments are hashed with SHA-256.
- **TTL Validity**: Cached entries expire after `ttl_seconds` (default: 3600 seconds).
- **Error Guard**: Results containing stack traces, runtime exceptions, or error markers are never cached.
- **Zero Cost**: Cache hits bypass both tool execution and model token consumption.

```python
cache.cache_tool_result("git_status", {"branch": "main"}, status_output, ttl_seconds=60)
cached = cache.get_tool_result("git_status", {"branch": "main"})
```

---

## 6. Deterministic Prompt Compression

Before large tool outputs or external documents enter prompts, `PromptCompressor` strips redundant text deterministically:

- Deduplicates consecutive identical lines (e.g., repeated build logs or progress outputs).
- Collapses excessive separator bars (`----`, `====`, `....`).
- Preserves code blocks (fenced with ```) intact without syntax modifications.
- Optional LLMLingua-style low-entropy filler phrase filtering.
- Quantifies exact tokens saved and reduction ratio.

```python
from nexcoder_core.llm.compression import compress_text

res = compress_text(long_log_output, preserve_code=True)
print(
    f"Compressed {res.original_tokens} -> {res.compressed_tokens} tokens (saved: {res.saved_tokens}, ratio: {res.savings_ratio:.1%})"
)
```
