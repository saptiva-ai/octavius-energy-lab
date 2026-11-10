"""
Unit tests for Fase 3: LLM Semantic Cache (Weaviate-backed).

Tests search/store/purge flows with mocked Weaviate client and embedding service.
"""

import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.llm_semantic_cache import (
    COLLECTION_NAME,
    DEFAULT_TTL_SECONDS,
    MAX_RESPONSE_LENGTH,
    SIMILARITY_THRESHOLD,
    LLMSemanticCache,
)


# --- Helpers ---


def _make_weaviate_service(connected=True, collection_exists=True):
    """Build a mock weaviate_service with controllable client."""
    svc = MagicMock()
    client = MagicMock()
    client.is_connected.return_value = connected
    client.collections.exists.return_value = collection_exists
    svc.client = client
    return svc


def _make_embedding_service(vector=None):
    """Build a mock embedding_service returning a fixed 384-dim vector."""
    svc = MagicMock()
    svc.encode_single.return_value = vector or [0.1] * 384
    return svc


def _make_cache(connected=True, collection_exists=True, vector=None):
    """Convenience: create LLMSemanticCache with mocked deps."""
    weaviate_svc = _make_weaviate_service(connected, collection_exists)
    embedding_svc = _make_embedding_service(vector)
    cache = LLMSemanticCache(weaviate_svc, embedding_svc, cache_version="v1")
    return cache, weaviate_svc, embedding_svc


def _make_weaviate_object(response_text, distance, hit_count=0, uuid="test-uuid"):
    """Build a mock Weaviate query result object."""
    obj = MagicMock()
    obj.uuid = uuid
    obj.properties = {
        "response_text": response_text,
        "hit_count": hit_count,
    }
    obj.metadata = SimpleNamespace(distance=distance)
    return obj


# --- Tests: _ensure_collection ---


@pytest.mark.unit
class TestEnsureCollection:
    """Test collection creation on init."""

    def test_creates_collection_when_missing(self):
        """Verify collection is created if it doesn't exist."""
        cache, weaviate_svc, _ = _make_cache(collection_exists=False)

        weaviate_svc.client.collections.create.assert_called_once()
        call_kwargs = weaviate_svc.client.collections.create.call_args
        assert call_kwargs[1]["name"] == COLLECTION_NAME

    def test_skips_creation_when_exists(self):
        """Verify no create call if collection already exists."""
        cache, weaviate_svc, _ = _make_cache(collection_exists=True)

        weaviate_svc.client.collections.create.assert_not_called()

    def test_handles_disconnected_client(self):
        """Verify no crash when Weaviate is not connected."""
        cache, weaviate_svc, _ = _make_cache(connected=False)

        weaviate_svc.client.collections.exists.assert_not_called()
        weaviate_svc.client.collections.create.assert_not_called()


# --- Tests: search ---


@pytest.mark.unit
class TestSearch:
    """Test semantic search for cached LLM responses."""

    def test_cache_hit_above_threshold(self):
        """Verify cache hit when similarity > threshold."""
        cache, weaviate_svc, _ = _make_cache()

        # distance=0.05 means similarity=0.95 (above 0.92 threshold)
        mock_obj = _make_weaviate_object("cached response", distance=0.05, hit_count=3)
        collection = weaviate_svc.client.collections.get.return_value
        collection.query.near_vector.return_value = MagicMock(objects=[mock_obj])

        result = cache.search("cartera comercial bancodemo", handler="evolucion_banco")

        assert result is not None
        response_text, similarity = result
        assert response_text == "cached response"
        assert abs(similarity - 0.95) < 0.001

    def test_cache_miss_no_objects(self):
        """Verify None returned when no similar queries found."""
        cache, weaviate_svc, _ = _make_cache()

        collection = weaviate_svc.client.collections.get.return_value
        collection.query.near_vector.return_value = MagicMock(objects=[])

        result = cache.search("pregunta completamente nueva")

        assert result is None

    def test_cache_miss_below_threshold(self):
        """Verify None returned when similarity < threshold."""
        cache, weaviate_svc, _ = _make_cache()

        # distance=0.15 means similarity=0.85 (below 0.92 threshold)
        mock_obj = _make_weaviate_object("irrelevant", distance=0.15)
        collection = weaviate_svc.client.collections.get.return_value
        collection.query.near_vector.return_value = MagicMock(objects=[mock_obj])

        result = cache.search("pregunta diferente")

        assert result is None

    def test_search_disconnected_returns_none(self):
        """Verify graceful None when Weaviate is disconnected."""
        cache, weaviate_svc, _ = _make_cache(connected=True)
        # Simulate disconnect after init
        weaviate_svc.client.is_connected.return_value = False

        result = cache.search("test query")

        assert result is None

    def test_search_records_hit_count(self):
        """Verify hit count is incremented on cache hit."""
        cache, weaviate_svc, _ = _make_cache()

        mock_obj = _make_weaviate_object("cached", distance=0.03, hit_count=5, uuid="abc-123")
        collection = weaviate_svc.client.collections.get.return_value
        collection.query.near_vector.return_value = MagicMock(objects=[mock_obj])

        cache.search("query with hit")

        collection.data.update.assert_called_once_with(
            uuid="abc-123",
            properties={"hit_count": 6},
        )

    def test_search_without_handler_filter(self):
        """Verify search works without handler filter."""
        cache, weaviate_svc, _ = _make_cache()

        mock_obj = _make_weaviate_object("generic cached", distance=0.02)
        collection = weaviate_svc.client.collections.get.return_value
        collection.query.near_vector.return_value = MagicMock(objects=[mock_obj])

        result = cache.search("query sin handler")

        assert result is not None
        assert result[0] == "generic cached"

    def test_search_custom_threshold(self):
        """Verify custom similarity threshold is respected."""
        cache, weaviate_svc, _ = _make_cache()

        # distance=0.05, similarity=0.95 — above 0.92 but below 0.98
        mock_obj = _make_weaviate_object("cached", distance=0.05)
        collection = weaviate_svc.client.collections.get.return_value
        collection.query.near_vector.return_value = MagicMock(objects=[mock_obj])

        result = cache.search("query", similarity_threshold=0.98)

        assert result is None


# --- Tests: store ---


@pytest.mark.unit
class TestStore:
    """Test storing query-response pairs in semantic cache."""

    def test_store_success(self):
        """Verify store inserts data with correct properties."""
        cache, weaviate_svc, embedding_svc = _make_cache()

        collection = weaviate_svc.client.collections.get.return_value
        collection.data.insert.return_value = "new-uuid-123"

        result = cache.store(
            query="cartera comercial bancodemo",
            response="La cartera comercial de BancoDemo...",
            handler="evolucion_banco",
            bank_context={"bank": "bancodemo"},
        )

        assert result == "new-uuid-123"
        insert_call = collection.data.insert.call_args
        props = insert_call[1]["properties"]
        assert props["query_text"] == "cartera comercial bancodemo"
        assert props["response_text"] == "La cartera comercial de BancoDemo..."
        assert props["handler"] == "evolucion_banco"
        assert json.loads(props["bank_context_json"]) == {"bank": "bancodemo"}
        assert props["cache_version"] == "v1"
        assert props["hit_count"] == 0
        assert "vector" in insert_call[1]

    def test_store_truncates_long_response(self):
        """Verify responses beyond MAX_RESPONSE_LENGTH are truncated."""
        cache, weaviate_svc, _ = _make_cache()

        collection = weaviate_svc.client.collections.get.return_value
        collection.data.insert.return_value = "uuid-trunc"

        long_response = "x" * (MAX_RESPONSE_LENGTH + 1000)
        cache.store("query", long_response)

        insert_call = collection.data.insert.call_args
        stored_text = insert_call[1]["properties"]["response_text"]
        assert len(stored_text) == MAX_RESPONSE_LENGTH

    def test_store_disconnected_returns_none(self):
        """Verify graceful None when Weaviate is disconnected."""
        cache, weaviate_svc, _ = _make_cache(connected=True)
        weaviate_svc.client.is_connected.return_value = False

        result = cache.store("query", "response")

        assert result is None

    def test_store_defaults_handler_to_empty(self):
        """Verify handler defaults to empty string when None."""
        cache, weaviate_svc, _ = _make_cache()

        collection = weaviate_svc.client.collections.get.return_value
        collection.data.insert.return_value = "uuid"

        cache.store("query", "response")

        props = collection.data.insert.call_args[1]["properties"]
        assert props["handler"] == ""

    def test_store_sets_ttl(self):
        """Verify expires_at is set correctly based on TTL."""
        cache, weaviate_svc, _ = _make_cache()

        collection = weaviate_svc.client.collections.get.return_value
        collection.data.insert.return_value = "uuid"

        before = time.time()
        cache.store("query", "response", ttl_seconds=3600)
        after = time.time()

        props = collection.data.insert.call_args[1]["properties"]
        # expires_at should be ~1 hour from now
        assert props["expires_at"] >= before + 3600
        assert props["expires_at"] <= after + 3600


# --- Tests: purge methods ---


@pytest.mark.unit
class TestPurge:
    """Test purge methods for cache maintenance."""

    def test_purge_expired(self):
        """Verify purge_expired deletes entries past expires_at."""
        cache, weaviate_svc, _ = _make_cache()

        collection = weaviate_svc.client.collections.get.return_value
        collection.data.delete_many.return_value = MagicMock(successful=5)

        deleted = cache.purge_expired()

        assert deleted == 5
        collection.data.delete_many.assert_called_once()

    def test_purge_cold(self):
        """Verify purge_cold deletes zero-hit entries older than threshold."""
        cache, weaviate_svc, _ = _make_cache()

        collection = weaviate_svc.client.collections.get.return_value
        collection.data.delete_many.return_value = MagicMock(successful=3)

        deleted = cache.purge_cold(max_age_seconds=10 * 86400)

        assert deleted == 3
        collection.data.delete_many.assert_called_once()

    def test_purge_version(self):
        """Verify purge_version deletes all entries for a given version."""
        cache, weaviate_svc, _ = _make_cache()

        collection = weaviate_svc.client.collections.get.return_value
        collection.data.delete_many.return_value = MagicMock(successful=10)

        deleted = cache.purge_version("v1")

        assert deleted == 10
        collection.data.delete_many.assert_called_once()

    def test_purge_disconnected_returns_zero(self):
        """Verify purge returns 0 when Weaviate is disconnected."""
        cache, weaviate_svc, _ = _make_cache(connected=True)
        weaviate_svc.client.is_connected.return_value = False

        assert cache.purge_expired() == 0
        assert cache.purge_cold() == 0
        assert cache.purge_version("v1") == 0


# --- Tests: get_stats ---


@pytest.mark.unit
class TestGetStats:
    """Test cache statistics retrieval."""

    def test_stats_healthy(self):
        """Verify stats returns correct values when healthy."""
        cache, weaviate_svc, _ = _make_cache()

        collection = weaviate_svc.client.collections.get.return_value
        collection.aggregate.over_all.return_value = MagicMock(total_count=42)

        stats = cache.get_stats()

        assert stats["status"] == "healthy"
        assert stats["total_entries"] == 42
        assert stats["collection"] == COLLECTION_NAME
        assert stats["cache_version"] == "v1"
        assert stats["similarity_threshold"] == SIMILARITY_THRESHOLD

    def test_stats_disconnected(self):
        """Verify stats returns disconnected status when client is down."""
        cache, weaviate_svc, _ = _make_cache(connected=True)
        weaviate_svc.client.is_connected.return_value = False

        stats = cache.get_stats()

        assert stats["status"] == "disconnected"


# --- Tests: singleton factory ---


@pytest.mark.unit
class TestGetLLMSemanticCache:
    """Test singleton factory function."""

    def test_singleton_returns_same_instance(self):
        """Verify repeated calls return the same cache instance."""
        import src.services.llm_semantic_cache as mod

        # Reset singleton
        mod._llm_semantic_cache = None

        mock_weaviate = _make_weaviate_service()
        mock_embedder = _make_embedding_service()
        mock_settings = MagicMock()
        mock_settings.cache_version = "v1"

        with (
            patch("src.services.weaviate_service.get_weaviate_service", return_value=mock_weaviate),
            patch("src.services.embedding_service.get_embedding_service", return_value=mock_embedder),
            patch("src.core.config.get_settings", return_value=mock_settings),
        ):
            cache1 = mod.get_llm_semantic_cache()
            cache2 = mod.get_llm_semantic_cache()

        assert cache1 is cache2
        assert cache1 is not None

        # Cleanup
        mod._llm_semantic_cache = None

    def test_singleton_returns_none_on_failure(self):
        """Verify None returned when dependencies are unavailable."""
        import src.services.llm_semantic_cache as mod

        mod._llm_semantic_cache = None

        with patch(
            "src.services.weaviate_service.get_weaviate_service",
            side_effect=RuntimeError("Weaviate unavailable"),
        ):
            result = mod.get_llm_semantic_cache()

        assert result is None

        # Cleanup
        mod._llm_semantic_cache = None
