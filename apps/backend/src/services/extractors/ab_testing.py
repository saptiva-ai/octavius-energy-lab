"""
A/B Testing Framework for Text Extraction

Enables gradual rollout of Saptiva extractor while maintaining ThirdParty
as the control group. Supports percentage-based rollout, user cohorts,
and metric tracking.

Features:
    - Percentage-based traffic splitting (5%, 25%, 50%, 100%)
    - User cohort assignment (consistent per user)
    - Metric tracking (latency, errors, cost)
    - Feature flag integration
    - Rollback capability

Architecture:
    - Cohort assignment based on user_id hash
    - Redis storage for cohort persistence
    - Fallback to control on errors
    - Metric export to observability stack

Usage:
    # Initialize with 25% Saptiva rollout
    ab_test = ABTestingFramework(saptiva_percentage=25)

    # Get extractor for user
    extractor = await ab_test.get_extractor_for_user(user_id)

    # Record metrics
    await ab_test.record_extraction(
        user_id=user_id,
        variant="saptiva",
        latency_ms=150,
        success=True,
    )
"""

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Lazy imports
_redis = None


def _get_redis():
    """Lazy load Redis client."""
    global _redis
    if _redis is None:
        try:
            import redis.asyncio as redis

            _redis = redis
        except ImportError:
            logger.warning("redis package not available for A/B testing")
            _redis = False
    return _redis if _redis is not False else None


class Variant(str, Enum):
    """A/B test variants."""

    CONTROL = "third_party"  # Control group (existing solution)
    TREATMENT = "saptiva"  # Treatment group (new solution)


@dataclass
class ExtractionMetrics:
    """Metrics for a single extraction."""

    user_id: str
    variant: str
    timestamp: str
    media_type: str  # "pdf" or "image"
    latency_ms: float
    success: bool
    error: Optional[str] = None
    file_size_kb: Optional[int] = None
    text_length: Optional[int] = None
    cache_hit: Optional[bool] = None


class ABTestingFramework:
    """
    A/B testing framework for text extraction rollout.

    Implements consistent user cohort assignment based on hashing,
    with configurable percentage rollout and metric tracking.

    Configuration (Environment Variables):
        AB_TEST_ENABLED: Enable A/B testing (default: false)
        AB_TEST_SAPTIVA_PERCENTAGE: Percentage of users in treatment (default: 0)
        AB_TEST_COHORT_TTL_DAYS: How long to cache cohort assignments (default: 30)
        REDIS_URL: Redis connection for cohort storage
    """

    def __init__(
        self,
        saptiva_percentage: Optional[int] = None,
        enabled: Optional[bool] = None,
        redis_url: Optional[str] = None,
    ):
        """
        Initialize A/B testing framework.

        Args:
            saptiva_percentage: Percentage of users to assign to Saptiva (0-100)
            enabled: Enable A/B testing (default: from env)
            redis_url: Redis connection URL (default: from env)
        """
        # Configuration
        self.enabled = (
            enabled
            if enabled is not None
            else os.getenv("AB_TEST_ENABLED", "false").lower() == "true"
        )

        self.saptiva_percentage = (
            saptiva_percentage
            if saptiva_percentage is not None
            else int(os.getenv("AB_TEST_SAPTIVA_PERCENTAGE", "0"))
        )

        self.cohort_ttl_days = int(os.getenv("AB_TEST_COHORT_TTL_DAYS", "30"))
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")

        # Redis client (lazy initialized)
        self._redis_client = None

        # Metrics tracking
        self._metrics_buffer = []

        if not self.enabled:
            logger.info("A/B testing disabled, all users will use control variant")
        else:
            logger.info(
                "A/B testing enabled",
                saptiva_percentage=self.saptiva_percentage,
                cohort_ttl_days=self.cohort_ttl_days,
            )

    async def _get_redis_client(self):
        """Get or create Redis client."""
        if self._redis_client is None:
            redis = _get_redis()
            if redis is None:
                logger.warning(
                    "Redis not available, A/B testing will use hash-based assignment"
                )
                return None

            try:
                self._redis_client = await redis.from_url(
                    self.redis_url, encoding="utf-8", decode_responses=True
                )
                await self._redis_client.ping()
                logger.info("Redis connection established for A/B testing")
            except Exception as exc:
                logger.error(
                    "Failed to connect to Redis for A/B testing",
                    error=str(exc),
                )
                self._redis_client = None

        return self._redis_client

    def _hash_user_to_percentage(self, user_id: str) -> int:
        """
        Hash user ID to a percentage (0-99).

        Uses consistent hashing to ensure same user always gets same cohort.

        Args:
            user_id: User identifier

        Returns:
            Integer from 0 to 99 (inclusive)
        """
        hash_bytes = hashlib.sha256(user_id.encode()).digest()
        hash_int = int.from_bytes(hash_bytes[:4], "big")
        return hash_int % 100

    def _assign_variant(self, user_id: str) -> Variant:
        """
        Assign user to variant based on configuration.

        Uses consistent hashing to ensure:
        - Same user always gets same variant
        - Percentage distribution matches configuration

        Args:
            user_id: User identifier

        Returns:
            Variant.CONTROL or Variant.TREATMENT
        """
        if not self.enabled or self.saptiva_percentage == 0:
            return Variant.CONTROL

        if self.saptiva_percentage == 100:
            return Variant.TREATMENT

        # Hash user to 0-99 range
        user_bucket = self._hash_user_to_percentage(user_id)

        # Assign to treatment if in rollout percentage
        if user_bucket < self.saptiva_percentage:
            return Variant.TREATMENT
        else:
            return Variant.CONTROL

    async def get_variant_for_user(self, user_id: str) -> Variant:
        """
        Get assigned variant for user.

        First checks Redis cache, then computes and caches if needed.

        Args:
            user_id: User identifier

        Returns:
            Assigned variant
        """
        if not self.enabled:
            return Variant.CONTROL

        # Try to get from Redis cache
        redis_client = await self._get_redis_client()
        if redis_client:
            cache_key = f"ab_test:cohort:{user_id}"
            try:
                cached_variant = await redis_client.get(cache_key)
                if cached_variant:
                    logger.debug(
                        "Retrieved cached cohort assignment",
                        user_id=user_id,
                        variant=cached_variant,
                    )
                    return Variant(cached_variant)
            except Exception as exc:
                logger.warning("Failed to retrieve cached cohort", error=str(exc))

        # Compute variant
        variant = self._assign_variant(user_id)

        # Cache in Redis
        if redis_client:
            cache_key = f"ab_test:cohort:{user_id}"
            ttl_seconds = self.cohort_ttl_days * 86400

            try:
                await redis_client.setex(cache_key, ttl_seconds, variant.value)
                logger.debug(
                    "Cached cohort assignment",
                    user_id=user_id,
                    variant=variant.value,
                    ttl_days=self.cohort_ttl_days,
                )
            except Exception as exc:
                logger.warning("Failed to cache cohort assignment", error=str(exc))

        logger.info(
            "Assigned user to cohort",
            user_id=user_id,
            variant=variant.value,
            rollout_percentage=self.saptiva_percentage,
        )

        return variant

    async def get_extractor_for_user(self, user_id: str):
        """
        Get appropriate extractor instance for user.

        Args:
            user_id: User identifier

        Returns:
            TextExtractor instance (ThirdPartyExtractor or SaptivaExtractor)
        """
        from .factory import clear_extractor_cache, get_text_extractor

        variant = await self.get_variant_for_user(user_id)

        # Set environment variable to control factory
        os.environ["EXTRACTOR_PROVIDER"] = variant.value
        clear_extractor_cache()

        extractor = get_text_extractor()

        logger.debug(
            "Retrieved extractor for user",
            user_id=user_id,
            variant=variant.value,
            extractor_type=type(extractor).__name__,
        )

        return extractor

    async def record_extraction(
        self,
        user_id: str,
        variant: str,
        media_type: str,
        latency_ms: float,
        success: bool,
        error: Optional[str] = None,
        file_size_kb: Optional[int] = None,
        text_length: Optional[int] = None,
        cache_hit: Optional[bool] = None,
    ):
        """
        Record extraction metrics for analysis.

        Args:
            user_id: User identifier
            variant: Variant used ("third_party" or "saptiva")
            media_type: Document type ("pdf" or "image")
            latency_ms: Extraction latency in milliseconds
            success: Whether extraction succeeded
            error: Error message if failed
            file_size_kb: Input file size in KB
            text_length: Extracted text length in characters
            cache_hit: Whether result came from cache
        """
        metrics = ExtractionMetrics(
            user_id=user_id,
            variant=variant,
            timestamp=datetime.utcnow().isoformat(),
            media_type=media_type,
            latency_ms=latency_ms,
            success=success,
            error=error,
            file_size_kb=file_size_kb,
            text_length=text_length,
            cache_hit=cache_hit,
        )

        # Buffer metrics (export in batches)
        self._metrics_buffer.append(metrics)

        # Log metrics
        logger.info(
            "Extraction metrics recorded",
            user_id=user_id,
            variant=variant,
            media_type=media_type,
            latency_ms=latency_ms,
            success=success,
            cache_hit=cache_hit,
        )

        # Flush buffer if large
        if len(self._metrics_buffer) >= 100:
            await self._flush_metrics()

    async def _flush_metrics(self):
        """
        Flush metrics buffer to storage/observability stack.

        In production, this would send metrics to:
        - Prometheus/Grafana for visualization
        - BigQuery/Snowflake for analysis
        - S3 for long-term storage
        """
        if not self._metrics_buffer:
            return

        logger.info(
            "Flushing A/B test metrics",
            metric_count=len(self._metrics_buffer),
        )

        # TODO: Send to observability stack
        # For now, just log summary
        control_metrics = [
            m for m in self._metrics_buffer if m.variant == "third_party"
        ]
        treatment_metrics = [m for m in self._metrics_buffer if m.variant == "saptiva"]

        if control_metrics:
            control_latency = sum(m.latency_ms for m in control_metrics) / len(
                control_metrics
            )
            control_success = sum(1 for m in control_metrics if m.success) / len(
                control_metrics
            )
            logger.info(
                "Control metrics",
                count=len(control_metrics),
                avg_latency_ms=control_latency,
                success_rate=control_success,
            )

        if treatment_metrics:
            treatment_latency = sum(m.latency_ms for m in treatment_metrics) / len(
                treatment_metrics
            )
            treatment_success = sum(1 for m in treatment_metrics if m.success) / len(
                treatment_metrics
            )
            logger.info(
                "Treatment metrics",
                count=len(treatment_metrics),
                avg_latency_ms=treatment_latency,
                success_rate=treatment_success,
            )

        # Clear buffer
        self._metrics_buffer.clear()

    async def get_experiment_status(self) -> dict:
        """
        Get current A/B test status and metrics.

        Returns:
            Dictionary with experiment configuration and metrics
        """
        redis_client = await self._get_redis_client()

        # Count users in each cohort
        control_count = 0
        treatment_count = 0

        if redis_client:
            try:
                keys = await redis_client.keys("ab_test:cohort:*")
                for key in keys:
                    variant = await redis_client.get(key)
                    if variant == "third_party":
                        control_count += 1
                    elif variant == "saptiva":
                        treatment_count += 1
            except Exception as exc:
                logger.warning("Failed to retrieve cohort counts", error=str(exc))

        return {
            "enabled": self.enabled,
            "saptiva_percentage": self.saptiva_percentage,
            "cohort_ttl_days": self.cohort_ttl_days,
            "users_in_control": control_count,
            "users_in_treatment": treatment_count,
            "metrics_buffered": len(self._metrics_buffer),
        }

    async def close(self):
        """Clean up resources."""
        # Flush remaining metrics
        await self._flush_metrics()

        # Close Redis connection
        if self._redis_client:
            await self._redis_client.close()
            self._redis_client = None


# Global A/B test instance
_global_ab_test: Optional[ABTestingFramework] = None


def get_ab_test_framework() -> ABTestingFramework:
    """
    Get global A/B testing framework instance (singleton).

    Returns:
        ABTestingFramework instance
    """
    global _global_ab_test

    if _global_ab_test is None:
        _global_ab_test = ABTestingFramework()

    return _global_ab_test


async def close_ab_test_framework():
    """Close global A/B testing framework."""
    global _global_ab_test

    if _global_ab_test is not None:
        await _global_ab_test.close()
        _global_ab_test = None
