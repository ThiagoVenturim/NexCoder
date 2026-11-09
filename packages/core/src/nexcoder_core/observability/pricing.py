"""Token prices used to turn usage into money.

Prices are USD per one million tokens (input, output). The defaults below are
illustrative starting values: check each provider's pricing page before using
the numbers for billing. They change; override
them with ``NEXCODER_PRICES_FILE`` pointing at a YAML file with the same shape,
or edit them in the control panel. Local models (Ollama, vLLM) cost zero here:
their cost is hardware, not tokens.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (1.0, 5.0),
    "claude-sonnet-5-5": (3.0, 15.0),
    "claude-opus-5-5": (15.0, 75.0),
    "gpt-4.1-mini": (0.4, 1.6),
    "gpt-4.1": (2.0, 8.0),
    "gemini-2.5-flash-lite": (0.1, 0.4),
    "gemini-2.5-flash": (0.3, 2.5),
    "gemini-2.5-pro": (1.25, 10.0),
}


@lru_cache(maxsize=1)
def price_table() -> dict[str, tuple[float, float]]:
    table = dict(DEFAULT_PRICES)
    path = os.environ.get("NEXCODER_PRICES_FILE")
    if path and Path(path).is_file():
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        for model, value in data.items():
            table[model] = (float(value[0]), float(value[1]))
    return table


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost of one call. Unknown models (typically local ones) cost 0."""
    table = price_table()
    price = table.get(model)
    if price is None:
        # Match by prefix so dated variants ("model-2026-01-01") still resolve.
        price = next((p for name, p in table.items() if model.startswith(name)), (0.0, 0.0))
    return (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000
