"""Búsqueda de términos y verificación de respondibilidad sobre la ontología.

``check_answerable`` no responde la pregunta ni escribe SQL: dice si la
ontología cubre los conceptos que la pregunta necesita. Las referencias de
tiempo no cuentan contra la cobertura (las cubren las columnas de fecha y la
frontera temporal del harness), pero se devuelven aparte.
"""

from __future__ import annotations

from .extractor import EntityExtractor
from .index import SemanticIndex
from .ontology import Ontology


class SemanticService:
    def __init__(
        self,
        ontology: Ontology,
        index: SemanticIndex,
        extractor: EntityExtractor,
        threshold: float = 0.55,
    ) -> None:
        self.ontology = ontology
        self.index = index
        self.extractor = extractor
        self.threshold = threshold

    def search_terms(self, query: str, limit: int = 5) -> dict:
        hits = self.index.search(query, limit=limit)
        return {"query": query, "hits": [h.as_dict() for h in hits], "ontology": self.ontology.summary()}

    def get_term(self, name: str) -> dict:
        term = self.ontology.term(name)
        return {
            "found": term is not None,
            "term": {**term.as_dict(), **self.ontology.related(term)} if term else None,
            "ontology": self.ontology.summary(),
        }

    def check_answerable(self, question: str) -> dict:
        entities = self.extractor.extract(question)
        time_refs = [e.text for e in entities if e.kind == "time"]
        concepts = [e for e in entities if e.kind != "time"]

        covered, uncovered = [], []
        for entity in concepts:
            best = self.index.search(entity.text, limit=1)[0]
            match = {
                "entity": entity.text,
                "kind": entity.kind,
                "term": best.term,
                "table": best.table,
                "column": best.column,
                "score": round(best.score, 4),
            }
            (covered if best.score >= self.threshold else uncovered).append(match)

        coverage = len(covered) / len(concepts) if concepts else 0.0
        result = {
            "question": question,
            "answerable": bool(concepts) and not uncovered,
            "coverage": round(coverage, 4),
            "covered": covered,
            "uncovered": uncovered,
            "time_references": time_refs,
            "threshold": self.threshold,
            "ontology": self.ontology.summary(),
        }
        if not concepts:
            result["reason"] = "no_entities"
        elif uncovered:
            result["reason"] = "uncovered_concepts"
        return result
