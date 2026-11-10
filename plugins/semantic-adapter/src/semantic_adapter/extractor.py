"""Extracción de entidades de una pregunta con salida estructurada, sobre Agno."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field

EntityKind = Literal["metric", "dimension", "filter", "time", "other"]


@dataclass(frozen=True)
class Entity:
    text: str
    kind: EntityKind = "other"


class EntityExtractor(Protocol):
    def extract(self, question: str) -> list[Entity]: ...


class _ExtractedEntity(BaseModel):
    text: str = Field(description="El concepto tal como aparece en la pregunta, sin inventar palabras")
    kind: EntityKind = Field(
        description=(
            "metric: algo que se mide o calcula; dimension: por qué se agrupa o filtra; "
            "filter: un valor concreto (un hogar, una zona); time: una referencia de tiempo; "
            "other: cualquier otra cosa"
        )
    )


class _Extraction(BaseModel):
    entities: list[_ExtractedEntity]


_INSTRUCTIONS = (
    "Extrae los conceptos de negocio que una base de datos tendría que tener para responder la "
    "pregunta. No respondas la pregunta. No agregues conceptos que la pregunta no menciona. "
    "Separa las referencias de tiempo (hoy, mañana, la semana pasada, junio de 2025) como 'time'. "
    "Devuelve solo JSON."
)


class AgnoEntityExtractor:
    """Modelo compatible con OpenAI vía ``agno.models.openai.like.OpenAILike``."""

    def __init__(self, base_url: str, api_key: str, model: str = "nemotron-3.5-lightning") -> None:
        from agno.models.openai.like import OpenAILike

        from .embedder import extra_headers

        kwargs = dict(
            id=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.0,
            max_tokens=600,
            timeout=60,
            max_retries=1,
        )
        headers = extra_headers()
        if headers:
            kwargs["default_headers"] = headers
        self.model = model
        self._model = OpenAILike(**kwargs)

    def __repr__(self) -> str:
        return f"AgnoEntityExtractor(model={self.model!r})"

    def extract(self, question: str) -> list[Entity]:
        from agno.models.message import Message

        response = self._model.response(
            messages=[
                Message(role="system", content=_INSTRUCTIONS),
                Message(role="user", content=question),
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "Extraction",
                    "schema": _Extraction.model_json_schema(),
                    "strict": False,
                },
            },
        )
        parsed = _Extraction.model_validate_json((response.content or "{}").strip() or "{}")
        return [Entity(e.text.strip(), e.kind) for e in parsed.entities if e.text.strip()]
