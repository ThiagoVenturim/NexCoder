"""Callbacks attached to every model built by the registry."""

from __future__ import annotations

from nexcoder_core.config import NexcoderConfig
from nexcoder_core.observability.langfuse_safe import langfuse_callbacks
from nexcoder_core.observability.usage import UsageCallback


def default_callbacks(cfg: NexcoderConfig, *, tier: str, model: str) -> list:
    """Tracing plus usage metering. A model built without the usage callback
    would become spending without an owner in the cost report."""
    return [*langfuse_callbacks(cfg, tier=tier, model=model), UsageCallback(model)]
