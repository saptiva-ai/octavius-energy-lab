"""
Idempotency helpers for document uploads.
"""

from __future__ import annotations

from typing import Optional

import structlog

from ..core.redis_cache import get_redis_cache
from ..schemas.files import FileIngestResponse

logger = structlog.get_logger(__name__)


class UploadIdempotencyRepository:
    """Persists upload responses keyed by (user_id, idempotency_key)."""

    KEY_PREFIX = "upload-idk"
    DEFAULT_TTL_SECONDS = 3600

    async def get(self, user_id: str, key: str) -> Optional[FileIngestResponse]:
        redis_cache = await get_redis_cache()
        redis_key = self._build_key(user_id, key)
        cached = await redis_cache.client.get(redis_key)
        if not cached:
            return None
        try:
            return FileIngestResponse.model_validate_json(cached)
        except Exception as exc:
            logger.warning("Failed to deserialize idempotency payload", error=str(exc))
            await redis_cache.client.delete(redis_key)
            return None

    async def set(
        self,
        user_id: str,
        key: str,
        response: FileIngestResponse,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        redis_cache = await get_redis_cache()
        redis_key = self._build_key(user_id, key)
        await redis_cache.client.setex(
            redis_key, ttl_seconds, response.model_dump_json()
        )

    def _build_key(self, user_id: str, key: str) -> str:
        return f"{self.KEY_PREFIX}:{user_id}:{key}"


upload_idempotency_repository = UploadIdempotencyRepository()
