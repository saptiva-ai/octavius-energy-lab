"""
LLM Semantic Cache Service (Weaviate-backed).

Caches LLM responses by embedding similarity. Two queries with
cosine similarity > THRESHOLD return the same cached response,
avoiding redundant LLM calls.

Architecture:
- Storage: Weaviate collection "LLM_Response_Cache"
- Embeddings: 384-dim via embedding_service (MiniLM-L12-v2)
- Search: near_vector (pure cosine, no hybrid)
- TTL: created_at + expires_at timestamps with periodic purge
- Version isolation: cache_version property filters

Usage:
    cache = get_llm_semantic_cache()
    hit = cache.search("cartera comercial bancodemo", handler="evolucion_banco")
    if hit:
        response_text, similarity = hit
    else:
        response_text = await call_llm(...)
        cache.store(query, response_text, handler="evolucion_banco")
"""

import json
import time
import uuid
from typing import Any, Dict, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

# --- Configuration ---
COLLECTION_NAME = "LLM_Response_Cache"
SIMILARITY_THRESHOLD = 0.92  # cosine similarity for cache hit
DEFAULT_TTL_SECONDS = 7 * 86400  # 7 days
MAX_RESPONSE_LENGTH = 50_000  # truncate responses beyond this


class LLMSemanticCache:
    """Cache LLM responses by semantic similarity using Weaviate."""

    def __init__(
        self,
        weaviate_service,
        embedding_service,
        cache_version: str = "v1",
    ):
        self._weaviate = weaviate_service
        self._embedder = embedding_service
        self._cache_version = cache_version
        self._collection_name = COLLECTION_NAME
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create the LLM cache collection if it doesn't exist."""
        try:
            client = self._weaviate.client
            if not client or not client.is_connected():
                logger.warning("llm_cache.weaviate_not_connected")
                return

            if client.collections.exists(self._collection_name):
                logger.debug("llm_cache.collection_exists")
                return

            from weaviate.classes.config import Configure, DataType, Property

            client.collections.create(
                name=self._collection_name,
                properties=[
                    Property(name="query_text", data_type=DataType.TEXT),
                    Property(name="response_text", data_type=DataType.TEXT),
                    Property(name="handler", data_type=DataType.TEXT),
                    Property(name="bank_context_json", data_type=DataType.TEXT),
                    Property(name="cache_version", data_type=DataType.TEXT),
                    Property(name="hit_count", data_type=DataType.INT),
                    Property(name="created_at", data_type=DataType.NUMBER),
                    Property(name="expires_at", data_type=DataType.NUMBER),
                ],
                vectorizer_config=Configure.Vectorizer.none(),
            )
            logger.info("llm_cache.collection_created")

        except Exception as e:
            logger.error("llm_cache.ensure_collection_failed", error=str(e))

    def search(
        self,
        query: str,
        handler: Optional[str] = None,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
    ) -> Optional[Tuple[str, float]]:
        """Search for semantically similar cached response.

        Returns (response_text, similarity) or None on miss.
        """
        try:
            client = self._weaviate.client
            if not client or not client.is_connected():
                return None

            embedding = self._embedder.encode_single(query)
            collection = client.collections.get(self._collection_name)

            from weaviate.classes.query import Filter, MetadataQuery

            # Build filters: version + not expired
            now = time.time()
            filters = Filter.by_property("cache_version").equal(
                self._cache_version
            ) & Filter.by_property("expires_at").greater_than(now)

            # Optional handler filter
            if handler:
                filters = filters & Filter.by_property("handler").equal(handler)

            response = collection.query.near_vector(
                near_vector=embedding,
                limit=1,
                filters=filters,
                return_metadata=MetadataQuery(distance=True),
            )

            if not response.objects:
                logger.debug("llm_cache.miss", query_preview=query[:60])
                return None

            obj = response.objects[0]
            # Weaviate cosine distance: [0, 2], similarity = 1 - distance
            distance = obj.metadata.distance or 1.0
            similarity = 1.0 - distance

            if similarity < similarity_threshold:
                logger.debug(
                    "llm_cache.below_threshold",
                    similarity=round(similarity, 4),
                    threshold=similarity_threshold,
                    query_preview=query[:60],
                )
                return None

            # Cache hit — update hit count async (best-effort)
            self._record_hit(obj.uuid, obj.properties.get("hit_count", 0))

            logger.info(
                "llm_cache.hit",
                similarity=round(similarity, 4),
                handler=handler,
                query_preview=query[:60],
            )
            return obj.properties["response_text"], similarity

        except Exception as e:
            logger.warning("llm_cache.search_error", error=str(e))
            return None

    def store(
        self,
        query: str,
        response: str,
        handler: Optional[str] = None,
        bank_context: Optional[Dict[str, Any]] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> Optional[str]:
        """Store query-response pair in semantic cache. Returns object UUID or None."""
        try:
            client = self._weaviate.client
            if not client or not client.is_connected():
                return None

            embedding = self._embedder.encode_single(query)
            collection = client.collections.get(self._collection_name)

            now = time.time()
            obj_uuid = str(
                uuid.uuid5(
                    uuid.NAMESPACE_DNS,
                    f"llm_cache:{self._cache_version}:{query}",
                )
            )

            # Truncate very long responses
            response_text = response[:MAX_RESPONSE_LENGTH]

            obj_id = collection.data.insert(
                uuid=obj_uuid,
                properties={
                    "query_text": query,
                    "response_text": response_text,
                    "handler": handler or "",
                    "bank_context_json": json.dumps(bank_context or {}),
                    "cache_version": self._cache_version,
                    "hit_count": 0,
                    "created_at": now,
                    "expires_at": now + ttl_seconds,
                },
                vector=embedding,
            )

            logger.info(
                "llm_cache.stored",
                handler=handler,
                ttl_days=ttl_seconds // 86400,
                query_preview=query[:60],
            )
            return str(obj_id)

        except Exception as e:
            logger.warning("llm_cache.store_error", error=str(e))
            return None

    def _record_hit(self, obj_uuid, current_count: int) -> None:
        """Increment hit count (best-effort, non-blocking)."""
        try:
            client = self._weaviate.client
            if not client or not client.is_connected():
                return

            collection = client.collections.get(self._collection_name)
            collection.data.update(
                uuid=obj_uuid,
                properties={"hit_count": current_count + 1},
            )
        except Exception:
            pass  # Non-critical

    def purge_expired(self) -> int:
        """Delete entries past their expires_at. Returns count deleted."""
        try:
            client = self._weaviate.client
            if not client or not client.is_connected():
                return 0

            collection = client.collections.get(self._collection_name)
            now = time.time()

            from weaviate.classes.query import Filter

            result = collection.data.delete_many(
                where=Filter.by_property("expires_at").less_than(now),
            )
            deleted = result.successful if hasattr(result, "successful") else 0
            logger.info("llm_cache.purge_expired", deleted=deleted)
            return deleted

        except Exception as e:
            logger.warning("llm_cache.purge_expired_error", error=str(e))
            return 0

    def purge_cold(self, max_age_seconds: int = 15 * 86400) -> int:
        """Delete entries with 0 hits older than max_age_seconds."""
        try:
            client = self._weaviate.client
            if not client or not client.is_connected():
                return 0

            collection = client.collections.get(self._collection_name)
            cutoff = time.time() - max_age_seconds

            from weaviate.classes.query import Filter

            result = collection.data.delete_many(
                where=(
                    Filter.by_property("hit_count").equal(0)
                    & Filter.by_property("created_at").less_than(cutoff)
                ),
            )
            deleted = result.successful if hasattr(result, "successful") else 0
            logger.info(
                "llm_cache.purge_cold",
                deleted=deleted,
                max_age_days=max_age_seconds // 86400,
            )
            return deleted

        except Exception as e:
            logger.warning("llm_cache.purge_cold_error", error=str(e))
            return 0

    def purge_version(self, version: str) -> int:
        """Delete all entries for a specific cache version."""
        try:
            client = self._weaviate.client
            if not client or not client.is_connected():
                return 0

            collection = client.collections.get(self._collection_name)

            from weaviate.classes.query import Filter

            result = collection.data.delete_many(
                where=Filter.by_property("cache_version").equal(version),
            )
            deleted = result.successful if hasattr(result, "successful") else 0
            logger.info("llm_cache.purge_version", version=version, deleted=deleted)
            return deleted

        except Exception as e:
            logger.warning("llm_cache.purge_version_error", error=str(e))
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        try:
            client = self._weaviate.client
            if not client or not client.is_connected():
                return {"status": "disconnected"}

            collection = client.collections.get(self._collection_name)
            agg = collection.aggregate.over_all(total_count=True)

            return {
                "status": "healthy",
                "collection": self._collection_name,
                "total_entries": agg.total_count,
                "cache_version": self._cache_version,
                "similarity_threshold": SIMILARITY_THRESHOLD,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


# --- Singleton ---
_llm_semantic_cache: Optional[LLMSemanticCache] = None


def get_llm_semantic_cache() -> Optional[LLMSemanticCache]:
    """Get or create singleton LLM semantic cache.

    Returns None if Weaviate or embedding service is unavailable.
    """
    global _llm_semantic_cache
    if _llm_semantic_cache is not None:
        return _llm_semantic_cache

    try:
        from ..core.config import get_settings
        from .embedding_service import get_embedding_service
        from .weaviate_service import get_weaviate_service

        weaviate_svc = get_weaviate_service()
        embedding_svc = get_embedding_service()
        settings = get_settings()

        _llm_semantic_cache = LLMSemanticCache(
            weaviate_service=weaviate_svc,
            embedding_service=embedding_svc,
            cache_version=settings.cache_version,
        )
        return _llm_semantic_cache

    except Exception as e:
        logger.warning("llm_cache.init_failed", error=str(e))
        return None
