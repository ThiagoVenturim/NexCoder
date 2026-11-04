"""Ready-made model presets.

A preset maps the three tiers to concrete models:

- ``small``: classification, routing, extraction, short summaries. Cheap and fast.
- ``medium``: most agent work: writing code, reviewing, drafting documents.
- ``large``: planning, architecture, juries, hard debugging.

Model names change often. Treat these as sensible defaults and override them in
``faccoder.yaml`` when a provider retires or releases a model.
"""

from __future__ import annotations

PRESETS: dict[str, dict] = {
    # Everything runs on your machine through Ollama. No data leaves the host.
    "all-open-source": {
        "description": "Local models through Ollama. Private and free to run; needs a capable GPU for the large tier.",
        "tiers": {
            "small": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
            "medium": {"provider": "ollama", "model": "qwen2.5-coder:14b"},
            "large": {"provider": "ollama", "model": "qwen2.5-coder:32b"},
        },
    },
    # Local models served by vLLM (OpenAI-compatible API). Best throughput on a GPU server.
    "local-vllm": {
        "description": "Models served by vLLM on an OpenAI-compatible endpoint.",
        "tiers": {
            "small": {
                "provider": "openai-compatible",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "base_url": "http://localhost:8000/v1",
                "api_key_env": "VLLM_API_KEY",
            },
            "medium": {
                "provider": "openai-compatible",
                "model": "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
                "base_url": "http://localhost:8000/v1",
                "api_key_env": "VLLM_API_KEY",
            },
            "large": {
                "provider": "openai-compatible",
                "model": "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ",
                "base_url": "http://localhost:8000/v1",
                "api_key_env": "VLLM_API_KEY",
            },
        },
    },
    # Hosted frontier models. Highest quality, pay per token.
    "all-paid": {
        "description": "Hosted models from Anthropic. Highest quality; billed per token.",
        "tiers": {
            "small": {"provider": "anthropic", "model": "claude-haiku-5-5", "api_key_env": "ANTHROPIC_API_KEY"},
            "medium": {"provider": "anthropic", "model": "claude-sonnet-5-5", "api_key_env": "ANTHROPIC_API_KEY"},
            "large": {"provider": "anthropic", "model": "claude-opus-5-5", "api_key_env": "ANTHROPIC_API_KEY"},
        },
    },
    # Cheap local model for routine work, paid models where quality matters most.
    "hybrid": {
        "description": "Local small tier, hosted medium and large tiers.",
        "tiers": {
            "small": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
            "medium": {"provider": "anthropic", "model": "claude-sonnet-5-5", "api_key_env": "ANTHROPIC_API_KEY"},
            "large": {"provider": "anthropic", "model": "claude-opus-5-5", "api_key_env": "ANTHROPIC_API_KEY"},
        },
    },
    "gemini": {
        "description": "Google Gemini models with fallback chains and key rotation.",
        "tiers": {
            "small": {
                "provider": "google",
                "model": "gemini-2.5-flash-lite",
                "api_keys_env": "GOOGLE_API_KEYS",
                "fallbacks": [
                    {"provider": "google", "model": "gemini-2.5-flash", "api_keys_env": "GOOGLE_API_KEYS"},
                ],
            },
            "medium": {
                "provider": "google",
                "model": "gemini-2.5-flash",
                "api_keys_env": "GOOGLE_API_KEYS",
                "fallbacks": [
                    {"provider": "google", "model": "gemini-2.5-pro", "api_keys_env": "GOOGLE_API_KEYS"},
                ],
            },
            "large": {
                "provider": "google",
                "model": "gemini-2.5-pro",
                "api_keys_env": "GOOGLE_API_KEYS",
            },
        },
    },
    "openai": {
        "description": "OpenAI hosted models.",
        "tiers": {
            "small": {"provider": "openai", "model": "gpt-4.1-mini", "api_key_env": "OPENAI_API_KEY"},
            "medium": {"provider": "openai", "model": "gpt-4.1", "api_key_env": "OPENAI_API_KEY"},
            "large": {"provider": "openai", "model": "gpt-4.1", "api_key_env": "OPENAI_API_KEY"},
        },
    },
    # Deterministic fake model. Used by tests and by --dry-run to exercise pipelines for free.
    "offline": {
        "description": "Deterministic fake model for tests and dry runs. Makes no network calls.",
        "tiers": {
            "small": {"provider": "fake", "model": "echo"},
            "medium": {"provider": "fake", "model": "echo"},
            "large": {"provider": "fake", "model": "echo"},
        },
    },
}
