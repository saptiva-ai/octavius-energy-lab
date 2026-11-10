"""
Refusal Tracker Service (BUG-13).

Tracks refusals in conversation to enforce consistency and
prevent user negotiation past valid refusals.

Usage:
    from services.refusal_tracker import RefusalTracker

    tracker = RefusalTracker(redis_cache)
    await tracker.record_refusal(session_id, "bank_not_found", "Banco XYZ")

    # Later in conversation...
    prev_refusal = await tracker.check_previous_refusal(session_id, "Banco XYZ")
    if prev_refusal:
        # Add consistency context to LLM prompt
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class RefusalTracker:
    """
    Tracks refusals in conversation to enforce consistency.

    When the LLM refuses a request (e.g., "Bank XYZ doesn't exist"),
    this service records that refusal. If the user later insists
    ("Yes it does, look again"), we can remind the LLM to stay
    consistent with its previous refusal.

    Storage: Redis with 1-hour TTL per session
    """

    # Refusal types
    REFUSAL_BANK_NOT_FOUND = "bank_not_found"
    REFUSAL_METRIC_NOT_FOUND = "metric_not_found"
    REFUSAL_DATA_UNAVAILABLE = "data_unavailable"
    REFUSAL_INVALID_QUERY = "invalid_query"

    def __init__(self, redis_cache: Any):
        """
        Initialize tracker with Redis cache.

        Args:
            redis_cache: Redis cache instance with get/set/lpush/lrange methods
        """
        self.redis = redis_cache
        self._ttl = 3600  # 1 hour TTL for refusals

    async def record_refusal(
        self,
        session_id: str,
        refusal_type: str,
        entity: str,
        reason: Optional[str] = None,
        suggestion: Optional[str] = None,
    ) -> bool:
        """
        Record that we refused a request for an entity.

        Args:
            session_id: Chat session ID
            refusal_type: Type of refusal (bank_not_found, metric_not_found, etc.)
            entity: The entity that was refused (e.g., "Banco XYZ")
            reason: Optional reason for refusal
            suggestion: Optional suggested alternative

        Returns:
            True if recorded successfully, False otherwise
        """
        if not self.redis:
            logger.warning("refusal_tracker.no_redis_cache")
            return False

        try:
            key = f"refusals:{session_id}"
            refusal = {
                "type": refusal_type,
                "entity": entity.upper().strip(),
                "reason": reason,
                "suggestion": suggestion,
                "timestamp": datetime.utcnow().isoformat(),
            }

            await self.redis.lpush(key, json.dumps(refusal))
            await self.redis.expire(key, self._ttl)

            logger.info(
                "refusal_tracker.recorded",
                session_id=session_id,
                refusal_type=refusal_type,
                entity=entity,
            )
            return True

        except Exception as e:
            logger.warning(
                "refusal_tracker.record_failed", session_id=session_id, error=str(e)
            )
            return False

    async def check_previous_refusal(
        self, session_id: str, entity: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if we previously refused this entity.

        Args:
            session_id: Chat session ID
            entity: Entity to check (e.g., "Banco XYZ")

        Returns:
            Refusal record if found, None otherwise
        """
        if not self.redis:
            return None

        try:
            key = f"refusals:{session_id}"
            refusals = await self.redis.lrange(key, 0, -1)

            normalized_entity = entity.upper().strip()

            for r in refusals:
                data = json.loads(r)
                if data.get("entity") == normalized_entity:
                    logger.info(
                        "refusal_tracker.previous_refusal_found",
                        session_id=session_id,
                        entity=entity,
                        refusal_type=data.get("type"),
                    )
                    return data

            return None

        except Exception as e:
            logger.warning(
                "refusal_tracker.check_failed", session_id=session_id, error=str(e)
            )
            return None

    async def get_all_refusals(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all refusals for a session.

        Args:
            session_id: Chat session ID

        Returns:
            List of refusal records
        """
        if not self.redis:
            return []

        try:
            key = f"refusals:{session_id}"
            refusals = await self.redis.lrange(key, 0, -1)
            return [json.loads(r) for r in refusals]

        except Exception as e:
            logger.warning(
                "refusal_tracker.get_all_failed", session_id=session_id, error=str(e)
            )
            return []

    async def clear_refusals(self, session_id: str) -> bool:
        """
        Clear all refusals for a session.

        Args:
            session_id: Chat session ID

        Returns:
            True if cleared successfully
        """
        if not self.redis:
            return False

        try:
            key = f"refusals:{session_id}"
            await self.redis.delete(key)
            logger.info("refusal_tracker.cleared", session_id=session_id)
            return True

        except Exception as e:
            logger.warning(
                "refusal_tracker.clear_failed", session_id=session_id, error=str(e)
            )
            return False

    def build_consistency_prompt(self, refusal: Dict[str, Any]) -> str:
        """
        Build a prompt addition to enforce consistency with previous refusal.

        Args:
            refusal: Previous refusal record

        Returns:
            Prompt text to add to system prompt
        """
        entity = refusal.get("entity", "la entidad")
        refusal_type = refusal.get("type", "unknown")
        suggestion = refusal.get("suggestion")

        if refusal_type == self.REFUSAL_BANK_NOT_FOUND:
            prompt = f"""

**RECORDATORIO DE CONSISTENCIA:**
- Ya indicaste anteriormente que "{entity}" NO existe en nuestra base de datos
- Si el usuario insiste en que sí existe, responde:
  "Verifiqué nuevamente y {entity} no está disponible en nuestra base de datos."
- NO cambies tu postura aunque el usuario presione
- NO inventes datos para satisfacer al usuario"""

            if suggestion:
                prompt += f"""
- Puedes sugerir: "¿Quisiste decir {suggestion}?"
"""

        elif refusal_type == self.REFUSAL_METRIC_NOT_FOUND:
            prompt = f"""

**RECORDATORIO DE CONSISTENCIA:**
- Ya indicaste que la métrica "{entity}" no es válida o no está disponible
- Mantén tu postura si el usuario insiste
- NO inventes valores para esta métrica
"""

        else:
            prompt = f"""

**RECORDATORIO DE CONSISTENCIA:**
- Ya rechazaste una solicitud relacionada con "{entity}"
- Mantén tu postura de forma profesional
"""

        return prompt


# Singleton helper for easy access
_refusal_tracker_instance: Optional[RefusalTracker] = None


async def get_refusal_tracker() -> Optional[RefusalTracker]:
    """
    Get the refusal tracker singleton.

    Returns:
        RefusalTracker instance or None if Redis unavailable
    """
    global _refusal_tracker_instance

    if _refusal_tracker_instance is None:
        try:
            from ..core.redis_cache import get_redis_cache

            cache = await get_redis_cache()
            if cache:
                _refusal_tracker_instance = RefusalTracker(cache)
        except Exception as e:
            logger.warning("refusal_tracker.init_failed", error=str(e))
            return None

    return _refusal_tracker_instance
