"""
Redis client service for caching extracted text.
"""

from typing import Optional
import json

import structlog
import redis.asyncio as redis

from ..config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# Global client instance
_client: Optional[redis.Redis] = None


async def init_redis_client() -> None:
    """Initialize the global Redis client."""
    global _client

    try:
        _client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

        # Test connection
        await _client.ping()

        logger.info(
            "Redis client initialized",
            url=settings.redis_url.split("@")[-1],  # Hide password
        )

    except Exception as e:
        logger.error("Failed to initialize Redis client", error=str(e))
        _client = None
        # Don't raise - extraction can work without cache


async def close_redis_client() -> None:
    """Close the Redis client."""
    global _client
    if _client:
        await _client.close()
        _client = None


def get_redis_client() -> Optional[redis.Redis]:
    """Get the global Redis client instance."""
    return _client


class ExtractionCache:
    """
    Cache for extracted text from documents.

    IMPORTANT: Uses "doc:text:" prefix for compatibility with Backend Core.
    Both Backend and File Manager plugin must share the same cache keys
    to avoid redundant extractions and ensure consistency.
    """

    # 🔧 FIX: Changed from "file-manager:extraction:" to "doc:text:" for Backend compatibility
    CACHE_PREFIX = "doc:text:"

    def __init__(self, client: Optional[redis.Redis] = None):
        self.client = client or get_redis_client()
        self.ttl = settings.extraction_cache_ttl_seconds

    async def get(self, file_id: str) -> Optional[dict]:
        """
        Get cached extraction result.

        Returns:
            Dict with 'text', 'pages', 'metadata' or None if not cached
        """
        if not self.client:
            return None

        try:
            key = f"{self.CACHE_PREFIX}{file_id}"
            data = await self.client.get(key)

            if data:
                logger.debug("Extraction cache hit", file_id=file_id)
                return json.loads(data)

            return None

        except Exception as e:
            logger.warning("Failed to get from extraction cache", error=str(e))
            return None

    async def set(
        self,
        file_id: str,
        text: str,
        pages: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Cache extraction result.

        Args:
            file_id: Unique file identifier
            text: Extracted text content
            pages: Number of pages (for PDFs)
            metadata: Additional metadata

        Returns:
            True if cached successfully
        """
        if not self.client:
            return False

        try:
            key = f"{self.CACHE_PREFIX}{file_id}"
            data = json.dumps({
                "text": text,
                "pages": pages,
                "metadata": metadata or {},
            })

            await self.client.setex(key, self.ttl, data)

            logger.debug(
                "Extraction cached",
                file_id=file_id,
                text_length=len(text),
                ttl=self.ttl,
            )

            return True

        except Exception as e:
            logger.warning("Failed to cache extraction", error=str(e))
            return False

    async def delete(self, file_id: str) -> bool:
        """Delete cached extraction."""
        if not self.client:
            return False

        try:
            key = f"{self.CACHE_PREFIX}{file_id}"
            await self.client.delete(key)
            return True

        except Exception as e:
            logger.warning("Failed to delete from cache", error=str(e))
            return False


# Singleton instance
_extraction_cache: Optional[ExtractionCache] = None


def get_extraction_cache() -> ExtractionCache:
    """Get the extraction cache instance."""
    global _extraction_cache
    if _extraction_cache is None:
        _extraction_cache = ExtractionCache()
    return _extraction_cache
