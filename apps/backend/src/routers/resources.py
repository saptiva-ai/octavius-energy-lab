"""
Resource Monitoring API - Endpoints para monitorear y gestionar recursos

Endpoints:
- GET /api/resources/metrics - Métricas de uso de recursos
- POST /api/resources/cleanup - Trigger manual de limpieza
- GET /api/resources/queue - Estado de la cola de limpieza
"""

from typing import Any, Dict, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..core.auth import get_current_user
from ..models.user import User
from ..services.resource_lifecycle_manager import (
    ResourceType,
    get_resource_manager,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/resources", tags=["resources"])


class ResourceMetricsResponse(BaseModel):
    """Response model para métricas de recursos."""

    redis: Dict[str, Any]
    weaviate: Dict[str, Any]
    minio: Dict[str, Any]
    mongodb: Dict[str, Any]


class CleanupRequest(BaseModel):
    """Request model para limpieza manual."""

    resource_type: Optional[str] = None  # None = all resources


class CleanupResponse(BaseModel):
    """Response model para limpieza."""

    success: bool
    deleted_counts: Dict[str, int]
    message: str


class CleanupQueueResponse(BaseModel):
    """Response model para estado de cola."""

    queue_size: int
    tasks: list[Dict[str, Any]]


@router.get("/metrics", response_model=ResourceMetricsResponse)
async def get_resource_metrics(current_user: User = Depends(get_current_user)):
    """
    Obtiene métricas de uso de todos los recursos.

    Retorna información sobre:
    - Redis: memoria usada, número de keys
    - Weaviate: número de vectores, tamaño estimado
    - MinIO: número de archivos, tamaño total
    - MongoDB: número de documentos, tamaño metadata

    Requiere autenticación.
    """
    try:
        manager = get_resource_manager()

        # Obtener métricas de todos los recursos
        redis_metrics = await manager.get_resource_metrics(ResourceType.REDIS_CACHE)
        weaviate_metrics = await manager.get_resource_metrics(
            ResourceType.WEAVIATE_VECTORS
        )
        minio_metrics = await manager.get_resource_metrics(ResourceType.MINIO_FILES)
        mongodb_metrics = await manager.get_resource_metrics(
            ResourceType.MONGODB_METADATA
        )

        logger.info(
            "Resource metrics retrieved",
            user_id=str(current_user.id),
            redis_usage=f"{redis_metrics.usage_percentage:.1%}",
            weaviate_usage=f"{weaviate_metrics.usage_percentage:.1%}",
            minio_usage=f"{minio_metrics.usage_percentage:.1%}",
        )

        return ResourceMetricsResponse(
            redis={
                "total_items": redis_metrics.total_items,
                "size_mb": redis_metrics.total_size_bytes / (1024 * 1024),
                "usage_percentage": redis_metrics.usage_percentage * 100,
                "cleanup_priority": redis_metrics.cleanup_priority.name,
                "oldest_age_hours": redis_metrics.oldest_item_age_hours,
            },
            weaviate={
                "total_items": weaviate_metrics.total_items,
                "size_mb": weaviate_metrics.total_size_bytes / (1024 * 1024),
                "usage_percentage": weaviate_metrics.usage_percentage * 100,
                "cleanup_priority": weaviate_metrics.cleanup_priority.name,
                "oldest_age_hours": weaviate_metrics.oldest_item_age_hours,
            },
            minio={
                "total_items": minio_metrics.total_items,
                "size_mb": minio_metrics.total_size_bytes / (1024 * 1024),
                "usage_percentage": minio_metrics.usage_percentage * 100,
                "cleanup_priority": minio_metrics.cleanup_priority.name,
                "oldest_age_hours": minio_metrics.oldest_item_age_hours,
            },
            mongodb={
                "total_items": mongodb_metrics.total_items,
                "size_mb": mongodb_metrics.total_size_bytes / (1024 * 1024),
                "usage_percentage": mongodb_metrics.usage_percentage * 100,
                "cleanup_priority": mongodb_metrics.cleanup_priority.name,
                "oldest_age_hours": mongodb_metrics.oldest_item_age_hours,
            },
        )

    except Exception as e:
        logger.error(
            "Failed to get resource metrics",
            error=str(e),
            user_id=str(current_user.id),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve resource metrics",
        )


@router.post("/cleanup", response_model=CleanupResponse)
async def trigger_cleanup(
    request: CleanupRequest, current_user: User = Depends(get_current_user)
):
    """
    Trigger manual de limpieza de recursos.

    Args:
        resource_type: Tipo de recurso a limpiar (opcional)
            - "redis_cache": Limpia Redis cache
            - "weaviate_vectors": Limpia Weaviate vectors
            - "minio_files": Limpia MinIO files
            - None: Limpia todos los recursos

    Requiere autenticación.
    """
    try:
        manager = get_resource_manager()

        # Parse resource type si fue proporcionado
        resource_type_enum = None
        if request.resource_type:
            try:
                resource_type_enum = ResourceType(request.resource_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid resource type: {request.resource_type}",
                )

        logger.info(
            "Manual cleanup triggered",
            user_id=str(current_user.id),
            resource_type=request.resource_type or "all",
        )

        # Ejecutar limpieza
        deleted_counts = await manager.cleanup_expired_resources(resource_type_enum)

        total_deleted = sum(deleted_counts.values())

        logger.info(
            "Manual cleanup completed",
            user_id=str(current_user.id),
            deleted_counts=deleted_counts,
            total_deleted=total_deleted,
        )

        return CleanupResponse(
            success=True,
            deleted_counts=deleted_counts,
            message=f"Cleanup completed. Total items deleted: {total_deleted}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Cleanup failed", error=str(e), user_id=str(current_user.id), exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cleanup operation failed",
        )


@router.get("/queue", response_model=CleanupQueueResponse)
async def get_cleanup_queue(current_user: User = Depends(get_current_user)):
    """
    Obtiene el estado actual de la cola de limpieza.

    Retorna:
    - Tamaño de la cola
    - Lista de tareas pendientes con prioridad

    Requiere autenticación.
    """
    try:
        manager = get_resource_manager()

        queue_tasks = [
            {
                "priority": task.priority.name,
                "resource_type": task.resource_type.value,
                "target_id": task.target_id,
                "created_at": task.created_at.isoformat(),
                "reason": task.reason,
            }
            for task in manager.cleanup_queue
        ]

        logger.info(
            "Cleanup queue status retrieved",
            user_id=str(current_user.id),
            queue_size=len(queue_tasks),
        )

        return CleanupQueueResponse(queue_size=len(queue_tasks), tasks=queue_tasks)

    except Exception as e:
        logger.error(
            "Failed to get cleanup queue",
            error=str(e),
            user_id=str(current_user.id),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve cleanup queue",
        )
