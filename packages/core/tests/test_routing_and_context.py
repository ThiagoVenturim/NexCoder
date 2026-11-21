from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from nexcoder_core.cache import SemanticCache
from nexcoder_core.config import ModelSpec
from nexcoder_core.llm.compression import compress_messages, compress_text
from nexcoder_core.llm.context import ContextBudget
from nexcoder_core.llm.fake import FakeChatModel
from nexcoder_core.llm.memory import PinnedMemory
from nexcoder_core.llm.registry import build_chat_model
from nexcoder_core.llm.rotation import RotatingChatModel, classify_error, requested_wait
from nexcoder_core.llm.tool_loader import SelectiveToolLoader, ToolUsageTracker
from nexcoder_core.observability.usage import usage_scope
from nexcoder_core.retrieval.embeddings import HashEmbedder
from nexcoder_core.store.sqlite_store import HybridStore


def test_classify_error_and_requested_wait():
    assert classify_error("429 RESOURCE_EXHAUSTED retry in 7s") == "quota"
    assert classify_error("HTTP 429: Rate limit exceeded") == "quota"
    assert classify_error("context_length_exceeded: maximum context length is 8192") == "context"
    assert classify_error("Estouro de contexto na requisicao") == "context"
    assert classify_error("404 model not found") == "model"
    assert classify_error("503 Service Unavailable") == "transient"
    assert classify_error("invalid auth token") == "fatal"

    # Requested wait formats
    assert requested_wait("retry in 7s", 0) == 8.0
    assert requested_wait("retry in 12.5s", 0) == 13.5
    assert requested_wait("Quota exceeded. Resets in 3h53m18s.", 0) == 3 * 3600 + 53 * 60 + 18 + 1.0
    assert requested_wait("Resets in 45m", 0) == 45 * 60 + 1.0
    assert requested_wait("Resets in 30s", 0) == 31.0


def test_fallback_chain_rotates_on_quota_and_records_usage():
    # Model A raises quota error; Model B succeeds
    model_a = FakeChatModel(model_name="gemini-flash", responses=[RuntimeError("429 RESOURCE_EXHAUSTED retry in 10s")])
    model_b = FakeChatModel(model_name="claude-sonnet", responses=["Answer from fallback model B"])

    rotating = RotatingChatModel(
        [model_a, model_b],
        model_names=["gemini-flash", "claude-sonnet"],
        fallback_chain=True,
    )

    with usage_scope(owner="test-runner") as meter:
        result = rotating.invoke("Analyze issue")
        assert result.content == "Answer from fallback model B"

        # Model A should have been cooled down, and fallback recorded in usage meter
        assert len(meter.fallbacks) == 1
        fb = meter.fallbacks[0]
        assert fb["source_model"] == "gemini-flash"
        assert fb["target_model"] == "claude-sonnet"
        assert fb["reason"] == "quota"
        assert fb["wait_seconds"] == 11.0

    # Next call within cooldown window should automatically pick model B directly
    model_b.responses.append("Second answer from model B")
    second_result = rotating.invoke("Next prompt")
    assert second_result.content == "Second answer from model B"


def test_build_chat_model_with_fallbacks_from_spec():
    spec = ModelSpec(
        provider="fake",
        model="primary-echo",
        fallbacks=[
            ModelSpec(provider="fake", model="fallback-echo"),
        ],
    )
    model = build_chat_model(spec)
    assert isinstance(model, RotatingChatModel)
    assert model.fallback_chain is True
    assert model._model_names == ["primary-echo", "fallback-echo"]


def test_context_window_budget_pruning_and_pinned_memory():
    pinned = PinnedMemory()
    pinned.pin("arch", "Clean Architecture with tiered fallback", category="decision")
    pinned.pin("target_file", "packages/core/src/nexcoder_core/llm/context.py", category="path")

    # Set small budget of 60 tokens to force pruning
    budgeter = ContextBudget(
        model_name="echo",
        max_tokens=60,
        keep_last_n=2,
        pinned_memory=pinned,
    )

    tool_content = "\n".join(f"Line {i}: function parse_record_{i}(); begin process({i}); end;" for i in range(100))

    messages = [
        SystemMessage(content="You are a senior developer."),
        HumanMessage(content="Step 1: Let us read the specification in detail."),
        AIMessage(content="Understood. Calling read_file tool."),
        ToolMessage(content=tool_content, tool_call_id="call-1"),
        HumanMessage(content="Step 2: Please create the file now."),
        AIMessage(content="Creating the file now."),
    ]

    pruned_msgs, report = budgeter.prune_messages(messages)
    assert report.was_pruned is True
    assert report.discarded_tool_messages == 1
    assert report.saved_tokens > 0

    # System message must be preserved
    assert isinstance(pruned_msgs[0], SystemMessage)
    assert "senior developer" in pruned_msgs[0].content

    # Summary message must contain the pinned memory facts
    summary_msg = pruned_msgs[1]
    assert "[Context Summary" in summary_msg.content
    assert "[PINNED MEMORY]" in summary_msg.content
    assert "Clean Architecture with tiered fallback" in summary_msg.content
    assert "packages/core/src/nexcoder_core/llm/context.py" in summary_msg.content

    # Recent turns (tail) must be preserved intact
    assert pruned_msgs[-2].content == "Step 2: Please create the file now."
    assert pruned_msgs[-1].content == "Creating the file now."


def test_context_budget_respects_sufficient_tokens():
    budgeter = ContextBudget(model_name="gemini-2.5-flash", budget_ratio=0.60)
    messages = [
        SystemMessage(content="System prompt."),
        HumanMessage(content="Short query."),
    ]
    pruned, report = budgeter.prune_messages(messages)
    assert report.was_pruned is False
    assert len(pruned) == 2


def test_selective_tool_loader():
    tracker = ToolUsageTracker()
    loader = SelectiveToolLoader(always_include={"read_file", "request_tool"}, tracker=tracker)

    all_tools = [
        {"name": "read_file", "description": "Reads a file."},
        {"name": "request_tool", "description": "Requests an on-demand tool."},
        {"name": "heavy_browser_crawler", "description": "Crawls web pages."},
        {"name": "sql_generator", "description": "Generates SQL queries."},
    ]

    agent_id = "agent-developer"

    # Initial load: only always_include tools are active; others are in on_demand manifest
    result = loader.load_tools(agent_id, all_tools)
    assert set(result.active_names) == {"read_file", "request_tool"}
    assert set(result.on_demand_names) == {"heavy_browser_crawler", "sql_generator"}
    assert "heavy_browser_crawler" in result.manifest

    # Agent requests sql_generator on-demand
    activated = loader.request_tool(agent_id, "sql_generator", all_tools)
    assert activated is not None
    assert activated["name"] == "sql_generator"

    # Next load: sql_generator is now active because it was recorded as used
    second_result = loader.load_tools(agent_id, all_tools)
    assert set(second_result.active_names) == {"read_file", "request_tool", "sql_generator"}
    assert set(second_result.on_demand_names) == {"heavy_browser_crawler"}


def test_tool_result_caching_in_semantic_cache(tmp_path):
    embedder = HashEmbedder(64)
    store = HybridStore(tmp_path / "tool_cache.sqlite", dimensions=64)
    cache = SemanticCache(store, embedder, ttl_seconds=3600)

    tool_name = "fetch_git_status"
    args = {"repo": "nexcoder", "branch": "layer/core"}

    # Initially cache miss
    assert cache.get_tool_result(tool_name, args) is None

    # Cache result
    result_text = "On branch layer/core\nnothing to commit, working tree clean"
    assert cache.cache_tool_result(tool_name, args, result_text, ttl_seconds=60) is True

    # Immediate cache hit without calling any model or tool
    cached_val = cache.get_tool_result(tool_name, args)
    assert cached_val == result_text

    # Different arguments should miss
    diff_args = {"repo": "nexcoder", "branch": "layer/planning"}
    assert cache.get_tool_result(tool_name, diff_args) is None

    # Error results must not be cached
    error_result = (
        "Traceback (most recent call last):\n  File 'test.py', line 1, in <module>\nRuntimeError: connection lost"
    )
    assert cache.cache_tool_result("db_query", {"query": "SELECT 1"}, error_result) is False
    assert cache.get_tool_result("db_query", {"query": "SELECT 1"}) is None


def test_prompt_compression_deduplication_and_code_preservation():
    raw_text = (
        "Starting test execution...\n"
        "Loading module...\n"
        "Loading module...\n"
        "Loading module...\n"
        "Loading module...\n"
        "----------------------------------------\n"
        "----------------------------------------\n"
        "----------------------------------------\n"
        "```python\n"
        "def compute_total(items: list[int]) -> int:\n"
        "    # Code must remain untouched\n"
        "    return sum(items)\n"
        "```\n"
        "Process finished with code 0.\n"
    )

    result = compress_text(raw_text, preserve_code=True, deduplicate_lines=True)
    assert result.saved_tokens > 0
    assert result.savings_ratio > 0.15
    assert "def compute_total(items: list[int]) -> int:" in result.compressed_text
    assert "[... repeated 3 more times]" in result.compressed_text

    # Test compress_messages
    msgs = [
        HumanMessage(content="Short question"),
        ToolMessage(content=raw_text, tool_call_id="call-42"),
    ]
    comp_msgs, summary = compress_messages(msgs, min_length_to_compress=50)
    assert summary.messages_compressed == 1
    assert summary.total_saved_tokens > 0
    assert "compute_total" in comp_msgs[1].content
