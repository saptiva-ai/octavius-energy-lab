"""
Unit tests for Fase 2: Event-driven cache invalidation via Pub/Sub.

Tests publish/subscribe flow, event routing, and cache flush handlers.
"""

import json

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.unit
class TestPublishInvalidation:
    """Test publishing invalidation events."""

    @pytest.mark.asyncio
    async def test_publish_etl_complete(self):
        """Verify publish sends correct JSON payload to Redis Pub/Sub."""
        from src.core.cache_invalidation import (
            CHANNEL,
            InvalidationEvent,
            publish_invalidation,
        )

        redis_client = AsyncMock()
        redis_client.publish = AsyncMock(return_value=1)

        receivers = await publish_invalidation(
            redis_client,
            InvalidationEvent.ETL_COMPLETE,
            metadata={"periodo": "202512"},
        )

        assert receivers == 1
        redis_client.publish.assert_called_once()
        call_args = redis_client.publish.call_args
        assert call_args[0][0] == CHANNEL
        payload = json.loads(call_args[0][1])
        assert payload["event"] == "etl_complete"
        assert payload["periodo"] == "202512"

    @pytest.mark.asyncio
    async def test_publish_deploy_complete(self):
        """Verify deploy_complete event is published correctly."""
        from src.core.cache_invalidation import InvalidationEvent, publish_invalidation

        redis_client = AsyncMock()
        redis_client.publish = AsyncMock(return_value=2)

        receivers = await publish_invalidation(
            redis_client, InvalidationEvent.DEPLOY_COMPLETE
        )

        assert receivers == 2
        payload = json.loads(redis_client.publish.call_args[0][1])
        assert payload["event"] == "deploy_complete"

    @pytest.mark.asyncio
    async def test_publish_with_no_metadata(self):
        """Verify publish works without metadata."""
        from src.core.cache_invalidation import InvalidationEvent, publish_invalidation

        redis_client = AsyncMock()
        redis_client.publish = AsyncMock(return_value=0)

        receivers = await publish_invalidation(
            redis_client, InvalidationEvent.HANDLER_CHANGE
        )

        assert receivers == 0
        payload = json.loads(redis_client.publish.call_args[0][1])
        assert payload["event"] == "handler_change"
        assert set(payload.keys()) == {"event"}


@pytest.mark.unit
class TestHandleInvalidation:
    """Test that events are routed to correct flush handlers."""

    @pytest.mark.asyncio
    async def test_etl_complete_flushes_classification(self):
        """Verify etl_complete flushes query_classification cache."""
        from src.core.cache_invalidation import _handle_invalidation

        mock_cache = AsyncMock()
        mock_cache.delete_pattern = AsyncMock()

        with patch(
            "src.core.redis_cache.get_redis_cache",
            new_callable=AsyncMock,
            return_value=mock_cache,
        ):
            await _handle_invalidation({"event": "etl_complete"})

        mock_cache.delete_pattern.assert_called_once_with(
            "*:query_classification:*"
        )

    @pytest.mark.asyncio
    async def test_deploy_complete_flushes_mcp(self):
        """Verify deploy_complete flushes MCP tool caches."""
        from src.core.cache_invalidation import _handle_invalidation

        with patch(
            "src.services.mcp_cache.invalidate_all_tool_caches",
            new_callable=AsyncMock,
            return_value=42,
        ) as mock_invalidate:
            await _handle_invalidation({"event": "deploy_complete"})

        mock_invalidate.assert_called_once()

    @pytest.mark.asyncio
    async def test_handler_change_flushes_classification(self):
        """Verify handler_change flushes classification for the specified handler."""
        from src.core.cache_invalidation import _handle_invalidation

        mock_cache = AsyncMock()
        mock_cache.delete_pattern = AsyncMock()

        with patch(
            "src.core.redis_cache.get_redis_cache",
            new_callable=AsyncMock,
            return_value=mock_cache,
        ):
            await _handle_invalidation(
                {"event": "handler_change", "handler": "evolucion_ventas"}
            )

        # NOTE: el src (core/cache_invalidation.py:137) aún usa el patrón residual
        # "bank_query_classification" en la ruta handler_change (etl_complete ya migró
        # a "query_classification"). Alinear en terminar-debanking-src.
        mock_cache.delete_pattern.assert_called_once_with(
            "*:bank_query_classification:*"
        )

    @pytest.mark.asyncio
    async def test_unknown_event_does_not_crash(self):
        """Verify unknown events are logged but don't raise."""
        from src.core.cache_invalidation import _handle_invalidation

        # Should not raise
        await _handle_invalidation({"event": "unknown_event_type"})


@pytest.mark.unit
class TestInvalidationEvent:
    """Test the InvalidationEvent enum."""

    def test_enum_values(self):
        from src.core.cache_invalidation import InvalidationEvent

        assert InvalidationEvent.ETL_COMPLETE.value == "etl_complete"
        assert InvalidationEvent.DEPLOY_COMPLETE.value == "deploy_complete"
        assert InvalidationEvent.HANDLER_CHANGE.value == "handler_change"

    def test_enum_from_string(self):
        from src.core.cache_invalidation import InvalidationEvent

        assert InvalidationEvent("etl_complete") == InvalidationEvent.ETL_COMPLETE

    def test_invalid_event_raises(self):
        from src.core.cache_invalidation import InvalidationEvent

        with pytest.raises(ValueError):
            InvalidationEvent("nonexistent_event")
