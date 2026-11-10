"""
Integration Tests for ResourceCleanupWorker

Tests:
- Worker startup and shutdown
- Concurrent task execution
- Graceful cancellation
- Error recovery
- Monitoring loop integration
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
import os

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_RESOURCE_WORKER", "false").lower() != "true",
    reason="Integration ResourceCleanupWorker deshabilitado por defecto (requires external services).",
)

from src.workers.resource_cleanup_worker import ResourceCleanupWorker, get_cleanup_worker
from src.services.resource_lifecycle_manager import ResourceType, CleanupPriority


class TestResourceCleanupWorker:
    """Integration tests for ResourceCleanupWorker."""

    @pytest.fixture
    def worker(self):
        """Create worker instance."""
        return ResourceCleanupWorker()

    @pytest.mark.asyncio
    async def test_worker_initialization(self, worker):
        """Test worker initializes with correct intervals."""
        # Assert
        assert worker.redis_cleanup_interval > 0
        assert worker.weaviate_cleanup_interval > 0
        assert worker.minio_cleanup_interval > 0
        assert worker.monitoring_interval > 0
        assert not worker.running
        assert len(worker.tasks) == 0

    @pytest.mark.asyncio
    async def test_worker_start_creates_tasks(self, worker):
        """Test that starting worker creates all background tasks."""
        # Act
        await worker.start()

        try:
            # Assert
            assert worker.running
            assert len(worker.tasks) == 4  # 4 concurrent tasks

            # Verify task names
            task_names = [task.get_name() for task in worker.tasks]
            assert "redis_cleanup" in task_names
            assert "weaviate_cleanup" in task_names
            assert "minio_cleanup" in task_names
            assert "resource_monitoring" in task_names

            # Verify all tasks are running
            for task in worker.tasks:
                assert not task.done()

        finally:
            await worker.stop()

    @pytest.mark.asyncio
    async def test_worker_stop_cancels_tasks(self, worker):
        """Test that stopping worker cancels all tasks."""
        # Arrange
        await worker.start()
        assert worker.running
        assert len(worker.tasks) == 4

        # Act
        await worker.stop()

        # Assert
        assert not worker.running
        for task in worker.tasks:
            assert task.done()
            assert task.cancelled()

    @pytest.mark.asyncio
    async def test_worker_double_start_ignored(self, worker):
        """Test that starting worker twice doesn't create duplicate tasks."""
        # Act
        await worker.start()
        task_count_first = len(worker.tasks)

        await worker.start()  # Second start should be ignored
        task_count_second = len(worker.tasks)

        try:
            # Assert
            assert task_count_first == 4
            assert task_count_second == 4  # No duplicates

        finally:
            await worker.stop()

    @pytest.mark.asyncio
    async def test_redis_cleanup_loop_executes(self, worker):
        """Test Redis cleanup loop executes periodically."""
        # Arrange
        worker.redis_cleanup_interval = 0.1  # 100ms for fast test

        cleanup_called = asyncio.Event()

        async def mock_cleanup(resource_type):
            if resource_type == ResourceType.REDIS_CACHE:
                cleanup_called.set()
            return {"redis": 5}

        worker.manager.cleanup_expired_resources = AsyncMock(side_effect=mock_cleanup)

        # Act
        await worker.start()

        try:
            # Wait for cleanup to be called (with timeout)
            await asyncio.wait_for(cleanup_called.wait(), timeout=2.0)

            # Assert
            assert cleanup_called.is_set()
            worker.manager.cleanup_expired_resources.assert_called()

        finally:
            await worker.stop()

    @pytest.mark.asyncio
    async def test_monitoring_loop_schedules_cleanup(self, worker):
        """Test monitoring loop schedules cleanup for high usage."""
        # Arrange
        worker.monitoring_interval = 0.1  # 100ms for fast test

        # Mock high usage metrics
        mock_metrics = MagicMock()
        mock_metrics.total_items = 1000
        mock_metrics.total_size_bytes = 100 * 1024 * 1024
        mock_metrics.usage_percentage = 0.85  # 85% usage
        mock_metrics.cleanup_priority = CleanupPriority.HIGH

        worker.manager.get_resource_metrics = AsyncMock(return_value=mock_metrics)
        worker.manager.schedule_cleanup_task = AsyncMock()

        # Act
        await worker.start()

        try:
            # Wait for monitoring to run
            await asyncio.sleep(0.3)

            # Assert
            assert worker.manager.schedule_cleanup_task.called

        finally:
            await worker.stop()

    @pytest.mark.asyncio
    async def test_cleanup_loop_error_recovery(self, worker):
        """Test cleanup loop recovers from errors."""
        # Arrange
        worker.redis_cleanup_interval = 0.1

        call_count = 0

        async def mock_cleanup_with_error(resource_type):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Simulated error")
            return {"redis": 0}

        worker.manager.cleanup_expired_resources = AsyncMock(side_effect=mock_cleanup_with_error)

        # Act
        await worker.start()

        try:
            # Wait for multiple attempts
            await asyncio.sleep(0.5)

            # Assert - should recover and continue
            assert call_count >= 2  # First call failed, but loop continued

        finally:
            await worker.stop()

    @pytest.mark.asyncio
    async def test_worker_processes_cleanup_queue(self, worker):
        """Test that worker processes scheduled cleanup tasks."""
        # Arrange
        worker.monitoring_interval = 0.1

        # Schedule some cleanup tasks
        await worker.manager.schedule_cleanup_task(
            resource_type=ResourceType.REDIS_CACHE,
            target_id="all",
            priority=CleanupPriority.HIGH,
            reason="Test task"
        )

        worker.manager.process_cleanup_queue = AsyncMock()

        # Act
        await worker.start()

        try:
            # Wait for monitoring to process queue
            await asyncio.sleep(0.3)

            # Assert
            worker.manager.process_cleanup_queue.assert_called()

        finally:
            await worker.stop()

    @pytest.mark.asyncio
    async def test_concurrent_task_execution(self, worker):
        """Test that all cleanup tasks run concurrently."""
        # Arrange
        worker.redis_cleanup_interval = 0.1
        worker.weaviate_cleanup_interval = 0.1
        worker.minio_cleanup_interval = 0.1
        worker.monitoring_interval = 0.1

        redis_called = asyncio.Event()
        weaviate_called = asyncio.Event()
        minio_called = asyncio.Event()

        async def mock_cleanup(resource_type):
            if resource_type == ResourceType.REDIS_CACHE:
                redis_called.set()
            elif resource_type == ResourceType.WEAVIATE_VECTORS:
                weaviate_called.set()
            elif resource_type == ResourceType.MINIO_FILES:
                minio_called.set()
            return {resource_type.value: 0}

        worker.manager.cleanup_expired_resources = AsyncMock(side_effect=mock_cleanup)

        # Act
        await worker.start()

        try:
            # Wait for all tasks to execute at least once
            await asyncio.wait_for(
                asyncio.gather(
                    redis_called.wait(),
                    weaviate_called.wait(),
                    minio_called.wait()
                ),
                timeout=2.0
            )

            # Assert
            assert redis_called.is_set()
            assert weaviate_called.is_set()
            assert minio_called.is_set()

        finally:
            await worker.stop()


class TestGetCleanupWorker:
    """Test get_cleanup_worker singleton."""

    def test_get_cleanup_worker_returns_singleton(self):
        """Test that get_cleanup_worker returns same instance."""
        # Act
        worker1 = get_cleanup_worker()
        worker2 = get_cleanup_worker()

        # Assert
        assert worker1 is worker2

    def test_get_cleanup_worker_returns_worker_instance(self):
        """Test that get_cleanup_worker returns ResourceCleanupWorker."""
        # Act
        worker = get_cleanup_worker()

        # Assert
        assert isinstance(worker, ResourceCleanupWorker)


class TestWorkerConfiguration:
    """Test worker configuration from environment variables."""

    @patch.dict("os.environ", {
        "REDIS_CLEANUP_INTERVAL_SECONDS": "1800",
        "RAG_CLEANUP_INTERVAL_SECONDS": "10800",
        "MINIO_CLEANUP_INTERVAL_SECONDS": "43200",
        "RESOURCE_MONITORING_INTERVAL_SECONDS": "900"
    })
    def test_worker_reads_env_variables(self):
        """Test worker reads configuration from env vars."""
        # Act
        worker = ResourceCleanupWorker()

        # Assert
        assert worker.redis_cleanup_interval == 1800
        assert worker.weaviate_cleanup_interval == 10800
        assert worker.minio_cleanup_interval == 43200
        assert worker.monitoring_interval == 900

    @patch.dict("os.environ", {}, clear=True)
    def test_worker_uses_defaults(self):
        """Test worker uses default values when env vars not set."""
        # Act
        worker = ResourceCleanupWorker()

        # Assert - Should have default values
        assert worker.redis_cleanup_interval == 3600  # 1 hour default
        assert worker.weaviate_cleanup_interval == 21600  # 6 hours default
        assert worker.minio_cleanup_interval == 86400  # 24 hours default
        assert worker.monitoring_interval == 1800  # 30 min default
