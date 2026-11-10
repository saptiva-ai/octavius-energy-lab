"""Fixtures sin red: la ontología real exportada, un embedder determinista y un extractor fijo."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

import pytest

from semantic_adapter.extractor import Entity
from semantic_adapter.ontology import load_ontology

ONTOLOGY = (
    Path(__file__).resolve().parents[3] / "semantic" / "ontologia" / "energy_lab" / "auto_ontology.yaml"
)

_DIM = 256
# Sin palabras vacías: con descripciones largas en español, "de" y "la" acercaban cualquier par de textos.
_STOPWORDS = {
    "de",
    "la",
    "el",
    "los",
    "las",
    "del",
    "y",
    "en",
    "por",
    "con",
    "a",
    "un",
    "una",
    "que",
    "se",
    "su",
    "o",
}


class HashEmbedder:
    """Bolsa de palabras con hashing: palabras compartidas acercan los vectores."""

    model = "hash-test"

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        self.calls += 1
        vectors = []
        for text in texts:
            vec = [0.0] * _DIM
            for token in re.findall(r"[a-záéíóúñ0-9]+", text.lower()):
                if token in _STOPWORDS:
                    continue
                vec[int(hashlib.sha1(token.encode()).hexdigest(), 16) % _DIM] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


class FixedExtractor:
    def __init__(self, entities: list[Entity]) -> None:
        self.entities = entities

    def extract(self, question: str) -> list[Entity]:
        return list(self.entities)


@pytest.fixture(scope="session")
def ontology():
    return load_ontology(ONTOLOGY)


@pytest.fixture()
def embedder() -> HashEmbedder:
    return HashEmbedder()
