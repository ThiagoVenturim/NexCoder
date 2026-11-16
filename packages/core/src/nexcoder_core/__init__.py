"""nexcoder-core: the shared foundation used by every nexcoder package and by
the sibling projects (askdash, Support Intelligence Engine).

Main entry points:

- ``load_config`` / ``NexcoderConfig``: project configuration (``nexcoder.yaml``).
- ``get_chat_model``: a LangChain chat model for a tier (small, medium, large),
  backed by an open source or a paid provider.
- ``call_structured``: LLM call validated against a Pydantic schema, with retry.
- ``rrf_fuse`` / ``mmr_select``: rank fusion and diversification for retrieval.
- ``HybridStore``: local vector + BM25 store on SQLite.
"""

from nexcoder_core.cache import SemanticCache
from nexcoder_core.config import AttributionSpec, NexcoderConfig, load_config
from nexcoder_core.llm.compression import compress_messages, compress_text
from nexcoder_core.llm.context import ContextBudget, count_tokens
from nexcoder_core.llm.firewall import (
    FirewallConfig,
    FirewalledChatModel,
    FirewallInspectionResult,
    FirewallViolation,
    PromptFirewall,
    PromptInjectionBlockedError,
)
from nexcoder_core.llm.memory import PinnedMemory
from nexcoder_core.llm.registry import get_chat_model
from nexcoder_core.llm.tool_loader import SelectiveToolLoader
from nexcoder_core.reports import (
    NEXDASH_CSP,
    LocalNexDashEngine,
    NexDashAuthError,
    NexDashClient,
    NexDashComputedChart,
    NexDashComputedKPI,
    NexDashCubeSpec,
    NexDashDashboardBundle,
    NexDashDimensionSpec,
    NexDashError,
    NexDashMetricSpec,
    NexDashMockMCPServer,
    NexDashModelDescriptor,
    NexDashPlanFilter,
    NexDashQueryPlan,
    NexDashTransportError,
    NexDashValidationError,
    create_nexdash_mock_transport,
    render_nexdash_html,
    safe_json_for_script,
)
from nexcoder_core.retrieval.fusion import mmr_select, rrf_fuse
from nexcoder_core.sandbox import PathOutsideSandboxError, resolve_inside
from nexcoder_core.structured import OutOfContractError, call_structured

__all__ = [
    "AttributionSpec",
    "ContextBudget",
    "FirewallConfig",
    "FirewallInspectionResult",
    "FirewallViolation",
    "FirewalledChatModel",
    "LocalNexDashEngine",
    "NEXDASH_CSP",
    "NexDashAuthError",
    "NexDashClient",
    "NexDashComputedChart",
    "NexDashComputedKPI",
    "NexDashCubeSpec",
    "NexDashDashboardBundle",
    "NexDashDimensionSpec",
    "NexDashError",
    "NexDashMetricSpec",
    "NexDashMockMCPServer",
    "NexDashModelDescriptor",
    "NexDashPlanFilter",
    "NexDashQueryPlan",
    "NexDashTransportError",
    "NexDashValidationError",
    "NexcoderConfig",
    "OutOfContractError",
    "PathOutsideSandboxError",
    "PinnedMemory",
    "PromptFirewall",
    "PromptInjectionBlockedError",
    "SelectiveToolLoader",
    "SemanticCache",
    "call_structured",
    "compress_messages",
    "compress_text",
    "count_tokens",
    "create_nexdash_mock_transport",
    "get_chat_model",
    "load_config",
    "mmr_select",
    "render_nexdash_html",
    "resolve_inside",
    "rrf_fuse",
    "safe_json_for_script",
]

__version__ = "0.1.0"
