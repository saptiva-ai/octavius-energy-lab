"""
Resource Lifecycle Manager - Gestión del ciclo de vida de recursos RAG

Responsabilidades:
1. Deduplicación de archivos (hash-based)
2. Limpieza automática de recursos obsoletos (Redis, Weaviate, MinIO)
3. Monitoreo de uso de memoria y storage
4. Políticas de retención configurables
5. Cola de prioridad para limpieza (LRU - Least Recently Used)

Arquitectura:
- Redis: Cache temporal de chunks (TTL corto)
- Weaviate: Vectores indexados (TTL medio)
- MinIO: Archivos originales (TTL largo)
- MongoDB: Metadatos (permanente con cleanup manual)

Estrategia de Limpieza:
1. Prioridad 1: Redis cache expired (cada 1 hora)
2. Prioridad 2: Weaviate old sessions (cada 6 horas)
3. Prioridad 3: MinIO unused files (cada 24 horas)
4. Prioridad 4: MongoDB orphaned documents (manual)
"""

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

import structlog
from beanie import PydanticObjectId

logger = structlog.get_logger(__name__)


class ResourceType(str, Enum):
    """Tipos de recursos gestionados."""

    REDIS_CACHE = "redis_cache"
    WEAVIATE_VECTORS = "weaviate_vectors"
    MINIO_FILES = "minio_files"
    MONGODB_METADATA = "mongodb_metadata"


class CleanupPriority(int, Enum):
    """Prioridad de limpieza (menor = más urgente)."""

    CRITICAL = 1  # > 90% uso
    HIGH = 2  # > 75% uso
    MEDIUM = 3  # > 50% uso
    LOW = 4  # < 50% uso


@dataclass
class ResourceMetrics:
    """Métricas de uso de recursos."""

    resource_type: ResourceType
    total_items: int
    total_size_bytes: int
    oldest_item_age_hours: float
    usage_percentage: float
    cleanup_priority: CleanupPriority


@dataclass
class CleanupTask:
    """Tarea de limpieza en cola."""

    priority: CleanupPriority
    resource_type: ResourceType
    target_id: str
    created_at: datetime
    reason: str


class ResourceLifecycleManager:
    """
    Gestor del ciclo de vida de recursos RAG.

    Implementa:
    - Deduplicación basada en hash SHA256
    - Limpieza automática con políticas LRU
    - Monitoreo de uso de recursos
    - Cola de prioridad para cleanup
    """

    def __init__(self):
        """Inicializar gestor de ciclo de vida."""
        # Configuración desde ENV
        self.redis_ttl_hours = int(os.getenv("REDIS_CACHE_TTL_HOURS", "1"))
        self.weaviate_ttl_hours = int(os.getenv("RAG_SESSION_TTL_HOURS", "24"))
        self.minio_ttl_days = int(os.getenv("FILES_TTL_DAYS", "7"))

        # Umbrales de limpieza (porcentaje de uso)
        self.cleanup_threshold_critical = float(
            os.getenv("CLEANUP_THRESHOLD_CRITICAL", "0.9")
        )
        self.cleanup_threshold_high = float(os.getenv("CLEANUP_THRESHOLD_HIGH", "0.75"))
        self.cleanup_threshold_medium = float(
            os.getenv("CLEANUP_THRESHOLD_MEDIUM", "0.5")
        )

        # Límites de memoria
        self.max_redis_memory_mb = int(os.getenv("MAX_REDIS_MEMORY_MB", "256"))
        self.max_weaviate_points = int(os.getenv("MAX_WEAVIATE_POINTS", "100000"))
        self.max_minio_storage_gb = int(os.getenv("MAX_MINIO_STORAGE_GB", "50"))

        # Cola de tareas de limpieza
        self.cleanup_queue: List[CleanupTask] = []

        logger.info(
            "ResourceLifecycleManager initialized",
            redis_ttl_hours=self.redis_ttl_hours,
            weaviate_ttl_hours=self.weaviate_ttl_hours,
            minio_ttl_days=self.minio_ttl_days,
            cleanup_thresholds={
                "critical": self.cleanup_threshold_critical,
                "high": self.cleanup_threshold_high,
                "medium": self.cleanup_threshold_medium,
            },
        )

    async def compute_file_hash(self, file_content: bytes) -> str:
        """
        Calcula SHA256 hash para deduplicación.

        Args:
            file_content: Contenido del archivo en bytes

        Returns:
            Hash SHA256 como string hexadecimal
        """
        return hashlib.sha256(file_content).hexdigest()

    async def check_duplicate_file(
        self, file_hash: str, user_id: str
    ) -> Optional[PydanticObjectId]:
        """
        Verifica si existe un archivo duplicado.

        Args:
            file_hash: SHA256 hash del archivo
            user_id: ID del usuario (para scope de deduplicación)

        Returns:
            Document ID si existe duplicado, None si no
        """
        from ..models.document import Document

        # Buscar documento con mismo hash del mismo usuario
        existing_doc = await Document.find_one(
            {"metadata.file_hash": file_hash, "user_id": user_id}
        )

        if existing_doc:
            logger.info(
                "Duplicate file detected",
                file_hash=file_hash[:16],
                existing_doc_id=str(existing_doc.id),
                user_id=user_id,
            )
            return existing_doc.id

        return None

    async def get_resource_metrics(
        self, resource_type: ResourceType
    ) -> ResourceMetrics:
        """
        Obtiene métricas de uso de un recurso.

        Args:
            resource_type: Tipo de recurso a analizar

        Returns:
            Métricas del recurso
        """
        if resource_type == ResourceType.REDIS_CACHE:
            return await self._get_redis_metrics()
        elif resource_type == ResourceType.WEAVIATE_VECTORS:
            return await self._get_weaviate_metrics()
        elif resource_type == ResourceType.MINIO_FILES:
            return await self._get_minio_metrics()
        elif resource_type == ResourceType.MONGODB_METADATA:
            return await self._get_mongodb_metrics()

        raise ValueError(f"Unknown resource type: {resource_type}")

    async def _get_redis_metrics(self) -> ResourceMetrics:
        """Métricas de Redis cache."""
        from ..core.redis_cache import get_redis_cache

        cache = await get_redis_cache()

        # Obtener info de Redis
        info = await cache.client.info("memory")
        used_memory_mb = info.get("used_memory", 0) / (1024 * 1024)
        usage_percentage = used_memory_mb / self.max_redis_memory_mb

        # Contar keys
        total_keys = await cache.client.dbsize()

        # Determinar prioridad
        if usage_percentage >= self.cleanup_threshold_critical:
            priority = CleanupPriority.CRITICAL
        elif usage_percentage >= self.cleanup_threshold_high:
            priority = CleanupPriority.HIGH
        elif usage_percentage >= self.cleanup_threshold_medium:
            priority = CleanupPriority.MEDIUM
        else:
            priority = CleanupPriority.LOW

        return ResourceMetrics(
            resource_type=ResourceType.REDIS_CACHE,
            total_items=total_keys,
            total_size_bytes=int(used_memory_mb * 1024 * 1024),
            oldest_item_age_hours=0,  # Redis TTL automático
            usage_percentage=usage_percentage,
            cleanup_priority=priority,
        )

    async def _get_weaviate_metrics(self) -> ResourceMetrics:
        """Métricas de Weaviate vectors."""
        from ..services.weaviate_service import get_weaviate_service

        weaviate = get_weaviate_service()

        # Obtener info de salud (incluye count)
        health = weaviate.health_check()
        total_points = health.get("points_count", 0)

        usage_percentage = total_points / self.max_weaviate_points

        # Determinar prioridad
        if usage_percentage >= self.cleanup_threshold_critical:
            priority = CleanupPriority.CRITICAL
        elif usage_percentage >= self.cleanup_threshold_high:
            priority = CleanupPriority.HIGH
        elif usage_percentage >= self.cleanup_threshold_medium:
            priority = CleanupPriority.MEDIUM
        else:
            priority = CleanupPriority.LOW

        # Estimar edad del punto más antiguo (basado en TTL)
        oldest_age_hours = self.weaviate_ttl_hours

        return ResourceMetrics(
            resource_type=ResourceType.WEAVIATE_VECTORS,
            total_items=total_points,
            total_size_bytes=total_points * 384 * 4,  # 384-dim * 4 bytes/float
            oldest_item_age_hours=oldest_age_hours,
            usage_percentage=usage_percentage,
            cleanup_priority=priority,
        )

    async def _get_minio_metrics(self) -> ResourceMetrics:
        """Métricas de MinIO storage."""
        from ..models.document import Document

        # Contar archivos en MinIO via MongoDB metadata
        total_docs = await Document.count()

        # Estimar tamaño total (promedio 2MB por archivo)
        avg_file_size_bytes = 2 * 1024 * 1024
        total_size_bytes = total_docs * avg_file_size_bytes
        total_size_gb = total_size_bytes / (1024**3)

        usage_percentage = total_size_gb / self.max_minio_storage_gb

        # Determinar prioridad
        if usage_percentage >= self.cleanup_threshold_critical:
            priority = CleanupPriority.CRITICAL
        elif usage_percentage >= self.cleanup_threshold_high:
            priority = CleanupPriority.HIGH
        elif usage_percentage >= self.cleanup_threshold_medium:
            priority = CleanupPriority.MEDIUM
        else:
            priority = CleanupPriority.LOW

        # Edad del archivo más antiguo
        oldest_doc = await Document.find().sort("-created_at").limit(1).to_list()
        if oldest_doc:
            oldest_age = datetime.utcnow() - oldest_doc[0].created_at
            oldest_age_hours = oldest_age.total_seconds() / 3600
        else:
            oldest_age_hours = 0

        return ResourceMetrics(
            resource_type=ResourceType.MINIO_FILES,
            total_items=total_docs,
            total_size_bytes=total_size_bytes,
            oldest_item_age_hours=oldest_age_hours,
            usage_percentage=usage_percentage,
            cleanup_priority=priority,
        )

    async def _get_mongodb_metrics(self) -> ResourceMetrics:
        """Métricas de MongoDB metadata."""
        from ..models.document import Document

        total_docs = await Document.count()

        # Estimar tamaño de metadata (promedio 5KB por documento)
        avg_metadata_size = 5 * 1024
        total_size_bytes = total_docs * avg_metadata_size

        # MongoDB no tiene límite hard-coded, usar threshold relativo
        usage_percentage = min(total_docs / 10000, 1.0)  # Cap at 10k docs

        return ResourceMetrics(
            resource_type=ResourceType.MONGODB_METADATA,
            total_items=total_docs,
            total_size_bytes=total_size_bytes,
            oldest_item_age_hours=0,
            usage_percentage=usage_percentage,
            cleanup_priority=CleanupPriority.LOW,  # Manual cleanup
        )

    async def cleanup_expired_resources(
        self, resource_type: Optional[ResourceType] = None
    ) -> Dict[str, int]:
        """
        Limpia recursos expirados.

        Args:
            resource_type: Tipo específico a limpiar, o None para todos

        Returns:
            Dict con contadores de items eliminados por tipo
        """
        results = {}

        if resource_type is None or resource_type == ResourceType.REDIS_CACHE:
            results["redis"] = await self._cleanup_redis_cache()

        if resource_type is None or resource_type == ResourceType.WEAVIATE_VECTORS:
            results["weaviate"] = await self._cleanup_weaviate_vectors()

        if resource_type is None or resource_type == ResourceType.MINIO_FILES:
            results["minio"] = await self._cleanup_minio_files()

        logger.info("Cleanup completed", results=results, resource_type=resource_type)

        return results

    async def _cleanup_redis_cache(self) -> int:
        """
        Limpia cache de Redis expirado.

        Returns:
            Número de keys eliminadas
        """
        from ..core.redis_cache import get_redis_cache

        cache = await get_redis_cache()

        # Redis TTL automático se encarga de la limpieza
        # Aquí solo forzamos limpieza de keys sin TTL

        # Buscar keys sin TTL (potencialmente olvidadas)
        cursor = 0
        deleted_count = 0

        while True:
            cursor, keys = await cache.client.scan(
                cursor=cursor, match="doc_segments:*", count=100
            )

            for key in keys:
                ttl = await cache.client.ttl(key)
                if ttl == -1:  # No TTL set
                    await cache.client.delete(key)
                    deleted_count += 1
                    logger.warning(
                        "Deleted Redis key without TTL",
                        key=key.decode() if isinstance(key, bytes) else key,
                    )

            if cursor == 0:
                break

        logger.info("Redis cache cleanup completed", deleted_count=deleted_count)
        return deleted_count

    async def _cleanup_weaviate_vectors(self) -> int:
        """
        Limpia vectores de Weaviate expirados.

        Returns:
            Número de puntos eliminados
        """
        from ..services.weaviate_service import get_weaviate_service

        weaviate = get_weaviate_service()

        # Calcular timestamp de corte (TTL hours ago)
        cutoff_time = datetime.utcnow() - timedelta(hours=self.weaviate_ttl_hours)

        # Eliminar puntos antiguos
        deleted_count = weaviate.cleanup_expired_sessions(
            ttl_hours=self.weaviate_ttl_hours
        )

        logger.info(
            "Weaviate vectors cleanup completed",
            deleted_count=deleted_count,
            cutoff_time=cutoff_time.isoformat(),
        )

        return deleted_count

    async def _cleanup_minio_files(self) -> int:
        """
        Limpia archivos de MinIO no utilizados.

        Returns:
            Número de archivos eliminados
        """
        from ..models.document import Document, DocumentStatus
        from .file_storage import get_file_storage

        storage = get_file_storage()

        # Buscar documentos antiguos sin referencias activas
        cutoff_time = datetime.utcnow() - timedelta(days=self.minio_ttl_days)

        old_docs = await Document.find(
            {
                "created_at": {"$lt": cutoff_time},
                "status": {"$in": [DocumentStatus.READY, DocumentStatus.FAILED]},
            }
        ).to_list()

        deleted_count = 0

        for doc in old_docs:
            try:
                # Verificar si está en alguna sesión activa
                from ..models.chat import ChatSession

                active_sessions = await ChatSession.find(
                    {
                        "attached_file_ids": str(doc.id),
                        "updated_at": {"$gte": cutoff_time},
                    }
                ).count()

                if active_sessions == 0:
                    # No hay sesiones activas, seguro eliminar
                    if doc.minio_path:
                        await storage.delete_file(doc.minio_path)

                    await doc.delete()
                    deleted_count += 1

                    logger.info(
                        "Deleted unused MinIO file",
                        doc_id=str(doc.id),
                        filename=doc.filename,
                        age_days=(datetime.utcnow() - doc.created_at).days,
                    )
            except Exception as e:
                logger.error(
                    "Failed to delete MinIO file",
                    doc_id=str(doc.id),
                    error=str(e),
                    exc_info=True,
                )

        logger.info("MinIO files cleanup completed", deleted_count=deleted_count)
        return deleted_count

    async def schedule_cleanup_task(
        self,
        resource_type: ResourceType,
        target_id: str,
        priority: CleanupPriority,
        reason: str,
    ):
        """
        Agrega tarea de limpieza a la cola.

        Args:
            resource_type: Tipo de recurso
            target_id: ID del recurso a limpiar
            priority: Prioridad de limpieza
            reason: Razón de la limpieza
        """
        task = CleanupTask(
            priority=priority,
            resource_type=resource_type,
            target_id=target_id,
            created_at=datetime.utcnow(),
            reason=reason,
        )

        self.cleanup_queue.append(task)

        # Ordenar por prioridad (menor primero)
        self.cleanup_queue.sort(key=lambda t: t.priority.value)

        logger.info(
            "Cleanup task scheduled",
            resource_type=resource_type,
            priority=priority,
            reason=reason,
            queue_size=len(self.cleanup_queue),
        )

    async def process_cleanup_queue(self, max_tasks: int = 10):
        """
        Procesa tareas de limpieza en cola.

        Args:
            max_tasks: Máximo número de tareas a procesar
        """
        processed = 0

        while self.cleanup_queue and processed < max_tasks:
            task = self.cleanup_queue.pop(0)

            try:
                await self.cleanup_expired_resources(resource_type=task.resource_type)
                processed += 1

                logger.info(
                    "Cleanup task processed",
                    resource_type=task.resource_type,
                    priority=task.priority,
                    reason=task.reason,
                )
            except Exception as e:
                logger.error(
                    "Cleanup task failed",
                    resource_type=task.resource_type,
                    error=str(e),
                    exc_info=True,
                )

        logger.info(
            "Cleanup queue processed",
            processed=processed,
            remaining=len(self.cleanup_queue),
        )


# Singleton instance
_resource_manager: Optional[ResourceLifecycleManager] = None


def get_resource_manager() -> ResourceLifecycleManager:
    """
    Obtiene instancia singleton del gestor de recursos.

    Returns:
        ResourceLifecycleManager instance
    """
    global _resource_manager

    if _resource_manager is None:
        _resource_manager = ResourceLifecycleManager()

    return _resource_manager
