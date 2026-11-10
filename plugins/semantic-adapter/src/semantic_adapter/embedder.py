"""Embeddings por un endpoint compatible con OpenAI (InferNode)."""

from __future__ import annotations

import json
import os
from typing import Protocol


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str], input_type: str) -> list[list[float]]: ...


def extra_headers() -> dict[str, str] | None:
    """Encabezados del gateway (p. ej. Cloudflare Access) desde LLM_EXTRA_HEADERS_JSON."""
    raw = os.environ.get("LLM_EXTRA_HEADERS_JSON", "").strip()
    if not raw:
        return None
    headers = json.loads(raw)
    return {str(k): str(v) for k, v in headers.items()}


class OpenAICompatibleEmbedder:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "qwen3-embedding-8b",
        dimensions: int | None = 2048,
        timeout_s: float = 60,
    ) -> None:
        from openai import OpenAI

        self.model = model
        self.dimensions = dimensions
        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_s,
            max_retries=2,
            default_headers=extra_headers(),
        )

    def __repr__(self) -> str:  # nunca la llave
        return f"OpenAICompatibleEmbedder(model={self.model!r}, dimensions={self.dimensions})"

    def embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        if not texts:
            return []
        kwargs = {"dimensions": self.dimensions} if self.dimensions else {}
        response = self._client.embeddings.create(
            model=self.model,
            input=texts,
            encoding_format="float",
            extra_body={"input_type": input_type},
            **kwargs,
        )
        return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
