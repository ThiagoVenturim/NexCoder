"""faccoder-core: the shared foundation used by every faccoder package and by
the sibling projects (askdash, Support Intelligence Engine).

Main entry points:

- ``load_config`` / ``FaccoderConfig``: project configuration (``faccoder.yaml``).
- ``get_chat_model``: a LangChain chat model for a tier (small, medium, large),
  backed by an open source or a paid provider.
- ``call_structured``: LLM call validated against a Pydantic schema, with retry.
- ``rrf_fuse`` / ``mmr_select``: rank fusion and diversification for retrieval.
- ``HybridStore``: local vector + BM25 store on SQLite.
"""

from faccoder_core.cache import SemanticCache
from faccoder_core.config import FaccoderConfig, load_config
from faccoder_core.llm.compression import compress_messages, compress_text
from faccoder_core.llm.context import ContextBudget, count_tokens
from faccoder_core.llm.memory import PinnedMemory
from faccoder_core.llm.registry import get_chat_model
from faccoder_core.llm.tool_loader import SelectiveToolLoader
from faccoder_core.retrieval.fusion import mmr_select, rrf_fuse
from faccoder_core.sandbox import PathOutsideSandboxError, resolve_inside
from faccoder_core.structured import OutOfContractError, call_structured

__all__ = [
    "ContextBudget",
    "FaccoderConfig",
    "OutOfContractError",
    "PathOutsideSandboxError",
    "PinnedMemory",
    "SelectiveToolLoader",
    "SemanticCache",
    "call_structured",
    "compress_messages",
    "compress_text",
    "count_tokens",
    "get_chat_model",
    "load_config",
    "mmr_select",
    "resolve_inside",
    "rrf_fuse",
]

__version__ = "0.1.0"
