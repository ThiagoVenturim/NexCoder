"""LLM calls with a contract: ask, validate, retry once with the error, fail loudly.

Output that does not match the expected shape is handled in one place. The
retry sends the validation error back to the model, which fixes the problem
far more often than repeating the same prompt: the issue is almost always
format, rarely capability.

Usage::

    class Verdict(BaseModel):
        decision: Literal["go", "pivot", "no-go"]
        reasons: list[str]

    verdict = await call_structured(prompt, schema=Verdict, context="jury")

Ported from ApoIA (``structured_llm``).
"""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from faccoder_core.jsonx import extract_json

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_ATTEMPTS = 2


class OutOfContractError(Exception):
    """The model answered, but not in the requested format.

    Different from a network or quota error, which propagates as the provider's
    own exception.
    """

    def __init__(self, context: str, reason: str, raw: str = ""):
        self.context = context
        self.reason = reason
        self.raw = (raw or "")[:800]
        super().__init__(f"[{context}] response out of contract: {reason}")


def response_text(response: Any) -> str:
    if isinstance(response, dict) and "messages" in response:
        messages = response.get("messages") or []
        return str(getattr(messages[-1], "content", "") or "") if messages else ""
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    return str(content or "")


def validate(data: Any, schema: type[T] | None, required: list[str] | None) -> tuple[Any | None, str]:
    """Return (result, failure_reason). An empty reason means the data passed."""
    if data is None or data == {} or data == []:
        return None, "no parseable JSON in the response"
    if schema is not None:
        if not isinstance(data, dict):
            return None, f"expected an object for {schema.__name__}, got {type(data).__name__}"
        try:
            return schema.model_validate(data), ""
        except ValidationError as err:
            return None, f"does not match schema {schema.__name__}: {err}"
    if required:
        if not isinstance(data, dict):
            return None, f"expected an object with {required}, got {type(data).__name__}"
        missing = [key for key in required if not data.get(key)]
        if missing:
            return None, f"missing required fields: {', '.join(missing)}"
    return data, ""


def _schema_hint(schema: type[BaseModel] | None) -> str:
    if schema is None:
        return ""
    import json

    return (
        "\n\nRespond ONLY with a JSON object that matches this JSON Schema:\n"
        f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
    )


async def call_structured(
    prompt: str,
    *,
    llm: Any = None,
    schema: type[T] | None = None,
    required: list[str] | None = None,
    context: str = "generic",
    config: dict | None = None,
    attempts: int = DEFAULT_ATTEMPTS,
    include_schema: bool = True,
) -> Any:
    """Call the model and return data that honours the contract, or raise.

    Args:
        prompt: the formatted request.
        llm: model to use; defaults to the ``medium`` tier.
        schema: expected Pydantic class (preferred).
        required: without a schema, keys that must be present and non-empty.
        context: short stable label for logs and metrics.
        config: LangChain run config (callbacks, metadata, tags).
        attempts: total calls including the first.
        include_schema: append the JSON Schema to the prompt.
    """
    if llm is None:
        from faccoder_core.llm.registry import get_chat_model

        llm = get_chat_model("medium")

    base_prompt = prompt + (_schema_hint(schema) if include_schema else "")
    current = base_prompt
    reason, raw = "", ""
    for attempt in range(1, attempts + 1):
        response = await llm.ainvoke(current, config=config or {})
        raw = response_text(response)
        result, reason = validate(extract_json(raw), schema, required)
        if not reason:
            return result
        if attempt < attempts:
            logger.warning("[%s] out of contract (attempt %s/%s): %s", context, attempt, attempts, reason)
            current = (
                f"{base_prompt}\n\nYour previous answer was rejected: {reason}\n"
                "Answer again with ONLY the requested JSON, no text around it."
            )
    raise OutOfContractError(context, reason, raw)


def call_structured_sync(prompt: str, **kwargs: Any) -> Any:
    """Synchronous wrapper for scripts and CLIs."""
    import asyncio

    return asyncio.run(call_structured(prompt, **kwargs))
