"""
Unit tests for cache service.

Tests Redis-based caching operations with mocked Redis client.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time

from src.services.cache_service import (
    get_redis_client,
    add_token_to_blacklist,
    is_token_blacklisted
)


@pytest.mark.unit
class TestCacheService:
    """Test cache service operations"""

    @pytest.mark.asyncio
    async def test_get_redis_client_singleton(self):
        """Test get_redis_client returns singleton instance"""
        with patch('src.services.cache_service.redis.from_url') as mock_from_url:
            mock_client = AsyncMock()
            mock_from_url.return_value = mock_client

            # Reset the global client
            import src.services.cache_service as cache_module
            cache_module._redis_client = None

            # First call should create client
            client1 = await get_redis_client()
            assert client1 is not None
            mock_from_url.assert_called_once()

            # Second call should reuse same client
            client2 = await get_redis_client()
            assert client2 is client1
            # from_url should still have been called only once
            assert mock_from_url.call_count == 1

    @pytest.mark.asyncio
    async def test_add_token_to_blacklist(self):
        """Test adding token to blacklist"""
        mock_client = AsyncMock()
        mock_client.set = AsyncMock()

        with patch('src.services.cache_service.get_redis_client', return_value=mock_client):
            token = "token-abc-123"
            expires_at = int(time.time()) + 3600

            await add_token_to_blacklist(token, expires_at)

            # Verify Redis set was called with correct parameters
            mock_client.set.assert_called_once_with(
                f"blacklist:{token}",
                "blacklisted",
                exat=expires_at
            )

    @pytest.mark.asyncio
    async def test_is_token_blacklisted_true(self):
        """Test checking if token is blacklisted (exists in Redis)"""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value="blacklisted")

        with patch('src.services.cache_service.get_redis_client', return_value=mock_client):
            token = "blacklisted-token"

            result = await is_token_blacklisted(token)

            assert result is True
            mock_client.get.assert_called_once_with(f"blacklist:{token}")

    @pytest.mark.asyncio
    async def test_is_token_blacklisted_false(self):
        """Test checking if token is not blacklisted (not in Redis)"""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)

        with patch('src.services.cache_service.get_redis_client', return_value=mock_client):
            token = "valid-token"

            result = await is_token_blacklisted(token)

            assert result is False
            mock_client.get.assert_called_once_with(f"blacklist:{token}")

    @pytest.mark.asyncio
    async def test_token_blacklist_key_format(self):
        """Test that blacklist keys use correct format"""
        mock_client = AsyncMock()
        mock_client.set = AsyncMock()

        with patch('src.services.cache_service.get_redis_client', return_value=mock_client):
            token = "my-token"
            expires_at = int(time.time()) + 1800

            await add_token_to_blacklist(token, expires_at)

            # Verify the key starts with "blacklist:"
            call_args = mock_client.set.call_args
            assert call_args[0][0].startswith("blacklist:")
            assert token in call_args[0][0]

    @pytest.mark.asyncio
    async def test_add_multiple_tokens_to_blacklist(self):
        """Test adding multiple tokens to blacklist"""
        mock_client = AsyncMock()
        mock_client.set = AsyncMock()

        with patch('src.services.cache_service.get_redis_client', return_value=mock_client):
            tokens = ["token-1", "token-2", "token-3"]
            expires_at = int(time.time()) + 3600

            for token in tokens:
                await add_token_to_blacklist(token, expires_at)

            # Verify set was called for each token
            assert mock_client.set.call_count == 3

    @pytest.mark.asyncio
    async def test_is_token_blacklisted_different_tokens(self):
        """Test checking multiple tokens for blacklist status"""
        mock_client = AsyncMock()

        # Token 1 is blacklisted, token 2 is not
        def mock_get(key):
            if "token-1" in key:
                return "blacklisted"
            return None

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch('src.services.cache_service.get_redis_client', return_value=mock_client):
            result1 = await is_token_blacklisted("token-1")
            result2 = await is_token_blacklisted("token-2")

            assert result1 is True
            assert result2 is False
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_token_expiration_time(self):
        """Test that expiration time is passed correctly"""
        mock_client = AsyncMock()
        mock_client.set = AsyncMock()

        with patch('src.services.cache_service.get_redis_client', return_value=mock_client):
            token = "temp-token"
            future_time = int(time.time()) + 7200  # 2 hours from now

            await add_token_to_blacklist(token, future_time)

            # Verify the exat parameter matches our future time
            call_args = mock_client.set.call_args
            assert call_args[1]['exat'] == future_time

    @pytest.mark.asyncio
    async def test_redis_client_initialization_with_settings(self):
        """Test Redis client is initialized with correct URL from settings"""
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"

        with patch('src.services.cache_service.get_settings', return_value=mock_settings):
            with patch('src.services.cache_service.redis.from_url') as mock_from_url:
                mock_client = AsyncMock()
                mock_from_url.return_value = mock_client

                # Reset client
                import src.services.cache_service as cache_module
                cache_module._redis_client = None

                await get_redis_client()

                # Verify from_url was called with correct URL
                mock_from_url.assert_called_once_with(
                    "redis://localhost:6379/0",
                    decode_responses=True
                )
