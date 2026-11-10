"""
Cache service for Redis operations.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import redis.asyncio as redis
import structlog

from ..core.config import get_settings

logger = structlog.get_logger(__name__)

_redis_client: redis.Redis | None = None


async def get_redis_client() -> redis.Redis:
    """
    Get a Redis client, initializing it if needed.
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        # Sin credenciales en el log (P0-8 de la auditoría).
        url = urlsplit(settings.redis_url)
        logger.info(
            "Initializing Redis client",
            url=f"{url.scheme}://{url.hostname}:{url.port}{url.path}",
        )
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def add_token_to_blacklist(token: str, expires_at: int) -> None:
    """
    Add a token to the blacklist with an expiration time.
    """
    client = await get_redis_client()
    jti = token  # Use the token itself as the key
    await client.set(f"blacklist:{jti}", "blacklisted", exat=expires_at)
    logger.info("Token blacklisted", jti=jti)


async def is_token_blacklisted(token: str) -> bool:
    """
    Check if a token is in the blacklist.
    """
    client = await get_redis_client()
    jti = token
    result = await client.get(f"blacklist:{jti}")
    return result is not None
