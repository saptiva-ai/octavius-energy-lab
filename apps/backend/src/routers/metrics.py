"""
Advanced metrics and monitoring API endpoints.

Provides comprehensive observability for Copilotos Bridge including:
- Prometheus metrics for requests, errors, and performance
- Deep Research specific metrics
- System health and status
"""

import structlog
from fastapi import APIRouter, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST

from ..core.telemetry import get_metrics, metrics_collector, telemetry

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/metrics", tags=["monitoring"])
async def get_prometheus_metrics():
    """
    Expose comprehensive Prometheus metrics endpoint.

    Returns metrics in Prometheus format for scraping, including:
    - HTTP request metrics (count, duration, status codes)
    - Deep Research operation metrics
    - Intent classification metrics
    - External API call metrics
    - Cache performance metrics
    - Active connections and sessions
    - Error tracking metrics
    """
    try:
        # Generate comprehensive Prometheus metrics
        metrics_data = get_metrics()

        return Response(
            content=metrics_data,
            media_type=CONTENT_TYPE_LATEST,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    except Exception as e:
        logger.error("Failed to generate metrics", error=str(e))
        return Response(
            content="# Error generating metrics\n",
            media_type=CONTENT_TYPE_LATEST,
            status_code=500,
        )


@router.get("/health/metrics", tags=["monitoring", "health"])
async def get_metrics_health():
    """
    Health check for advanced metrics collection.

    Returns detailed status about the metrics system including:
    - Basic health status
    - Request and error counts
    - Active connections
    - Telemetry component status
    """
    try:
        request_count = metrics_collector.get_request_count()
        error_count = metrics_collector.get_error_count()
        active_connections = metrics_collector.get_active_connections()

        return {
            "status": "healthy",
            "metrics_collector": "active",
            "telemetry_enabled": True,
            "statistics": {
                "total_requests": request_count,
                "total_errors": error_count,
                "active_connections": active_connections,
                "error_rate": (error_count / max(request_count, 1)) * 100,
            },
            "exporters": {
                "prometheus": True,
                "custom_registry": True,
                "console": False,
            },
            "features": {
                "request_tracking": True,
                "error_tracking": True,
                "research_metrics": True,
                "intent_classification_metrics": True,
                "external_api_metrics": True,
                "cache_metrics": True,
            },
        }
    except Exception as e:
        logger.error("Metrics health check failed", error=str(e))
        return {"status": "unhealthy", "error": str(e), "metrics_collector": "error"}


@router.get("/metrics/summary", tags=["monitoring"])
async def get_metrics_summary():
    """
    Get a human-readable summary of key metrics.

    Returns summarized metrics for monitoring dashboards.
    """
    try:
        request_count = metrics_collector.get_request_count()
        error_count = metrics_collector.get_error_count()
        active_connections = metrics_collector.get_active_connections()

        error_rate = (error_count / max(request_count, 1)) * 100

        return {
            "system": {
                "status": (
                    "healthy"
                    if error_rate < 5
                    else "degraded"
                    if error_rate < 10
                    else "unhealthy"
                ),
                "uptime": "available",  # Could be enhanced with actual uptime tracking
                "version": "1.0.0",
            },
            "performance": {
                "total_requests": request_count,
                "error_count": error_count,
                "error_rate_percent": round(error_rate, 2),
                "active_connections": active_connections,
            },
            "features": {
                "deep_research": "enabled",
                "intent_classification": "enabled",
                "external_apis": "enabled",
                "caching": "enabled",
            },
        }
    except Exception as e:
        logger.error("Failed to generate metrics summary", error=str(e))
        raise HTTPException(
            status_code=500, detail="Failed to generate metrics summary"
        )


@router.post("/metrics/research/quality", tags=["monitoring", "research"])
async def update_research_quality_metric(research_type: str, quality_score: float):
    """
    Update research quality metrics.

    Allows the system to report quality scores for different types of research operations.
    """
    try:
        if not 0 <= quality_score <= 1:
            raise HTTPException(
                status_code=400, detail="Quality score must be between 0 and 1"
            )

        telemetry.update_research_quality(research_type, quality_score)

        logger.info(
            "Research quality metric updated",
            research_type=research_type,
            quality_score=quality_score,
        )

        return {
            "status": "success",
            "research_type": research_type,
            "quality_score": quality_score,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update research quality metric", error=str(e))
        raise HTTPException(
            status_code=500, detail="Failed to update research quality metric"
        )


@router.get("/metrics/research", tags=["monitoring", "research"])
async def get_research_metrics():
    """
    Get Deep Research specific metrics.

    Returns metrics related to Deep Research operations and performance.
    """
    try:
        # This would typically pull from the Prometheus metrics
        # For now, return a structure showing available research metrics
        return {
            "available_metrics": {
                "research_requests_total": "Counter of total research requests by intent type and classification method",
                "research_duration_seconds": "Histogram of research operation durations by phase and success status",
                "research_quality_score": "Gauge of research quality scores by research type",
                "intent_classification_total": "Counter of intent classifications by type, confidence level, and method",
            },
            "endpoints": {
                "update_quality": "/api/metrics/research/quality",
                "main_metrics": "/api/metrics",
            },
        }
    except Exception as e:
        logger.error("Failed to get research metrics", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get research metrics")
