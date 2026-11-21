"""Pinned memory for critical facts that survive context summarization.

Allows an agent or workflow to pin essential decisions, paths, identifiers, and
constraints into a compact memory block that is never pruned or lost when
older messages are summarized.
"""

from __future__ import annotations

import threading
import time

from pydantic import BaseModel, Field


class PinnedFact(BaseModel):
    """A single factual item protected from summarization or pruning."""

    key: str
    value: str
    category: str = "general"
    pinned_at: float = Field(default_factory=time.time)


class PinnedMemory:
    """Thread-safe store for pinned facts."""

    def __init__(self, initial_facts: list[PinnedFact] | None = None) -> None:
        self._facts: dict[str, PinnedFact] = {}
        self._lock = threading.Lock()
        if initial_facts:
            for fact in initial_facts:
                self._facts[fact.key] = fact

    def pin(self, key: str, value: str, category: str = "general") -> PinnedFact:
        """Pin or update a critical fact."""
        fact = PinnedFact(key=key, value=value, category=category, pinned_at=time.time())
        with self._lock:
            self._facts[key] = fact
        return fact

    def unpin(self, key: str) -> bool:
        """Remove a fact by key."""
        with self._lock:
            return self._facts.pop(key, None) is not None

    def get(self, key: str) -> str | None:
        """Retrieve a fact value by key."""
        with self._lock:
            fact = self._facts.get(key)
            return fact.value if fact else None

    def list_facts(self) -> list[PinnedFact]:
        """Return a snapshot of all active pinned facts sorted by category and key."""
        with self._lock:
            return sorted(self._facts.values(), key=lambda f: (f.category, f.key))

    def clear(self) -> None:
        with self._lock:
            self._facts.clear()

    def render_block(self) -> str:
        """Render facts into a compact markdown block suitable for prompt injection."""
        facts = self.list_facts()
        if not facts:
            return ""
        lines = ["[PINNED MEMORY]"]
        for f in facts:
            lines.append(f"- [{f.category}] {f.key}: {f.value}")
        return "\n".join(lines)
