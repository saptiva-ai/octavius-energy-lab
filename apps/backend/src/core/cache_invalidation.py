"""
Event-driven cache invalidation via Redis Pub/Sub.

Publishes and subscribes to invalidation events so that cache layers
are flushed when underlying data changes (ETL ingest, deploy, handler update).

Usage:
    # Publish (from ETL script, CI/CD, or internal endpoint):
    await publish_invalidation(redis_client, InvalidationEvent.ETL_COMPLETE)

    # Subscribe (started as background task in lifespan):
    asyncio.create_task(start_invalidation_listener(redis_client))
"""

import asyncio
import json
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

CHANNEL = "cache:invalidate"


class InvalidationEvent(str, Enum):
    ETL_COMPLETE = "etl_complete"
    DEPLOY_COMPLETE = "deploy_complete"
    HANDLER_CHANGE = "handler_change"


async def publish_invalidation(
    redis_client,
    event: InvalidationEvent,
    metadata: Optional[dict] = None,
) -> int:
    """Publish cache invalidation event. Returns number of subscribers that received it."""
    payload = json.dumps({"event": event.value, **(metadata or {})})
    receivers = await redis_client.publish(CHANNEL, payload)
    logger.info(
        "cache_invalidation.published",
        invalidation_event=event.value,
        receivers=receivers,
        metadata=metadata,
    )
    return receivers


async def start_invalidation_listener(redis_client) -> None:
    """Subscribe and handle invalidation events. Run as background task."""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(CHANNEL)
    logger.info("cache_invalidation.listener_started", channel=CHANNEL)

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = message.get("data", "")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                parsed = json.loads(data)
                await _handle_invalidation(parsed)
            except Exception as e:
                logger.error("cache_invalidation.handler_error", error=str(e))
    except asyncio.CancelledError:
        logger.info("cache_invalidation.listener_stopped")
        await pubsub.unsubscribe(CHANNEL)
        await pubsub.close()
    except Exception as e:
        logger.error("cache_invalidation.listener_fatal", error=str(e))


async def _handle_invalidation(payload: dict) -> None:
    """Route invalidation event to appropriate cache layers."""
    event_type = payload.get("event")
    logger.info("cache_invalidation.handling", invalidation_event=event_type)

    if event_type == InvalidationEvent.ETL_COMPLETE:
        await _flush_etl_caches(payload)
    elif event_type == InvalidationEvent.DEPLOY_COMPLETE:
        await _flush_deploy_caches(payload)
    elif event_type == InvalidationEvent.HANDLER_CHANGE:
        await _flush_handler_caches(payload)
    else:
        logger.warning(
            "cache_invalidation.unknown_event", invalidation_event=event_type
        )


async def _flush_etl_caches(payload: dict) -> None:
    """Flush caches affected by new ETL data (response classification + tool results)."""
    from ..services.mcp_cache import invalidate_all_tool_caches
    from .redis_cache import get_redis_cache

    cache = await get_redis_cache()
    await cache.delete_pattern("*:query_classification:*")
    tool_deleted = await invalidate_all_tool_caches()
    logger.info(
        "cache_invalidation.etl_flushed",
        caches=[
            "query_classification",
            "mcp_tool_results",
        ],
        tool_keys_deleted=tool_deleted,
        metadata=payload.get("metadata"),
    )


async def _flush_deploy_caches(payload: dict) -> None:
    """Flush caches affected by new deploy (MCP tool results).

    Note: versioned caches (chat_history, research_tasks) are handled
    automatically by CACHE_VERSION bump — no explicit flush needed.
    """
    from ..services.mcp_cache import invalidate_all_tool_caches

    deleted = await invalidate_all_tool_caches()
    logger.info(
        "cache_invalidation.deploy_flushed",
        caches=["mcp_tool_results"],
        keys_deleted=deleted,
    )


async def _flush_handler_caches(payload: dict) -> None:
    """Flush caches for a specific handler that changed."""
    handler = payload.get("handler")
    from .redis_cache import get_redis_cache

    cache = await get_redis_cache()
    await cache.delete_pattern("*:bank_query_classification:*")
    logger.info(
        "cache_invalidation.handler_flushed",
        handler=handler,
        caches=["bank_query_classification"],
    )
