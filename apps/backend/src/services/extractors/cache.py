"""
Extraction Cache Module with Redis and zstd Compression

Provides caching layer for text extraction to reduce API costs and improve performance.

Features:
    - Redis-based caching with 24h TTL
    - zstd compression for large documents (>1KB)
    - Content-based cache keys (SHA-256 hash)
    - Cache hit/miss metrics
    - Automatic cache expiration
    - Optional cache warming

Architecture:
    Cache Key: "extract:{provider}:{media_type}:{content_hash}"
    Value: Compressed extracted text
    TTL: 24 hours (86400 seconds)

Performance:
    - zstd compression ratio: ~3x-5x for text
    - Redis GET latency: <1ms (local), <5ms (remote)
    - Savings: $0.01-0.10 per cached extraction (vs API call)
"""

import hashlib
import os
from typing import Literal, Optional

import structlog

logger = structlog.get_logger(__name__)

# Lazy imports (only load if caching is enabled)
_redis = None
_zstd = None


def _get_redis():
    """Lazy load Redis client."""
    global _redis
    if _redis is None:
        try:
            import redis.asyncio as redis

            _redis = redis
        except ImportError:
            logger.warning("redis package not available, caching disabled")
            _redis = False
    return _redis if _redis is not False else None


def _get_zstd():
    """Lazy load zstd compression."""
    global _zstd
    if _zstd is None:
        try:
            import zstandard as zstd

            _zstd = zstd
        except ImportError:
            logger.warning("zstandard package not available, compression disabled")
            _zstd = False
    return _zstd if _zstd is not False else None


MediaType = Literal["pdf", "image"]


class ExtractionCache:
    """
    Redis-based cache for text extraction results.

    Uses content-based keys (SHA-256 hash) to cache extracted text,
    with optional zstd compression for large results.

    Configuration (Environment Variables):
        EXTRACTION_CACHE_ENABLED: Enable caching (default: true)
        EXTRACTION_CACHE_TTL_HOURS: Cache TTL in hours (default: 24)
        EXTRACTION_CACHE_COMPRESSION_THRESHOLD: Compression threshold in bytes (default: 1024)
        REDIS_URL: Redis connection URL

    Example:
        cache = ExtractionCache()

        # Try to get cached result
        cached = await cache.get("saptiva", "pdf", pdf_bytes)
        if cached:
            return cached

        # Extract and cache
        text = await expensive_extraction(pdf_bytes)
        await cache.set("saptiva", "pdf", pdf_bytes, text)
    """

    # Cache configuration
    DEFAULT_TTL_HOURS = 24
    DEFAULT_COMPRESSION_THRESHOLD = 1024  # 1KB
    CACHE_KEY_PREFIX = "extract"

    def __init__(
        self,
        redis_url: Optional[str] = None,
        enabled: Optional[bool] = None,
        ttl_hours: Optional[int] = None,
        compression_threshold: Optional[int] = None,
    ):
        """
        Initialize extraction cache.

        Args:
            redis_url: Redis connection URL (default: from REDIS_URL env)
            enabled: Enable caching (default: from EXTRACTION_CACHE_ENABLED env)
            ttl_hours: Cache TTL in hours (default: 24)
            compression_threshold: Min size in bytes for compression (default: 1024)
        """
        # Configuration
        self.enabled = (
            enabled
            if enabled is not None
            else os.getenv("EXTRACTION_CACHE_ENABLED", "true").lower() == "true"
        )
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.ttl_hours = ttl_hours or int(
            os.getenv("EXTRACTION_CACHE_TTL_HOURS", str(self.DEFAULT_TTL_HOURS))
        )
        self.compression_threshold = compression_threshold or int(
            os.getenv(
                "EXTRACTION_CACHE_COMPRESSION_THRESHOLD",
                str(self.DEFAULT_COMPRESSION_THRESHOLD),
            )
        )

        # Redis client (lazy initialized)
        self._redis_client = None

        # Compression context (lazy initialized)
        self._compressor = None
        self._decompressor = None

        # Metrics
        self._cache_hits = 0
        self._cache_misses = 0
        self._bytes_saved = 0

        if not self.enabled:
            logger.info("Extraction cache disabled via configuration")
        else:
            logger.info(
                "Extraction cache initialized",
                redis_url=self._mask_redis_url(self.redis_url),
                ttl_hours=self.ttl_hours,
                compression_threshold=self.compression_threshold,
            )

    def _mask_redis_url(self, url: str) -> str:
        """Mask password in Redis URL for logging."""
        import re

        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)

    async def _get_redis_client(self):
        """Get or create Redis client."""
        if not self.enabled:
            return None

        if self._redis_client is None:
            redis = _get_redis()
            if redis is None:
                logger.warning("Redis not available, caching disabled")
                self.enabled = False
                return None

            try:
                self._redis_client = await redis.from_url(
                    self.redis_url, encoding="utf-8", decode_responses=False
                )
                # Test connection
                await self._redis_client.ping()
                logger.info("Redis connection established for extraction cache")
            except Exception as exc:
                logger.error(
                    "Failed to connect to Redis, caching disabled",
                    error=str(exc),
                    redis_url=self._mask_redis_url(self.redis_url),
                )
                self.enabled = False
                self._redis_client = None

        return self._redis_client

    def _get_compressor(self):
        """Get or create zstd compressor."""
        if self._compressor is None:
            zstd = _get_zstd()
            if zstd is None:
                return None

            # Level 3 is good balance of speed/compression
            self._compressor = zstd.ZstdCompressor(level=3)
            self._decompressor = zstd.ZstdDecompressor()

        return self._compressor

    def _generate_cache_key(
        self, provider: str, media_type: MediaType, data: bytes
    ) -> str:
        """
        Generate cache key from content hash.

        Format: "extract:{provider}:{media_type}:{hash}"
        Example: "extract:saptiva:pdf:a1b2c3d4e5f6"

        Args:
            provider: Extractor provider (e.g., "saptiva", "third_party")
            media_type: Document type ("pdf" or "image")
            data: Raw document bytes

        Returns:
            Cache key string
        """
        content_hash = hashlib.sha256(data).hexdigest()[:16]  # First 16 chars
        return f"{self.CACHE_KEY_PREFIX}:{provider}:{media_type}:{content_hash}"

    def _compress_text(self, text: str) -> bytes:
        """
        Compress text using zstd if above threshold.

        Args:
            text: Extracted text to compress

        Returns:
            Compressed bytes (or raw utf-8 bytes if below threshold)
        """
        text_bytes = text.encode("utf-8")

        # Skip compression for small texts
        if len(text_bytes) < self.compression_threshold:
            return text_bytes

        compressor = self._get_compressor()
        if compressor is None:
            return text_bytes

        try:
            compressed = compressor.compress(text_bytes)

            compression_ratio = len(text_bytes) / len(compressed)
            logger.debug(
                "Compressed extraction result",
                original_size=len(text_bytes),
                compressed_size=len(compressed),
                ratio=f"{compression_ratio:.2f}x",
            )

            return compressed
        except Exception as exc:
            logger.warning("Compression failed, storing uncompressed", error=str(exc))
            return text_bytes

    def _decompress_text(self, compressed_bytes: bytes) -> Optional[str]:
        """
        Decompress text using zstd.

        Args:
            compressed_bytes: Compressed or raw bytes

        Returns:
            Decompressed text string, or None if decompression fails
        """
        # Try decompression first
        if self._decompressor is not None:
            try:
                decompressed = self._decompressor.decompress(compressed_bytes)
                return decompressed.decode("utf-8")
            except Exception:
                # Not compressed, try direct decode
                pass

        # Fallback to direct decode
        try:
            return compressed_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            # Data is corrupted or not text (e.g., binary image data)
            logger.warning(
                "Failed to decode cached data, may be corrupted",
                error=str(exc)[:100],
                bytes_preview=compressed_bytes[:20].hex(),
            )
            return None

    async def get(
        self, provider: str, media_type: MediaType, data: bytes
    ) -> Optional[str]:
        """
        Get cached extraction result.

        Args:
            provider: Extractor provider (e.g., "saptiva")
            media_type: Document type ("pdf" or "image")
            data: Raw document bytes

        Returns:
            Cached extracted text, or None if not found
        """
        if not self.enabled:
            return None

        redis_client = await self._get_redis_client()
        if redis_client is None:
            return None

        cache_key = self._generate_cache_key(provider, media_type, data)

        try:
            cached_bytes = await redis_client.get(cache_key)

            if cached_bytes is None:
                self._cache_misses += 1
                logger.debug("Cache miss", cache_key=cache_key)
                return None

            # Decompress and return
            text = self._decompress_text(cached_bytes)

            # If decompression failed, treat as cache miss
            if text is None:
                self._cache_misses += 1
                logger.debug(
                    "Cache data corrupted, treating as miss", cache_key=cache_key
                )
                return None

            self._cache_hits += 1
            self._bytes_saved += len(data)

            logger.info(
                "Cache hit",
                cache_key=cache_key,
                text_length=len(text),
                bytes_saved=len(data),
                hit_rate=f"{self.get_hit_rate():.1%}",
            )

            return text

        except Exception as exc:
            logger.error(
                "Cache get failed",
                cache_key=cache_key,
                error=str(exc),
                exc_info=True,
            )
            return None

    async def set(
        self, provider: str, media_type: MediaType, data: bytes, text: str
    ) -> bool:
        """
        Cache extraction result.

        Args:
            provider: Extractor provider (e.g., "saptiva")
            media_type: Document type ("pdf" or "image")
            data: Raw document bytes
            text: Extracted text to cache

        Returns:
            True if cached successfully, False otherwise
        """
        if not self.enabled:
            return False

        redis_client = await self._get_redis_client()
        if redis_client is None:
            return False

        cache_key = self._generate_cache_key(provider, media_type, data)

        try:
            # Compress if needed
            compressed = self._compress_text(text)

            # Store with TTL
            ttl_seconds = self.ttl_hours * 3600
            await redis_client.setex(cache_key, ttl_seconds, compressed)

            logger.info(
                "Cache set",
                cache_key=cache_key,
                text_length=len(text),
                cached_size=len(compressed),
                ttl_hours=self.ttl_hours,
            )

            return True

        except Exception as exc:
            logger.error(
                "Cache set failed",
                cache_key=cache_key,
                error=str(exc),
                exc_info=True,
            )
            return False

    async def invalidate(
        self, provider: str, media_type: MediaType, data: bytes
    ) -> bool:
        """
        Invalidate cached extraction result.

        Args:
            provider: Extractor provider
            media_type: Document type
            data: Raw document bytes

        Returns:
            True if invalidated, False otherwise
        """
        if not self.enabled:
            return False

        redis_client = await self._get_redis_client()
        if redis_client is None:
            return False

        cache_key = self._generate_cache_key(provider, media_type, data)

        try:
            result = await redis_client.delete(cache_key)
            logger.info("Cache invalidated", cache_key=cache_key, existed=bool(result))
            return bool(result)

        except Exception as exc:
            logger.error(
                "Cache invalidation failed", cache_key=cache_key, error=str(exc)
            )
            return False

    def get_hit_rate(self) -> float:
        """
        Calculate cache hit rate.

        Returns:
            Hit rate as float (0.0 to 1.0)
        """
        total = self._cache_hits + self._cache_misses
        if total == 0:
            return 0.0
        return self._cache_hits / total

    def get_metrics(self) -> dict:
        """
        Get cache metrics.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "enabled": self.enabled,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": self.get_hit_rate(),
            "bytes_saved": self._bytes_saved,
            "ttl_hours": self.ttl_hours,
            "compression_threshold": self.compression_threshold,
        }

    async def close(self):
        """Close Redis connection."""
        if self._redis_client is not None:
            await self._redis_client.close()
            self._redis_client = None


# Global cache instance
_global_cache: Optional[ExtractionCache] = None


def get_extraction_cache() -> ExtractionCache:
    """
    Get global extraction cache instance (singleton).

    Returns:
        ExtractionCache instance
    """
    global _global_cache

    if _global_cache is None:
        _global_cache = ExtractionCache()

    return _global_cache


async def close_extraction_cache():
    """Close global extraction cache."""
    global _global_cache

    if _global_cache is not None:
        await _global_cache.close()
        _global_cache = None
