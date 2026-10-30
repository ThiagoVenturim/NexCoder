"""Embedding providers.

==========================  ==================================================
``sentence-transformers``   Local models (bge-m3, nomic-embed-code, jina-code).
``ollama``                  Local models served by Ollama (nomic-embed-text).
``openai`` / compatible     OpenAI, vLLM, TEI or any OpenAI-compatible server.
``voyage``                  Voyage AI (voyage-code-3).
``google``                  Gemini embeddings.
``hash``                    Deterministic, dependency-free; for tests only.
==========================  ==================================================

See ``docs/choosing-embedding-models.md`` for how to pick one.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Protocol

import httpx

from faccoder_core.config import EmbeddingSpec


class Embedder(Protocol):
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashEmbedder:
    """Feature-hashing bag of words. Not semantic, but stable and fast: good for
    tests and for exercising the pipeline without downloading a model."""

    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        for token in re.findall(r"[A-Za-z0-9_]+", text.lower()):
            digest = hashlib.md5(token.encode("utf-8"), usedforsecurity=False).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dimensions
            vec[idx] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class SentenceTransformerEmbedder:
    def __init__(self, model: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError("pip install faccoder-core[local-embeddings]") from exc
        self._model = SentenceTransformer(model)
        self.dimensions = int(self._model.get_sentence_embedding_dimension())

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True, batch_size=32).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class OpenAICompatibleEmbedder:
    """Works with OpenAI, vLLM (``--task embed``), HuggingFace TEI and similar."""

    def __init__(self, model: str, base_url: str, api_key: str | None, dimensions: int | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "not-needed"
        self.dimensions = dimensions or 0

    def _call(self, texts: list[str]) -> list[list[float]]:
        payload: dict = {"model": self.model, "input": texts}
        response = httpx.post(
            f"{self.base_url}/embeddings",
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=120,
        )
        response.raise_for_status()
        vectors = [item["embedding"] for item in sorted(response.json()["data"], key=lambda d: d["index"])]
        if vectors and not self.dimensions:
            self.dimensions = len(vectors[0])
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), 64):
            out.extend(self._call(texts[start : start + 64]))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._call([text])[0]


class OllamaEmbedder:
    def __init__(self, model: str, base_url: str):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.dimensions = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(f"{self.base_url}/api/embed", json={"model": self.model, "input": texts},
                              timeout=300)
        response.raise_for_status()
        vectors = response.json()["embeddings"]
        if vectors:
            self.dimensions = len(vectors[0])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class VoyageEmbedder:
    def __init__(self, model: str, api_key: str):
        self.model = model
        self.api_key = api_key
        self.dimensions = 0

    def _call(self, texts: list[str], input_type: str) -> list[list[float]]:
        response = httpx.post(
            "https://api.voyageai.com/v1/embeddings",
            json={"model": self.model, "input": texts, "input_type": input_type},
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=120,
        )
        response.raise_for_status()
        vectors = [item["embedding"] for item in response.json()["data"]]
        if vectors:
            self.dimensions = len(vectors[0])
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._call(texts, "document")

    def embed_query(self, text: str) -> list[float]:
        return self._call([text], "query")[0]


def build_embedder(spec: EmbeddingSpec) -> Embedder:
    provider = spec.provider.lower()
    api_key = os.environ.get(spec.api_key_env) if spec.api_key_env else None
    if provider == "hash":
        return HashEmbedder(spec.dimensions or 256)
    if provider == "sentence-transformers":
        return SentenceTransformerEmbedder(spec.model)
    if provider == "ollama":
        return OllamaEmbedder(spec.model, spec.base_url or os.environ.get("OLLAMA_BASE_URL",
                                                                           "http://localhost:11434"))
    if provider in {"openai", "openai-compatible"}:
        base_url = spec.base_url or "https://api.openai.com/v1"
        return OpenAICompatibleEmbedder(spec.model, base_url, api_key or os.environ.get("OPENAI_API_KEY"),
                                        spec.dimensions)
    if provider == "voyage":
        key = api_key or os.environ.get("VOYAGE_API_KEY")
        if not key:
            raise ValueError("VOYAGE_API_KEY is not set")
        return VoyageEmbedder(spec.model, key)
    if provider == "google":
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
        except ImportError as exc:
            raise ImportError("pip install faccoder-core[google]") from exc
        model = GoogleGenerativeAIEmbeddings(model=spec.model, google_api_key=api_key
                                             or os.environ.get("GOOGLE_API_KEY"))
        model.dimensions = spec.dimensions or 768  # type: ignore[attr-defined]
        return model  # type: ignore[return-value]
    raise ValueError(f"Unknown embedding provider '{spec.provider}'")
