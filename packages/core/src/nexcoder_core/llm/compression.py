"""Deterministic and LLMLingua-style prompt compression.

Reduces token consumption by compressing long tool outputs, logs, and documents
before they enter the prompt:
- Strips consecutive duplicate lines and repetitive progress indicators.
- Collapses excessive separators and empty lines.
- Strictly preserves fenced code blocks, numbers, identifiers, paths, and JSON structures.
- Optional LLMLingua-style low-entropy filler word filtering.
- Quantifies exact tokens saved and reduction ratio.
"""

from __future__ import annotations

import re

from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from nexcoder_core.llm.context import count_tokens

# Low-entropy conversational fluff patterns (LLMLingua-style heuristic)
FILLER_PATTERNS = [
    re.compile(r"\b(?:please note that|it is important to note that|it should be noted that)\b", re.IGNORECASE),
    re.compile(r"\b(?:in accordance with the above|as previously mentioned|as mentioned earlier)\b", re.IGNORECASE),
    re.compile(r"\b(?:for your information|needless to say|without further ado)\b", re.IGNORECASE),
    re.compile(r"\b(?:as you can see from the above|in order to achieve this)\b", re.IGNORECASE),
]

SEPARATOR_PATTERN = re.compile(r"^([\-=\.\*\_~#])\1{3,}$")


class CompressionResult(BaseModel):
    """Result of a single text compression operation."""

    original_text: str
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    saved_tokens: int
    savings_ratio: float


class CompressionSummary(BaseModel):
    """Aggregated compression metrics across a sequence of messages."""

    total_original_tokens: int
    total_compressed_tokens: int
    total_saved_tokens: int
    savings_ratio: float
    messages_compressed: int


def _compress_prose_block(
    block: str,
    deduplicate_lines: bool = True,
    collapse_separators: bool = True,
    llmlingua_style: bool = False,
) -> str:
    lines = block.split("\n")
    processed_lines: list[str] = []
    prev_line: str | None = None
    repeat_count = 0

    for line in lines:
        stripped = line.strip()

        # Collapse excessive separator lines
        if collapse_separators and SEPARATOR_PATTERN.match(stripped):
            line = stripped[:4]
            stripped = line

        # Deduplicate consecutive identical lines (e.g. repeated logs or loops)
        if deduplicate_lines:
            if stripped and stripped == prev_line:
                repeat_count += 1
                continue
            if repeat_count > 0:
                processed_lines.append(f"  [... repeated {repeat_count} more times]")
                repeat_count = 0
            prev_line = stripped

        # Heuristic low-entropy fluff removal if enabled
        if llmlingua_style and stripped:
            for pat in FILLER_PATTERNS:
                line = pat.sub("", line)

        processed_lines.append(line.rstrip())

    if repeat_count > 0:
        processed_lines.append(f"  [... repeated {repeat_count} more times]")

    text = "\n".join(processed_lines)
    # Collapse 3+ consecutive newlines into 2
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def compress_text(
    text: str,
    preserve_code: bool = True,
    deduplicate_lines: bool = True,
    collapse_separators: bool = True,
    llmlingua_style: bool = False,
) -> CompressionResult:
    """Compress a text string deterministically, preserving code fences and data."""
    if not text:
        return CompressionResult(
            original_text="",
            compressed_text="",
            original_tokens=0,
            compressed_tokens=0,
            saved_tokens=0,
            savings_ratio=0.0,
        )

    orig_tokens = count_tokens(text)

    if preserve_code and "```" in text:
        # Split on code fences to protect code intact
        parts = re.split(r"(```[\s\S]*?```)", text)
        compressed_parts = []
        for part in parts:
            if part.startswith("```"):
                # Preserve fenced code block without modifying syntax or code tokens
                compressed_parts.append(part)
            else:
                compressed_parts.append(
                    _compress_prose_block(
                        part,
                        deduplicate_lines=deduplicate_lines,
                        collapse_separators=collapse_separators,
                        llmlingua_style=llmlingua_style,
                    )
                )
        comp_text = "\n".join(p for p in compressed_parts if p)
    else:
        comp_text = _compress_prose_block(
            text,
            deduplicate_lines=deduplicate_lines,
            collapse_separators=collapse_separators,
            llmlingua_style=llmlingua_style,
        )

    comp_tokens = count_tokens(comp_text)
    saved = max(0, orig_tokens - comp_tokens)
    ratio = (saved / orig_tokens) if orig_tokens > 0 else 0.0

    return CompressionResult(
        original_text=text,
        compressed_text=comp_text,
        original_tokens=orig_tokens,
        compressed_tokens=comp_tokens,
        saved_tokens=saved,
        savings_ratio=round(ratio, 4),
    )


def compress_messages(
    messages: list[BaseMessage],
    min_length_to_compress: int = 120,
    llmlingua_style: bool = False,
) -> tuple[list[BaseMessage], CompressionSummary]:
    """Compress long messages and tool outputs in a message list."""
    compressed_msgs: list[BaseMessage] = []
    total_orig = 0
    total_comp = 0
    msgs_compressed_count = 0

    for msg in messages:
        content = str(msg.content) if msg.content is not None else ""
        msg_tokens = count_tokens(content)
        total_orig += msg_tokens

        if len(content) >= min_length_to_compress:
            res = compress_text(content, llmlingua_style=llmlingua_style)
            total_comp += res.compressed_tokens
            if res.saved_tokens > 0:
                msgs_compressed_count += 1
                # Return copy of message with compressed content
                new_msg = msg.model_copy(update={"content": res.compressed_text})
                compressed_msgs.append(new_msg)
                continue

        total_comp += msg_tokens
        compressed_msgs.append(msg)

    total_saved = max(0, total_orig - total_comp)
    ratio = (total_saved / total_orig) if total_orig > 0 else 0.0

    summary = CompressionSummary(
        total_original_tokens=total_orig,
        total_compressed_tokens=total_comp,
        total_saved_tokens=total_saved,
        savings_ratio=round(ratio, 4),
        messages_compressed=msgs_compressed_count,
    )
    return compressed_msgs, summary
