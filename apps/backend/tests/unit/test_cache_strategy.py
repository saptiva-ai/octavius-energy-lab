"""
Unit tests for Fase 1: Cache strategy improvements.

Tests SCAN-based invalidation, version prefix, and rate limiter Redis storage.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
class TestScanKeysHelper:
    """Test that _scan_keys uses SCAN instead of KEYS."""

    @pytest.mark.asyncio
    async def test_scan_keys_uses_scan_not_keys(self):
        """Verify _scan_keys iterates with SCAN cursor, never calls KEYS."""
        from src.core.redis_cache import RedisCache

        cache = RedisCache.__new__(RedisCache)
        cache.client = AsyncMock()
        cache.settings = MagicMock()

        # Simulate SCAN returning keys in two batches
        cache.client.scan = AsyncMock(
            side_effect=[
                (42, ["v1:cache:chat_history:abc:1", "v1:cache:chat_history:abc:2"]),
                (0, ["v1:cache:chat_history:abc:3"]),
            ]
        )

        keys = await cache._scan_keys("*:cache:chat_history:abc*")

        assert len(keys) == 3
        assert cache.client.scan.call_count == 2
        # First call starts at cursor 0
        cache.client.scan.assert_any_call(0, match="*:cache:chat_history:abc*", count=200)
        # Second call continues at cursor 42
        cache.client.scan.assert_any_call(42, match="*:cache:chat_history:abc*", count=200)

    @pytest.mark.asyncio
    async def test_scan_keys_returns_empty_when_no_client(self):
        """Verify _scan_keys returns empty list when Redis is not connected."""
        from src.core.redis_cache import RedisCache

        cache = RedisCache.__new__(RedisCache)
        cache.client = None
        cache.settings = MagicMock()

        keys = await cache._scan_keys("some:pattern*")
        assert keys == []

    @pytest.mark.asyncio
    async def test_invalidate_chat_history_uses_scan(self):
        """Verify invalidate_chat_history calls _scan_keys, not client.keys."""
        from src.core.redis_cache import RedisCache

        cache = RedisCache.__new__(RedisCache)
        cache.client = AsyncMock()
        cache.settings = MagicMock()

        cache._scan_keys = AsyncMock(return_value=["key1", "key2"])

        await cache.invalidate_chat_history("chat-123")

        # _scan_keys should be called for each pattern
        assert cache._scan_keys.call_count == 2
        # client.keys should NOT be called
        cache.client.keys.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_pattern_uses_scan(self):
        """Verify delete_pattern calls _scan_keys, not client.keys."""
        from src.core.redis_cache import RedisCache

        cache = RedisCache.__new__(RedisCache)
        cache.client = AsyncMock()
        cache.settings = MagicMock()

        cache._scan_keys = AsyncMock(return_value=["key1"])

        await cache.delete_pattern("some:pattern*")

        cache._scan_keys.assert_called_once_with("some:pattern*")
        cache.client.keys.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalidate_research_tasks_uses_scan(self):
        """Verify invalidate_research_tasks calls _scan_keys, not client.keys."""
        from src.core.redis_cache import RedisCache

        cache = RedisCache.__new__(RedisCache)
        cache.client = AsyncMock()
        cache.settings = MagicMock()

        cache._scan_keys = AsyncMock(return_value=["key1"])

        await cache.invalidate_research_tasks("session-456")

        cache._scan_keys.assert_called_once_with("*:cache:research_tasks:session-456*")
        cache.client.keys.assert_not_called()


@pytest.mark.unit
class TestCacheVersionPrefix:
    """Test that _make_key includes CACHE_VERSION prefix."""

    def test_make_key_includes_version(self):
        """Verify _make_key prepends cache_version to the key."""
        from src.core.redis_cache import RedisCache

        cache = RedisCache.__new__(RedisCache)
        cache.settings = MagicMock()
        cache.settings.cache_version = "v3"

        key = cache._make_key("chat_history", "abc123")
        assert key == "v3:cache:chat_history:abc123"

    def test_make_key_includes_version_with_params(self):
        """Verify _make_key includes version even with params hash."""
        from src.core.redis_cache import RedisCache

        cache = RedisCache.__new__(RedisCache)
        cache.settings = MagicMock()
        cache.settings.cache_version = "v2"

        key = cache._make_key("chat_history", "abc123", {"limit": 50})
        assert key.startswith("v2:cache:chat_history:abc123:")
        # The params hash should be appended
        parts = key.split(":")
        assert len(parts) == 5

    def test_version_bump_produces_different_key(self):
        """Verify that bumping cache_version changes the key (cache miss)."""
        from src.core.redis_cache import RedisCache

        cache = RedisCache.__new__(RedisCache)
        cache.settings = MagicMock()

        cache.settings.cache_version = "v1"
        key_v1 = cache._make_key("chat_history", "abc123")

        cache.settings.cache_version = "v2"
        key_v2 = cache._make_key("chat_history", "abc123")

        assert key_v1 != key_v2
        assert key_v1.startswith("v1:")
        assert key_v2.startswith("v2:")


@pytest.mark.unit
class TestRateLimiterStorage:
    """Test that rate limiter uses Redis when available."""

    def test_rate_limiter_uses_redis_when_env_set(self):
        """Verify _get_rate_limit_storage_uri returns Redis URL when set."""
        with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/0"}):
            from src.middleware.rate_limit import _get_rate_limit_storage_uri

            uri = _get_rate_limit_storage_uri()
            assert uri == "redis://localhost:6379/0"

    def test_rate_limiter_falls_back_to_memory(self):
        """Verify _get_rate_limit_storage_uri falls back to memory:// without Redis."""
        with patch.dict("os.environ", {"REDIS_URL": ""}):
            from src.middleware.rate_limit import _get_rate_limit_storage_uri

            uri = _get_rate_limit_storage_uri()
            assert uri == "memory://"

    def test_rate_limiter_falls_back_when_no_env(self):
        """Verify fallback when REDIS_URL is not in env at all."""
        with patch.dict("os.environ", {}, clear=True):
            from src.middleware.rate_limit import _get_rate_limit_storage_uri

            uri = _get_rate_limit_storage_uri()
            assert uri == "memory://"
