"""Deterministic offline chat model.

Used by the test suite and by ``--dry-run`` so pipelines can be exercised end
to end without network access or cost. It can either replay scripted responses
(in order) or echo a short, stable digest of the last message.
"""

from __future__ import annotations

import hashlib
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr


class FakeChatModel(BaseChatModel):
    model_name: str = "echo"
    responses: list[Any] = []

    _calls: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "fake"

    @property
    def calls(self) -> int:
        return self._calls

    def bind_tools(self, tools: Any, **kwargs: Any) -> FakeChatModel:
        return self

    def _reply(self, messages) -> str:
        if self.responses:
            reply = self.responses[min(self._calls, len(self.responses) - 1)]
            self._calls += 1
            if isinstance(reply, Exception):
                raise reply
            return str(reply)

        last = str(messages[-1].content) if messages else ""
        digest = hashlib.sha256(last.encode("utf-8")).hexdigest()[:12]
        reply = f"[offline:{self.model_name}:{digest}] {last[:200]}"
        self._calls += 1
        return reply

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        text = self._reply(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])
