"""
Health check endpoints.
"""

import time
from datetime import datetime
from typing import Any, Dict

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..core.config import Settings, get_settings
from ..core.database import Database

logger = structlog.get_logger(__name__)
router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    timestamp: datetime
    version: str
    uptime_seconds: float
    checks: Dict[str, Any]


class DatabaseCheck(BaseModel):
    """Database health check model."""

    status: str
    latency_ms: float
    connected: bool
    error: str = ""


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """
    Comprehensive health check endpoint.

    Checks:
    - API availability
    - Database connectivity
    - External service connectivity (future)
    """

    start_time = time.time()
    checks = {}
    overall_status = "healthy"

    # Check database connectivity
    try:
        db_start = time.time()
        await Database.ping()
        db_latency = (time.time() - db_start) * 1000

        checks["database"] = DatabaseCheck(
            status="healthy", latency_ms=round(db_latency, 2), connected=True
        ).model_dump()

        logger.info("Database health check passed", latency_ms=db_latency)

    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        checks["database"] = DatabaseCheck(
            status="unhealthy", latency_ms=0.0, connected=False, error=str(e)
        ).model_dump()
        overall_status = "degraded"

    # Future: Add health checks for:
    # - Redis connection and ping test
    # - Aletheia orchestrator availability
    # - MinIO/S3 storage connectivity
    # - Message queue (if implemented)

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        version=settings.app_version,
        uptime_seconds=round(time.time() - start_time, 3),
        checks=checks,
    )


@router.get("/health/live", tags=["health"])
async def liveness_probe() -> Dict[str, str]:
    """
    Kubernetes liveness probe endpoint.
    Simple endpoint that returns 200 if the service is running.
    """
    return {"status": "alive"}


@router.get("/health/ready", tags=["health"])
async def readiness_probe() -> Dict[str, str]:
    """
    Kubernetes readiness probe endpoint.
    Returns 200 if the service is ready to accept traffic.
    """
    try:
        # Quick database connectivity check
        await Database.ping()
        return {"status": "ready"}
    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service not ready"
        )


class FeatureFlagsResponse(BaseModel):
    """Feature flags response model."""

    deep_research_kill_switch: bool  # P0-DR-KILL-001: Global kill switch
    deep_research_enabled: bool
    deep_research_auto: bool
    deep_research_complexity_threshold: float
    create_chat_optimistic: bool = True


@router.get("/feature-flags", response_model=FeatureFlagsResponse, tags=["health"])
async def get_feature_flags(
    settings: Settings = Depends(get_settings),
) -> FeatureFlagsResponse:
    """
    Get current feature flags configuration (P0-DR-KILL-001, P0-DR-002).

    Returns the state of Deep Research feature flags so the frontend
    can adjust its UI accordingly. The kill switch dominates all other flags.
    """
    return FeatureFlagsResponse(
        deep_research_kill_switch=settings.deep_research_kill_switch,
        deep_research_enabled=settings.deep_research_enabled,
        deep_research_auto=settings.deep_research_auto,
        deep_research_complexity_threshold=settings.deep_research_complexity_threshold,
        create_chat_optimistic=settings.create_chat_optimistic,
    )
