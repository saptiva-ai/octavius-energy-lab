"""
Background Worker para Limpieza de Recursos

Ejecuta tareas de limpieza periódicas:
1. Redis cache expired - cada 1 hora
2. Weaviate old sessions - cada 6 horas
3. MinIO unused files - cada 24 horas
4. Monitoreo de recursos - cada 30 minutos

Arquitectura:
- asyncio tasks concurrentes
- Graceful shutdown handling
- Error recovery y retry logic
- Métricas de limpieza para observability
"""

import asyncio
import os
import signal
from contextlib import asynccontextmanager
from typing import Optional

import structlog

from ..services.resource_lifecycle_manager import (
    CleanupPriority,
    ResourceType,
    get_resource_manager,
)

logger = structlog.get_logger(__name__)


class ResourceCleanupWorker:
    """
    Worker background para limpieza automática de recursos.

    Ejecuta múltiples tareas concurrentes con diferentes intervalos.
    """

    def __init__(self):
        """Inicializar worker."""
        self.manager = get_resource_manager()
        self.running = False
        self.tasks: list[asyncio.Task] = []

        # Configuración de intervalos (en segundos)
        self.redis_cleanup_interval = int(
            os.getenv("REDIS_CLEANUP_INTERVAL_SECONDS", "3600")
        )  # 1 hora
        self.weaviate_cleanup_interval = int(
            os.getenv("RAG_CLEANUP_INTERVAL_SECONDS", "21600")
        )  # 6 horas
        self.minio_cleanup_interval = int(
            os.getenv("MINIO_CLEANUP_INTERVAL_SECONDS", "86400")
        )  # 24 horas
        self.monitoring_interval = int(
            os.getenv("RESOURCE_MONITORING_INTERVAL_SECONDS", "1800")
        )  # 30 min

        logger.info(
            "ResourceCleanupWorker initialized",
            intervals={
                "redis_cleanup": f"{self.redis_cleanup_interval}s",
                "weaviate_cleanup": f"{self.weaviate_cleanup_interval}s",
                "minio_cleanup": f"{self.minio_cleanup_interval}s",
                "monitoring": f"{self.monitoring_interval}s",
            },
        )

    async def start(self):
        """Inicia todas las tareas de limpieza."""
        if self.running:
            logger.warning("Worker already running")
            return

        self.running = True
        logger.info("Starting ResourceCleanupWorker...")

        # Crear tareas concurrentes
        self.tasks = [
            asyncio.create_task(self._redis_cleanup_loop(), name="redis_cleanup"),
            asyncio.create_task(self._weaviate_cleanup_loop(), name="weaviate_cleanup"),
            asyncio.create_task(self._minio_cleanup_loop(), name="minio_cleanup"),
            asyncio.create_task(self._monitoring_loop(), name="resource_monitoring"),
        ]

        logger.info("All cleanup tasks started", task_count=len(self.tasks))

    async def stop(self):
        """Detiene todas las tareas de limpieza gracefully."""
        if not self.running:
            return

        logger.info("Stopping ResourceCleanupWorker...")
        self.running = False

        # Cancelar todas las tareas
        for task in self.tasks:
            task.cancel()

        # Esperar a que terminen
        await asyncio.gather(*self.tasks, return_exceptions=True)

        logger.info("ResourceCleanupWorker stopped")

    async def _redis_cleanup_loop(self):
        """Loop de limpieza de Redis cache."""
        logger.info(
            "Redis cleanup loop started", interval_seconds=self.redis_cleanup_interval
        )

        while self.running:
            try:
                await asyncio.sleep(self.redis_cleanup_interval)

                logger.info("Running Redis cache cleanup...")
                deleted = await self.manager.cleanup_expired_resources(
                    ResourceType.REDIS_CACHE
                )

                logger.info(
                    "Redis cleanup completed", deleted_count=deleted.get("redis", 0)
                )

            except asyncio.CancelledError:
                logger.info("Redis cleanup loop cancelled")
                break
            except Exception as e:
                logger.error("Redis cleanup failed", error=str(e), exc_info=True)
                # Retry después de 1 minuto en caso de error
                await asyncio.sleep(60)

    async def _weaviate_cleanup_loop(self):
        """Loop de limpieza de Weaviate vectors."""
        logger.info(
            "Weaviate cleanup loop started",
            interval_seconds=self.weaviate_cleanup_interval,
        )

        while self.running:
            try:
                await asyncio.sleep(self.weaviate_cleanup_interval)

                logger.info("Running Weaviate vectors cleanup...")
                deleted = await self.manager.cleanup_expired_resources(
                    ResourceType.WEAVIATE_VECTORS
                )

                logger.info(
                    "Weaviate cleanup completed",
                    deleted_count=deleted.get("weaviate", 0),
                )

            except asyncio.CancelledError:
                logger.info("Weaviate cleanup loop cancelled")
                break
            except Exception as e:
                logger.error("Weaviate cleanup failed", error=str(e), exc_info=True)
                # Retry después de 5 minutos
                await asyncio.sleep(300)

    async def _minio_cleanup_loop(self):
        """Loop de limpieza de MinIO files."""
        logger.info(
            "MinIO cleanup loop started", interval_seconds=self.minio_cleanup_interval
        )

        while self.running:
            try:
                await asyncio.sleep(self.minio_cleanup_interval)

                logger.info("Running MinIO files cleanup...")
                deleted = await self.manager.cleanup_expired_resources(
                    ResourceType.MINIO_FILES
                )

                logger.info(
                    "MinIO cleanup completed", deleted_count=deleted.get("minio", 0)
                )

            except asyncio.CancelledError:
                logger.info("MinIO cleanup loop cancelled")
                break
            except Exception as e:
                logger.error("MinIO cleanup failed", error=str(e), exc_info=True)
                # Retry después de 30 minutos
                await asyncio.sleep(1800)

    async def _monitoring_loop(self):
        """Loop de monitoreo de recursos."""
        logger.info(
            "Resource monitoring loop started",
            interval_seconds=self.monitoring_interval,
        )

        while self.running:
            try:
                await asyncio.sleep(self.monitoring_interval)

                logger.info("Running resource monitoring...")

                # Obtener métricas de todos los recursos
                metrics = {}
                for resource_type in ResourceType:
                    try:
                        metric = await self.manager.get_resource_metrics(resource_type)
                        metrics[resource_type.value] = {
                            "total_items": metric.total_items,
                            "size_mb": metric.total_size_bytes / (1024 * 1024),
                            "usage_percentage": metric.usage_percentage * 100,
                            "priority": metric.cleanup_priority.name,
                        }

                        # Schedule cleanup si prioridad es alta o crítica
                        if metric.cleanup_priority in [
                            CleanupPriority.HIGH,
                            CleanupPriority.CRITICAL,
                        ]:
                            await self.manager.schedule_cleanup_task(
                                resource_type=resource_type,
                                target_id="all",
                                priority=metric.cleanup_priority,
                                reason=f"High resource usage: {metric.usage_percentage:.1%}",
                            )

                    except Exception as e:
                        logger.error(
                            "Failed to get metrics",
                            resource_type=resource_type,
                            error=str(e),
                        )

                logger.info("Resource monitoring completed", metrics=metrics)

                # Procesar cola de limpieza si hay tareas pendientes
                if self.manager.cleanup_queue:
                    logger.info(
                        "Processing cleanup queue",
                        queue_size=len(self.manager.cleanup_queue),
                    )
                    await self.manager.process_cleanup_queue(max_tasks=5)

            except asyncio.CancelledError:
                logger.info("Monitoring loop cancelled")
                break
            except Exception as e:
                logger.error("Resource monitoring failed", error=str(e), exc_info=True)
                # Retry después de 5 minutos
                await asyncio.sleep(300)


# Global worker instance
_cleanup_worker: Optional[ResourceCleanupWorker] = None


def get_cleanup_worker() -> ResourceCleanupWorker:
    """
    Obtiene instancia singleton del worker.

    Returns:
        ResourceCleanupWorker instance
    """
    global _cleanup_worker

    if _cleanup_worker is None:
        _cleanup_worker = ResourceCleanupWorker()

    return _cleanup_worker


@asynccontextmanager
async def lifespan_cleanup_worker():
    """
    Context manager para integración con FastAPI lifespan.

    Usage:
        app = FastAPI(lifespan=lifespan_cleanup_worker)
    """
    worker = get_cleanup_worker()
    await worker.start()

    try:
        yield
    finally:
        await worker.stop()


# Signal handlers para graceful shutdown
def setup_signal_handlers(worker: ResourceCleanupWorker):
    """
    Configura handlers para SIGINT y SIGTERM.

    Args:
        worker: Worker instance
    """

    def signal_handler(signum, frame):
        logger.info("Received shutdown signal", signal=signum)
        asyncio.create_task(worker.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


# Standalone runner (para testing)
async def run_standalone():
    """Run worker as standalone process."""
    worker = get_cleanup_worker()
    setup_signal_handlers(worker)

    await worker.start()

    # Keep running until stopped
    try:
        while worker.running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(run_standalone())
