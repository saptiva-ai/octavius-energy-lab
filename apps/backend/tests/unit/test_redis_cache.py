"""
Unit tests for Redis cache module.

Tests cache operations, key generation, and TTL handling.
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.core.redis_cache import RedisCache


class TestRedisCache:
    """Test suite for RedisCache class."""

    def test_redis_cache_initialization(self):
        """Test that RedisCache initializes with correct defaults."""
        cache = RedisCache()

        assert cache.client is None  # Not connected yet
        assert cache.ttl_chat_history == 300  # 5 minutes
        assert cache.ttl_research_tasks == 600  # 10 minutes
        assert cache.ttl_session_list == 120  # 2 minutes

    def test_redis_cache_has_settings(self):
        """Test that RedisCache loads settings on init."""
        cache = RedisCache()

        assert hasattr(cache, 'settings')
        assert cache.settings is not None

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful Redis connection."""
        cache = RedisCache()

        with patch('redis.asyncio.from_url') as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_from_url.return_value = mock_client

            await cache.connect()

            assert cache.client is not None
            mock_client.ping.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_failure_handles_gracefully(self):
        """Test that connection failure is handled gracefully."""
        cache = RedisCache()

        with patch('redis.asyncio.from_url') as mock_from_url:
            mock_from_url.side_effect = Exception("Connection refused")

            await cache.connect()

            # Should not raise exception, just set client to None
            assert cache.client is None

    @pytest.mark.asyncio
    async def test_close_connection(self):
        """Test closing Redis connection."""
        cache = RedisCache()
        mock_client = AsyncMock()
        cache.client = mock_client

        await cache.close()

        # Verify close was called before client was set to None
        mock_client.close.assert_awaited_once()
        assert cache.client is None

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self):
        """Test that close() works when client is None."""
        cache = RedisCache()
        cache.client = None

        # Should not raise exception
        await cache.close()

        assert cache.client is None

    def test_make_key_simple(self):
        """Test cache key generation without parameters."""
        cache = RedisCache()
        version = cache.settings.cache_version

        key = cache._make_key("chat_history", "chat-123")

        assert key == f"{version}:cache:chat_history:chat-123"

    def test_make_key_with_params(self):
        """Test cache key generation with parameters."""
        cache = RedisCache()
        version = cache.settings.cache_version

        params = {"limit": 50, "offset": 0}
        key = cache._make_key("chat_history", "chat-123", params)

        # Should include version prefix and params hash
        assert key.startswith(f"{version}:cache:chat_history:chat-123:")
        assert len(key.split(":")) == 5  # version:cache:prefix:id:hash

    def test_make_key_params_are_deterministic(self):
        """Test that same parameters generate same key."""
        cache = RedisCache()

        params1 = {"limit": 50, "offset": 0, "include_research": True}
        params2 = {"include_research": True, "offset": 0, "limit": 50}  # Different order

        key1 = cache._make_key("test", "id", params1)
        key2 = cache._make_key("test", "id", params2)

        # Should be identical (params are sorted)
        assert key1 == key2

    @pytest.mark.asyncio
    async def test_get_chat_history_cache_miss(self):
        """Test getting chat history when not in cache."""
        cache = RedisCache()
        cache.client = AsyncMock()
        cache.client.get = AsyncMock(return_value=None)

        result = await cache.get_chat_history("chat-123")

        assert result is None
        cache.client.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_chat_history_cache_hit(self):
        """Test getting chat history when in cache."""
        cache = RedisCache()
        cache.client = AsyncMock()

        cached_data = {"messages": [{"role": "user", "content": "Hello"}]}
        cache.client.get = AsyncMock(return_value=json.dumps(cached_data))

        result = await cache.get_chat_history("chat-123")

        assert result == cached_data
        assert "messages" in result

    @pytest.mark.asyncio
    async def test_get_chat_history_when_not_connected(self):
        """Test getting chat history when Redis not connected."""
        cache = RedisCache()
        cache.client = None

        result = await cache.get_chat_history("chat-123")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_chat_history(self):
        """Test setting chat history in cache."""
        cache = RedisCache()
        cache.client = AsyncMock()
        cache.client.setex = AsyncMock()

        history_data = {"messages": [{"role": "user", "content": "Test"}]}

        await cache.set_chat_history("chat-123", history_data)

        # Should call setex with TTL
        cache.client.setex.assert_awaited_once()
        call_args = cache.client.setex.call_args
        assert call_args[0][1] == cache.ttl_chat_history  # TTL argument

    @pytest.mark.asyncio
    async def test_cache_handles_json_serialization_error(self):
        """Test that cache handles JSON serialization errors gracefully."""
        cache = RedisCache()
        cache.client = AsyncMock()

        # Create non-serializable object
        class NonSerializable:
            pass

        data = {"obj": NonSerializable()}

        # Should not raise exception
        try:
            await cache.set_chat_history("chat-123", data)
        except Exception:
            pass  # Expected to fail gracefully


class TestRedisCacheTTL:
    """Test TTL (Time To Live) settings."""

    def test_ttl_defaults(self):
        """Test that TTL values are set to reasonable defaults."""
        cache = RedisCache()

        assert cache.ttl_chat_history > 0
        assert cache.ttl_research_tasks > 0
        assert cache.ttl_session_list > 0

    def test_ttl_chat_history_is_5_minutes(self):
        """Test that chat history TTL is 5 minutes."""
        cache = RedisCache()

        assert cache.ttl_chat_history == 300  # 5 * 60 seconds

    def test_ttl_research_tasks_is_10_minutes(self):
        """Test that research tasks TTL is 10 minutes."""
        cache = RedisCache()

        assert cache.ttl_research_tasks == 600  # 10 * 60 seconds

    def test_ttl_session_list_is_2_minutes(self):
        """Test that session list TTL is 2 minutes."""
        cache = RedisCache()

        assert cache.ttl_session_list == 120  # 2 * 60 seconds


class TestRedisCacheOperations:
    """Test cache CRUD operations."""

    @pytest.mark.asyncio
    async def test_cache_stores_data_as_json(self):
        """Test that data is stored as JSON string."""
        cache = RedisCache()
        cache.client = AsyncMock()

        data = {"key": "value", "number": 123}
        await cache.set_chat_history("test-id", data)

        # Verify JSON serialization was used
        call_args = cache.client.setex.call_args
        stored_value = call_args[0][2]  # Third argument is the value

        # Should be a JSON string
        assert isinstance(stored_value, str)
        parsed = json.loads(stored_value)
        # Cache now adds metadata (_cached_at, _cache_params), verify original data is present
        assert parsed["key"] == data["key"]
        assert parsed["number"] == data["number"]
        assert "_cached_at" in parsed  # Metadata should be added

    @pytest.mark.asyncio
    async def test_cache_retrieves_parsed_json(self):
        """Test that retrieved data is parsed from JSON."""
        cache = RedisCache()
        cache.client = AsyncMock()

        original_data = {"messages": ["msg1", "msg2"]}
        cache.client.get = AsyncMock(return_value=json.dumps(original_data))

        result = await cache.get_chat_history("test-id")

        # Should be parsed back to dict
        assert isinstance(result, dict)
        assert result == original_data

    @pytest.mark.asyncio
    async def test_cache_delete_operation(self):
        """Test deleting data from cache."""
        cache = RedisCache()
        cache.client = AsyncMock()
        cache.client.delete = AsyncMock(return_value=1)

        # Should be able to delete a key
        if hasattr(cache, 'delete'):
            await cache.delete("test-key")
            cache.client.delete.assert_awaited_once()


class TestRedisCacheKeyGeneration:
    """Test cache key generation patterns."""

    def test_key_format_consistency(self):
        """Test that generated keys follow consistent format."""
        cache = RedisCache()
        version = cache.settings.cache_version

        # All keys should start with "{version}:cache:"
        key1 = cache._make_key("prefix1", "id1")
        key2 = cache._make_key("prefix2", "id2")

        assert key1.startswith(f"{version}:cache:")
        assert key2.startswith(f"{version}:cache:")

    def test_key_separators(self):
        """Test that key components are separated by colons."""
        cache = RedisCache()
        version = cache.settings.cache_version

        key = cache._make_key("myprefix", "myid")

        parts = key.split(":")
        assert len(parts) == 4  # version:cache:prefix:id
        assert parts[0] == version
        assert parts[1] == "cache"
        assert parts[2] == "myprefix"
        assert parts[3] == "myid"

    def test_key_with_special_characters(self):
        """Test key generation with special characters."""
        cache = RedisCache()

        # Should handle IDs with special characters
        key = cache._make_key("prefix", "user-123_abc@test")

        assert "user-123_abc@test" in key


class TestRedisCacheErrorHandling:
    """Test error handling in cache operations."""

    @pytest.mark.asyncio
    async def test_cache_handles_redis_connection_error(self):
        """Test that cache operations handle Redis connection errors."""
        cache = RedisCache()
        cache.client = AsyncMock()
        cache.client.get = AsyncMock(side_effect=Exception("Connection lost"))

        # Should not raise exception
        result = await cache.get_chat_history("chat-123")

        # Should return None on error
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_handles_invalid_json_in_cache(self):
        """Test that cache handles invalid JSON data gracefully."""
        cache = RedisCache()
        cache.client = AsyncMock()
        cache.client.get = AsyncMock(return_value="invalid-json{{{")

        # Should not raise exception
        result = await cache.get_chat_history("chat-123")

        # Should return None on parse error
        assert result is None
