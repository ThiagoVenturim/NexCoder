"""Query rewriting and Hypothetical Document Embeddings (HyDE) for code search."""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class RewrittenQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    original_query: str
    expanded_text: str
    keywords: list[str] = Field(default_factory=list)
    symbol_hints: list[str] = Field(default_factory=list)


# Common abbreviation and synonym mappings in code intelligence
TECHNICAL_SYNONYMS: dict[str, list[str]] = {
    "auth": ["authenticate", "authentication", "login", "credential", "token", "jwt"],
    "db": ["database", "repository", "sql", "store", "connection"],
    "calc": ["calculate", "computation", "compute", "total", "sum"],
    "cfg": ["config", "configuration", "settings", "options"],
    "msg": ["message", "payload", "event", "notification"],
    "req": ["request", "param", "payload"],
    "resp": ["response", "result", "output"],
    "usr": ["user", "account", "profile"],
    "err": ["error", "exception", "failure"],
    "tax": ["tax_rate", "vat", "invoice", "tributo"],
}


class QueryRewriter:
    """Expands technical terminology, acronyms, and extracts code entity hints."""

    def rewrite(self, query: str) -> RewrittenQuery:
        tokens = re.findall(r"[A-Za-z0-9_]+", query)
        symbol_hints: list[str] = []
        synonyms: list[str] = []

        for token in tokens:
            lower = token.lower()
            # Extract camelCase or snake_case as potential symbol hints
            if "_" in token or any(c.isupper() for c in token[1:]):
                symbol_hints.append(token)

            if lower in TECHNICAL_SYNONYMS:
                synonyms.extend(TECHNICAL_SYNONYMS[lower])

        unique_keywords = list(dict.fromkeys(tokens + synonyms))
        expanded = " ".join(unique_keywords)

        return RewrittenQuery(
            original_query=query,
            expanded_text=expanded,
            keywords=unique_keywords,
            symbol_hints=symbol_hints,
        )


class HyDEGenerator:
    """Hypothetical Document Embeddings generator for code search.

    Generates synthetic code snippets/docstrings representing the target implementation
    so embedding retrieval matches code patterns rather than conversational queries.
    """

    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm

    def generate_hypothetical_code(self, query: str, language: str = "python") -> str:
        """Synthesize a hypothetical code implementation matching user query."""
        if self.llm is not None:
            prompt = (
                f"Write a short, realistic {language} function signature, docstring, and implementation "
                f"for the following task: {query}\n"
                f"Output only code without markdown formatting."
            )
            try:
                response = self.llm.invoke(prompt)
                content = getattr(response, "content", str(response)).strip()
                if content:
                    return content
            except Exception as exc:
                logger.debug("LLM code generation fallback: %s", exc)

        return self._heuristic_code_synthesis(query, language)

    def _heuristic_code_synthesis(self, query: str, language: str) -> str:
        """Deterministic offline synthetic code generator."""
        tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9]+", query) if len(t) > 2]
        func_name = "_".join(tokens[:4]) if tokens else "process_operation"
        class_name = "".join(t.capitalize() for t in tokens[:3]) or "Service"

        if language in {"delphi", "pascal"}:
            return f"function T{class_name}.{func_name}: Boolean;\nbegin\n  // {query}\n  Result := True;\nend;"
        if language in {"typescript", "javascript"}:
            return (
                f"export async function {func_name}(params: any): Promise<boolean> {{\n  // {query}\n  return true;\n}}"
            )
        # Default Python
        return f'def {func_name}(*args, **kwargs) -> bool:\n    """{query}"""\n    return True\n'
