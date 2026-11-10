"""
Health check endpoint.
"""

from fastapi import APIRouter
import structlog

from ..services.minio_client import get_minio_client
from ..services.redis_client import get_redis_client

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns status of all dependencies.
    """
    status = {
        "status": "healthy",
        "service": "file-manager",
        "version": "1.0.0",
        "dependencies": {},
    }

    # Check MinIO
    try:
        minio = get_minio_client()
        # MinIO 7.2.x API: bucket_exists() requires named parameter
        minio.client.bucket_exists(bucket_name=minio.bucket)
        status["dependencies"]["minio"] = "connected"
    except Exception as e:
        status["dependencies"]["minio"] = f"error: {str(e)}"
        status["status"] = "degraded"

    # Check Redis
    try:
        redis = get_redis_client()
        if redis:
            await redis.ping()
            status["dependencies"]["redis"] = "connected"
        else:
            status["dependencies"]["redis"] = "not configured"
    except Exception as e:
        status["dependencies"]["redis"] = f"error: {str(e)}"
        # Redis is optional, don't degrade status

    return status


@router.get("/ready")
async def readiness_check():
    """
    Readiness check for Kubernetes.

    Returns 200 only if all critical dependencies are available.
    """
    try:
        minio = get_minio_client()
        # MinIO 7.2.x API: bucket_exists() requires named parameter
        minio.client.bucket_exists(bucket_name=minio.bucket)
        return {"ready": True}
    except Exception:
        return {"ready": False}


@router.get("/live")
async def liveness_check():
    """
    Liveness check for Kubernetes.

    Always returns 200 if the service is running.
    """
    return {"alive": True}
