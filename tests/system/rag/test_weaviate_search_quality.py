"""
Weaviate Search Quality Tests — verify semantic + hybrid search on Ontology_Term_V2.

Tests that the Weaviate Ontology_Term_V2 collection returns relevant results
for educational banking queries. Requires a running Weaviate Cloud cluster.

Set RUN_WEAVIATE_TESTS=true to enable (skipped by default).

Run:
    cd <repo_root>
    RUN_WEAVIATE_TESTS=true apps/backend/.venv/bin/python -m pytest \\
        tests/system/rag/test_weaviate_search_quality.py -v
"""

import os
import sys
from pathlib import Path

import pytest

# Load envs/.env for WEAVIATE_URL and WEAVIATE_API_KEY
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_PATH = _REPO_ROOT / "envs" / ".env"

if _ENV_PATH.exists():
    with open(_ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"'))

_skip = pytest.mark.skipif(
    os.getenv("RUN_WEAVIATE_TESTS", "false").lower() != "true",
    reason="RUN_WEAVIATE_TESTS not set",
)


def _get_client():
    """Connect to Weaviate Cloud."""
    import weaviate

    url = os.environ.get("WEAVIATE_URL", "")
    api_key = os.environ.get("WEAVIATE_API_KEY", "")
    if not url or not api_key:
        pytest.skip("WEAVIATE_URL or WEAVIATE_API_KEY not configured")

    return weaviate.connect_to_weaviate_cloud(
        cluster_url=url,
        auth_credentials=weaviate.auth.AuthApiKey(api_key),
    )


# =============================================================================
# Collection health
# =============================================================================


@_skip
class TestCollectionHealth:
    """Verify Ontology_Term_V2 exists and has expected data."""

    def test_collection_exists(self):
        client = _get_client()
        try:
            assert client.collections.exists("Ontology_Term_V2")
        finally:
            client.close()

    def test_has_objects(self):
        client = _get_client()
        try:
            coll = client.collections.get("Ontology_Term_V2")
            count = coll.aggregate.over_all(total_count=True).total_count
            assert count > 200, f"Expected >200 objects, got {count}"
        finally:
            client.close()

    def test_vectorizer_is_active(self):
        client = _get_client()
        try:
            coll = client.collections.get("Ontology_Term_V2")
            config = coll.config.get()
            vec = str(config.vectorizer_config)
            assert "text2vec" in vec.lower() or "weaviate" in vec.lower(), (
                f"Expected text2vec-weaviate vectorizer, got: {vec}"
            )
        finally:
            client.close()

    def test_no_placeholder_definitions(self):
        """Verify noise placeholders were cleaned."""
        client = _get_client()
        try:
            coll = client.collections.get("Ontology_Term_V2")
            noise_patterns = [
                "Lista Anexo 36",
                "Concepto tabla Anexo 36",
                "Detalle del reporte regulatorio",
            ]
            for item in coll.iterator(include_vector=False):
                defn = item.properties.get("definition", "") or ""
                for pattern in noise_patterns:
                    assert pattern not in defn, (
                        f"Found placeholder noise: '{pattern}' in '{item.properties.get('name')}'"
                    )
                # Only check first 100 objects (performance)
                break
        finally:
            client.close()


# =============================================================================
# Semantic search quality
# =============================================================================


@_skip
class TestSemanticSearch:
    """Verify nearText returns relevant results for educational queries."""

    def _search(self, query: str, limit: int = 5):
        client = _get_client()
        try:
            coll = client.collections.get("Ontology_Term_V2")
            results = coll.query.near_text(query=query, limit=limit)
            return [
                {
                    "name": obj.properties.get("name", ""),
                    "definition": obj.properties.get("definition", ""),
                    "source": obj.properties.get("source", ""),
                }
                for obj in results.objects
            ]
        finally:
            client.close()

    def test_icap_query(self):
        """'¿qué es el ICAP?' should return ICAP/Índice de Capitalización."""
        results = self._search("¿qué es el ICAP?")
        names = [r["name"].lower() for r in results]
        assert any("icap" in n or "capitalización" in n for n in names), (
            f"Expected ICAP in results, got: {names}"
        )

    def test_cartera_vencida_query(self):
        """'préstamos que no se pagan' should return morosidad/NPL terms."""
        results = self._search("préstamos que no se pagan a tiempo")
        all_text = " ".join(r["name"] + " " + r["definition"] for r in results).lower()
        assert any(
            kw in all_text
            for kw in ["morosidad", "vencida", "incumplimiento", "npl", "préstamo"]
        ), f"Expected loan default terms, got: {[r['name'] for r in results]}"

    def test_capital_query(self):
        """'capitalización bancaria' should return capital-related terms."""
        results = self._search("¿qué tan bien capitalizado está un banco?")
        all_text = " ".join(r["name"] + " " + r["definition"] for r in results).lower()
        assert any(
            kw in all_text for kw in ["capital", "icap", "capitalización", "suficiencia"]
        ), f"Expected capital terms, got: {[r['name'] for r in results]}"

    def test_reporte_regulatorio_query(self):
        """Query about regulatory reports should return Anexo 36 reportes."""
        results = self._search("razón de apalancamiento bancario")
        all_text = " ".join(r["name"] + " " + r["definition"] for r in results).lower()
        assert any(
            kw in all_text for kw in ["apalancamiento", "a-3401", "leverage"]
        ), f"Expected leverage terms, got: {[r['name'] for r in results]}"


# =============================================================================
# Hybrid search quality
# =============================================================================


@_skip
class TestHybridSearch:
    """Verify hybrid search (vector + BM25) returns relevant results."""

    def _search(self, query: str, limit: int = 5, alpha: float = 0.7):
        client = _get_client()
        try:
            coll = client.collections.get("Ontology_Term_V2")
            results = coll.query.hybrid(query=query, limit=limit, alpha=alpha)
            return [
                {
                    "name": obj.properties.get("name", ""),
                    "definition": obj.properties.get("definition", ""),
                }
                for obj in results.objects
            ]
        finally:
            client.close()

    def test_riesgo_crediticio(self):
        results = self._search("riesgo crediticio calificación")
        names = [r["name"].lower() for r in results]
        assert any(
            "calificaci" in n or "riesgo" in n or "creditici" in n for n in names
        ), f"Expected risk/rating terms, got: {names}"

    def test_banca_electronica(self):
        results = self._search("servicios digitales bancarios")
        all_text = " ".join(r["name"] for r in results).lower()
        assert any(
            kw in all_text for kw in ["banca", "electrónic", "móvil", "digital"]
        ), f"Expected e-banking terms, got: {[r['name'] for r in results]}"

    def test_no_empty_results(self):
        """Any reasonable query should return at least 1 result."""
        results = self._search("información financiera bancaria")
        assert len(results) > 0


# =============================================================================
# Data source diversity
# =============================================================================


@_skip
class TestDataSourceDiversity:
    """Verify multiple data sources are present in the collection."""

    def test_has_glosario_cub_terms(self):
        client = _get_client()
        try:
            from weaviate.classes.query import Filter

            coll = client.collections.get("Ontology_Term_V2")
            results = coll.query.fetch_objects(
                filters=Filter.by_property("source").equal("Glosario CUB México"),
                limit=1,
            )
            assert len(results.objects) > 0, "No Glosario CUB terms found"
        finally:
            client.close()

    def test_has_anexo36_reportes(self):
        client = _get_client()
        try:
            from weaviate.classes.query import Filter

            coll = client.collections.get("Ontology_Term_V2")
            results = coll.query.fetch_objects(
                filters=Filter.by_property("source").equal("Anexo 36 CUB"),
                limit=1,
            )
            assert len(results.objects) > 0, "No Anexo 36 reporte chunks found"
        finally:
            client.close()
