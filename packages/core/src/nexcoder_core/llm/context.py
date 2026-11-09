"""Context window budgeting and pruning for LLM calls.

Monitors token consumption before every call, enforcing a budget (default: 60%
of the model window). When the budget is exceeded, system messages and recent turns
are kept, older turns are summarized with the small tier, tool outputs already
summarized are discarded, and pinned memory facts survive untouched.
"""

from __future__ import annotations

import math

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel

from faccoder_core.llm.memory import PinnedMemory

MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # Gemini
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.5-flash-lite": 1_000_000,
    "gemini-2.5-pro": 2_000_000,
    # Claude
    "claude-haiku-5-5": 200_000,
    "claude-sonnet-5-5": 200_000,
    "claude-opus-5-5": 200_000,
    # OpenAI
    "gpt-4.1": 128_000,
    "gpt-4.1-mini": 128_000,
    # Open Source (Qwen / Llama)
    "qwen2.5:7b-instruct": 32_768,
    "qwen2.5-coder:14b": 32_768,
    "qwen2.5-coder:32b": 32_768,
    # Test fake model default
    "echo": 1_000,
    "echo-2": 1_000,
}

DEFAULT_FALLBACK_WINDOW: int = 32_768


def get_model_context_window(model_name: str) -> int:
    """Return the context window size in tokens for a model name."""
    norm = model_name.strip().lower()
    for key, val in MODEL_CONTEXT_WINDOWS.items():
        if key in norm:
            return val
    return DEFAULT_FALLBACK_WINDOW


def count_tokens(content: str | BaseMessage | list[BaseMessage]) -> int:
    """Fast, deterministic token estimation for strings and LangChain messages."""
    if isinstance(content, list):
        return sum(count_tokens(m) for m in content)
    if isinstance(content, BaseMessage):
        text = str(content.content) if content.content is not None else ""
        return max(1, math.ceil(len(text) / 3.8)) + 4

    text = str(content)
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 3.8))


class PruneReport(BaseModel):
    original_tokens: int
    pruned_tokens: int
    saved_tokens: int
    was_pruned: bool
    discarded_tool_messages: int = 0
    summary_used: bool = False


class ContextBudget:
    """Manages token budgeting and automated pruning against model context limits."""

    def __init__(
        self,
        model_name: str = "default",
        budget_ratio: float = 0.60,
        max_tokens: int | None = None,
        keep_last_n: int = 2,
        small_model: BaseChatModel | None = None,
        pinned_memory: PinnedMemory | None = None,
    ) -> None:
        self.model_name = model_name
        self.budget_ratio = max(0.05, min(1.0, budget_ratio))
        self.max_tokens = max_tokens
        self.keep_last_n = max(1, keep_last_n)
        self.small_model = small_model
        self.pinned_memory = pinned_memory

    @property
    def effective_budget(self) -> int:
        if self.max_tokens is not None:
            return self.max_tokens
        window = get_model_context_window(self.model_name)
        return int(window * self.budget_ratio)

    def prune_messages(self, messages: list[BaseMessage]) -> tuple[list[BaseMessage], PruneReport]:
        """Check messages against budget; prune and summarize middle turns if exceeded."""
        orig_tokens = count_tokens(messages)
        budget = self.effective_budget

        if orig_tokens <= budget or len(messages) <= (self.keep_last_n + 1):
            # Budget respected or too few messages to prune
            return list(messages), PruneReport(
                original_tokens=orig_tokens,
                pruned_tokens=orig_tokens,
                saved_tokens=0,
                was_pruned=False,
            )

        # Separate system messages at the start
        system_msgs: list[BaseMessage] = []
        rest: list[BaseMessage] = []
        in_system = True
        for m in messages:
            if in_system and isinstance(m, SystemMessage):
                system_msgs.append(m)
            else:
                in_system = False
                rest.append(m)

        if len(rest) <= self.keep_last_n:
            return list(messages), PruneReport(
                original_tokens=orig_tokens,
                pruned_tokens=orig_tokens,
                saved_tokens=0,
                was_pruned=False,
            )

        split_idx = len(rest) - self.keep_last_n
        middle_msgs = rest[:split_idx]
        tail_msgs = rest[split_idx:]

        # Count and discard tool messages from middle
        discarded_tools = sum(
            1 for m in middle_msgs if isinstance(m, ToolMessage) or getattr(m, "tool_call_id", None) is not None
        )

        # Summarize middle messages
        summary_text = self._summarize_middle(middle_msgs)

        # Assemble summary message
        pinned_block = self.pinned_memory.render_block() if self.pinned_memory else ""
        summary_content = f"[Context Summary of prior steps: {summary_text}]"
        if pinned_block:
            summary_content += f"\n\n{pinned_block}"

        summary_msg = SystemMessage(content=summary_content)

        new_messages = [*system_msgs, summary_msg, *tail_msgs]
        pruned_tokens = count_tokens(new_messages)
        saved = max(0, orig_tokens - pruned_tokens)

        return new_messages, PruneReport(
            original_tokens=orig_tokens,
            pruned_tokens=pruned_tokens,
            saved_tokens=saved,
            was_pruned=True,
            discarded_tool_messages=discarded_tools,
            summary_used=True,
        )

    def _summarize_middle(self, middle_msgs: list[BaseMessage]) -> str:
        """Summarize middle messages using small model if available, else deterministic extraction."""
        if self.small_model is not None:
            dialogue_snippet = "\n".join(
                f"{m.type}: {str(m.content)[:300]}" for m in middle_msgs if not isinstance(m, ToolMessage)
            )
            prompt = (
                "Summarize the following prior conversation turns in 2-3 concise factual sentences, "
                "preserving decisions and user goals:\n" + dialogue_snippet
            )
            try:
                res = self.small_model.invoke(prompt)
                content = str(res.content).strip()
                if content:
                    return content
            except Exception:  # noqa: S110, BLE001
                pass

        # Deterministic extraction fallback
        points = []
        for m in middle_msgs:
            if isinstance(m, HumanMessage):
                points.append(f"User asked: {str(m.content)[:120]}")
            elif isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
                points.append(f"Assistant replied: {str(m.content)[:120]}")
        return " | ".join(points) if points else "Conversation history compacted."
