"""Índice de embeddings sobre términos y columnas de la ontología.

Es chico (decenas de documentos), así que la búsqueda es un coseno en Python.
Los vectores se guardan en caché por versión de la ontología y modelo de
embeddings: reiniciar el plugin no vuelve a llamar al endpoint.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .embedder import Embedder
from .ontology import Ontology


@dataclass(frozen=True)
class Hit:
    term: str
    table: str | None
    column: str | None
    kind: str  # "term" o "column"
    text: str
    score: float  # coseno en [0, 1]

    def as_dict(self) -> dict:
        return {
            "term": self.term,
            "table": self.table,
            "column": self.column,
            "kind": self.kind,
            "text": self.text,
            "score": round(self.score, 4),
        }


def _documents(ontology: Ontology) -> list[dict]:
    docs = []
    for term in ontology.terms:
        table = term.tables[0] if term.tables else None
        docs.append(
            {
                "term": term.name,
                "table": table,
                "column": None,
                "kind": "term",
                "text": f"{term.name}. {term.description} Vista {table or ''}.".strip(),
            }
        )
        for column in term.columns:
            physical = column.column.rsplit(".", 1)[-1]
            docs.append(
                {
                    "term": term.name,
                    "table": column.column.rsplit(".", 1)[0],
                    "column": column.column,
                    "kind": "column",
                    "text": (
                        f"{term.name} · {column.name} ({physical}, {column.column}): {column.description}"
                    ),
                }
            )
    return docs


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return max(0.0, dot / norm) if norm else 0.0


class SemanticIndex:
    def __init__(self, ontology: Ontology, embedder: Embedder, cache_dir: Path | None = None) -> None:
        self.ontology = ontology
        self.embedder = embedder
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self._docs = _documents(ontology)
        self._vectors: list[list[float]] | None = None

    def _cache_file(self) -> Path | None:
        if self.cache_dir is None:
            return None
        safe_model = "".join(c if c.isalnum() or c in "-." else "_" for c in self.embedder.model)
        return self.cache_dir / f"indice-{self.ontology.version}-{safe_model}.json"

    def _ensure_vectors(self) -> list[list[float]]:
        if self._vectors is not None:
            return self._vectors
        cache = self._cache_file()
        texts = [d["text"] for d in self._docs]
        if cache and cache.exists():
            stored = json.loads(cache.read_text(encoding="utf-8"))
            if stored.get("texts") == texts:
                self._vectors = stored["vectors"]
                return self._vectors
        self._vectors = self.embedder.embed(texts, "passage")
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"texts": texts, "vectors": self._vectors}), encoding="utf-8")
        return self._vectors

    def search(self, query: str, limit: int = 5) -> list[Hit]:
        vectors = self._ensure_vectors()
        [query_vector] = self.embedder.embed([query], "query")
        scored = sorted(
            ((_cosine(query_vector, vector), doc) for vector, doc in zip(vectors, self._docs, strict=True)),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return [Hit(score=score, **doc) for score, doc in scored[: max(1, limit)]]
