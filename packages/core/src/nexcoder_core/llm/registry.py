"""Single place where chat models are built.

Every agent, pipeline step and tool asks for a *tier* (small, medium, large),
never for a vendor model. The tier resolves through ``faccoder.yaml`` to one of
the providers below, so switching a whole installation from paid to open source
models is a one-line configuration change.

Providers:

=====================  ==========================================================
``ollama``             Local open source models (Ollama).
``openai-compatible``  Any OpenAI-compatible server: vLLM, LM Studio, llama.cpp,
                       TGI, OpenRouter, Together, Groq.
``openai``             OpenAI.
``azure-openai``       Azure OpenAI.
``anthropic``          Anthropic Claude.
``google``             Google Gemini, with optional key rotation.
``bedrock``            AWS Bedrock.
``fake``               Deterministic offline model for tests and dry runs.
=====================  ==========================================================

Provider SDKs are imported lazily so that installing ``faccoder-core`` does not
pull every vendor library; install the matching extra (for example
``pip install faccoder-core[ollama]``).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from faccoder_core.config import FaccoderConfig, ModelSpec, load_config
from faccoder_core.llm.fake import FakeChatModel
from faccoder_core.llm.rotation import RotatingChatModel
from faccoder_core.observability.callbacks import default_callbacks

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class ProviderNotInstalledError(ImportError):
    def __init__(self, provider: str, extra: str):
        super().__init__(
            f"Provider '{provider}' needs an optional dependency. Install it with: pip install faccoder-core[{extra}]"
        )


def _env(name: str | None) -> str | None:
    return os.environ.get(name) if name else None


def _keys(spec: ModelSpec) -> list[str]:
    if spec.api_keys_env and os.environ.get(spec.api_keys_env):
        return [k.strip() for k in os.environ[spec.api_keys_env].split(",") if k.strip()]
    single = _env(spec.api_key_env)
    return [single] if single else []


def build_chat_model(spec: ModelSpec, callbacks: list | None = None) -> Any:
    """Instantiate a LangChain chat model from a ModelSpec."""
    if spec.fallbacks:
        primary_spec = spec.model_copy(update={"fallbacks": []})
        primary_model = build_chat_model(primary_spec, callbacks=callbacks)
        fallback_models = [build_chat_model(fb, callbacks=callbacks) for fb in spec.fallbacks]
        model_names = [spec.model, *[fb.model for fb in spec.fallbacks]]
        return RotatingChatModel(
            [primary_model, *fallback_models],
            model_names=model_names,
            fallback_chain=True,
        )

    provider = spec.provider.lower()
    common: dict[str, Any] = {"temperature": spec.temperature, **spec.extra}
    if spec.max_tokens:
        common["max_tokens"] = spec.max_tokens
    if callbacks:
        common["callbacks"] = callbacks

    if provider == "fake":
        return FakeChatModel(model_name=spec.model)

    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise ProviderNotInstalledError(provider, "ollama") from exc
        base_url = spec.base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        common.pop("max_tokens", None)
        return ChatOllama(model=spec.model, base_url=base_url, **common)

    if provider in {"openai", "openai-compatible", "openrouter"}:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise ProviderNotInstalledError(provider, "openai") from exc
        base_url = spec.base_url
        if provider == "openrouter":
            base_url = base_url or OPENROUTER_BASE_URL
        keys = _keys(spec)
        # Local OpenAI-compatible servers usually accept any key.
        api_key = keys[0] if keys else ("not-needed" if provider == "openai-compatible" else None)
        if len(keys) > 1:
            return RotatingChatModel(
                [ChatOpenAI(model=spec.model, base_url=base_url, api_key=k, max_retries=0, **common) for k in keys]
            )
        return ChatOpenAI(model=spec.model, base_url=base_url, api_key=api_key, **common)

    if provider == "azure-openai":
        try:
            from langchain_openai import AzureChatOpenAI
        except ImportError as exc:
            raise ProviderNotInstalledError(provider, "openai") from exc
        return AzureChatOpenAI(
            azure_deployment=spec.model,
            azure_endpoint=spec.base_url or os.environ.get("AZURE_OPENAI_ENDPOINT"),
            api_key=_env(spec.api_key_env or "AZURE_OPENAI_API_KEY"),
            api_version=spec.extra.pop("api_version", "2024-10-21"),
            **common,
        )

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise ProviderNotInstalledError(provider, "anthropic") from exc
        keys = _keys(spec) or [os.environ.get("ANTHROPIC_API_KEY", "")]
        if not keys[0]:
            raise ValueError("ANTHROPIC_API_KEY is not set. Add it to your environment or .env file.")
        if len(keys) > 1:
            return RotatingChatModel(
                [ChatAnthropic(model=spec.model, api_key=k, max_retries=0, **common) for k in keys]
            )
        return ChatAnthropic(model=spec.model, api_key=keys[0], **common)

    if provider == "google":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise ProviderNotInstalledError(provider, "google") from exc
        keys = _keys(spec) or [os.environ.get("GOOGLE_API_KEY", "")]
        if not keys[0]:
            raise ValueError("Set GOOGLE_API_KEYS (comma separated) or GOOGLE_API_KEY to use Gemini.")
        models = [ChatGoogleGenerativeAI(model=spec.model, google_api_key=k, max_retries=0, **common) for k in keys]
        return models[0] if len(models) == 1 else RotatingChatModel(models)

    if provider == "bedrock":
        try:
            from langchain_aws import ChatBedrockConverse
        except ImportError as exc:
            raise ProviderNotInstalledError(provider, "bedrock") from exc
        return ChatBedrockConverse(model=spec.model, **common)

    raise ValueError(
        f"Unknown provider '{spec.provider}'. Use one of: ollama, openai-compatible, openai, "
        "openrouter, azure-openai, anthropic, google, bedrock, fake."
    )


def get_chat_model(
    tier: str = "medium",
    *,
    config: FaccoderConfig | None = None,
    temperature: float | None = None,
    tracing: bool = True,
) -> Any:
    """Return the chat model configured for a tier.

    Args:
        tier: ``small``, ``medium`` or ``large``.
        config: configuration to use; defaults to the nearest ``faccoder.yaml``.
        temperature: override the spec temperature for this call site.
        tracing: attach Langfuse and usage-metering callbacks.
    """
    cfg = config or load_config()
    spec = cfg.model_for(tier)
    if temperature is not None:
        spec = spec.model_copy(update={"temperature": temperature})
    callbacks = default_callbacks(cfg, tier=tier, model=spec.model) if tracing else None
    logger.debug("chat model for tier=%s provider=%s model=%s", tier, spec.provider, spec.model)
    return build_chat_model(spec, callbacks=callbacks)
