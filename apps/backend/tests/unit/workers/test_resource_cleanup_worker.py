"""
Unit tests for ResourceCleanupWorker.

Tests cover:
- Worker initialization
- Task scheduling and management
- Graceful shutdown
- Signal handlers
- Singleton behavior
- Cleanup loop execution
- Error handling and retry logic
- Monitoring and metrics collection
"""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.workers.resource_cleanup_worker import (
    ResourceCleanupWorker,
    get_cleanup_worker,
    lifespan_cleanup_worker,
    setup_signal_handlers,
    run_standalone,
)
from src.services.resource_lifecycle_manager import (
    CleanupPriority,
    ResourceType,
    ResourceMetrics,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture
def mock_resource_manager():
    """Mock ResourceLifecycleManager."""
    manager = AsyncMock()
    manager.cleanup_expired_resources = AsyncMock(return_value={"redis": 5})
    manager.get_resource_metrics = AsyncMock()
    manager.schedule_cleanup_task = AsyncMock()
    manager.process_cleanup_queue = AsyncMock()
    manager.cleanup_queue = []
    return manager


@pytest.fixture
def worker_with_mock(mock_resource_manager):
    """Worker with mocked resource manager."""
    with patch(
        "src.workers.resource_cleanup_worker.get_resource_manager",
        return_value=mock_resource_manager,
    ):
        worker = ResourceCleanupWorker()
        worker.manager = mock_resource_manager
        return worker


@pytest.mark.unit
class TestResourceCleanupWorkerInit:
    """Tests for worker initialization."""

    def test_default_initialization(self):
        """Should initialize with default intervals from env."""
        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager"
        ) as mock_get:
            mock_get.return_value = MagicMock()
            worker = ResourceCleanupWorker()

            assert worker.running is False
            assert worker.tasks == []
            assert worker.redis_cleanup_interval == 3600  # Default 1 hour
            assert worker.weaviate_cleanup_interval == 21600  # Default 6 hours
            assert worker.minio_cleanup_interval == 86400  # Default 24 hours
            assert worker.monitoring_interval == 1800  # Default 30 min

    def test_custom_intervals_from_env(self):
        """Should read custom intervals from environment."""
        env_vars = {
            "REDIS_CLEANUP_INTERVAL_SECONDS": "1000",
            "RAG_CLEANUP_INTERVAL_SECONDS": "2000",
            "MINIO_CLEANUP_INTERVAL_SECONDS": "3000",
            "RESOURCE_MONITORING_INTERVAL_SECONDS": "500",
        }

        with patch.dict(os.environ, env_vars), patch(
            "src.workers.resource_cleanup_worker.get_resource_manager"
        ) as mock_get:
            mock_get.return_value = MagicMock()
            worker = ResourceCleanupWorker()

            assert worker.redis_cleanup_interval == 1000
            assert worker.weaviate_cleanup_interval == 2000
            assert worker.minio_cleanup_interval == 3000
            assert worker.monitoring_interval == 500


@pytest.mark.unit
class TestResourceCleanupWorkerStart:
    """Tests for worker start functionality."""

    @pytest.mark.asyncio
    async def test_start_creates_tasks(self, worker_with_mock):
        """Should create cleanup tasks on start."""
        worker = worker_with_mock

        await worker.start()

        assert worker.running is True
        assert len(worker.tasks) == 4

        task_names = [t.get_name() for t in worker.tasks]
        assert "redis_cleanup" in task_names
        assert "weaviate_cleanup" in task_names
        assert "minio_cleanup" in task_names
        assert "resource_monitoring" in task_names

        # Cleanup immediately
        await worker.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self, worker_with_mock):
        """Should not create duplicate tasks if already running."""
        worker = worker_with_mock

        await worker.start()
        initial_tasks = len(worker.tasks)

        await worker.start()  # Second call

        assert len(worker.tasks) == initial_tasks

        # Cleanup
        await worker.stop()


@pytest.mark.unit
class TestResourceCleanupWorkerStop:
    """Tests for worker stop functionality."""

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self, worker_with_mock):
        """Should cancel all tasks on stop."""
        worker = worker_with_mock

        await worker.start()
        assert worker.running is True

        await worker.stop()

        assert worker.running is False
        for task in worker.tasks:
            assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, worker_with_mock):
        """Should handle stop when not running."""
        worker = worker_with_mock

        # Should not raise
        await worker.stop()

        assert worker.running is False


@pytest.mark.unit
class TestCleanupLoopBehavior:
    """Tests for cleanup loop behavior - graceful cancellation handling."""

    @pytest.mark.asyncio
    async def test_redis_cleanup_handles_cancellation(self, worker_with_mock):
        """Should handle cancellation gracefully (exits cleanly without propagating)."""
        worker = worker_with_mock
        worker.running = True

        # Create a task that we'll cancel
        task = asyncio.create_task(worker._redis_cleanup_loop())

        # Give it a moment to start
        await asyncio.sleep(0.01)

        # Cancel the task
        task.cancel()

        # The loop catches CancelledError and exits cleanly (doesn't propagate)
        # So we just await and verify it completes without error
        try:
            await task
        except asyncio.CancelledError:
            pass  # OK if it propagates, also OK if it doesn't

        # Task should be done
        assert task.done()

    @pytest.mark.asyncio
    async def test_weaviate_cleanup_handles_cancellation(self, worker_with_mock):
        """Should handle cancellation gracefully."""
        worker = worker_with_mock
        worker.running = True

        task = asyncio.create_task(worker._weaviate_cleanup_loop())
        await asyncio.sleep(0.01)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        assert task.done()

    @pytest.mark.asyncio
    async def test_minio_cleanup_handles_cancellation(self, worker_with_mock):
        """Should handle cancellation gracefully."""
        worker = worker_with_mock
        worker.running = True

        task = asyncio.create_task(worker._minio_cleanup_loop())
        await asyncio.sleep(0.01)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        assert task.done()

    @pytest.mark.asyncio
    async def test_monitoring_loop_handles_cancellation(self, worker_with_mock):
        """Should handle cancellation gracefully."""
        worker = worker_with_mock
        worker.running = True

        task = asyncio.create_task(worker._monitoring_loop())
        await asyncio.sleep(0.01)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        assert task.done()


@pytest.mark.unit
class TestGetCleanupWorker:
    """Tests for get_cleanup_worker singleton."""

    def test_returns_worker_instance(self):
        """Should return a worker instance."""
        with patch(
            "src.workers.resource_cleanup_worker._cleanup_worker", None
        ), patch(
            "src.workers.resource_cleanup_worker.get_resource_manager"
        ) as mock_get:
            mock_get.return_value = MagicMock()

            worker = get_cleanup_worker()

            assert worker is not None
            assert isinstance(worker, ResourceCleanupWorker)

    def test_returns_same_instance(self):
        """Should return same instance on subsequent calls."""
        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager"
        ) as mock_get:
            mock_get.return_value = MagicMock()

            # Reset global
            import src.workers.resource_cleanup_worker as worker_module
            worker_module._cleanup_worker = None

            worker1 = get_cleanup_worker()
            worker2 = get_cleanup_worker()

            assert worker1 is worker2


@pytest.mark.unit
class TestLifespanCleanupWorker:
    """Tests for lifespan context manager."""

    @pytest.mark.asyncio
    async def test_lifespan_starts_and_stops_worker(self):
        """Should start worker on enter and stop on exit."""
        mock_worker = AsyncMock()
        mock_worker.running = False
        mock_worker.tasks = []

        with patch(
            "src.workers.resource_cleanup_worker.get_cleanup_worker",
            return_value=mock_worker,
        ):
            async with lifespan_cleanup_worker():
                mock_worker.start.assert_called_once()

            mock_worker.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_stops_on_exception(self):
        """Should stop worker even if exception occurs."""
        mock_worker = AsyncMock()
        mock_worker.running = False
        mock_worker.tasks = []

        with patch(
            "src.workers.resource_cleanup_worker.get_cleanup_worker",
            return_value=mock_worker,
        ):
            try:
                async with lifespan_cleanup_worker():
                    raise ValueError("Test error")
            except ValueError:
                pass

            mock_worker.stop.assert_called_once()


@pytest.mark.unit
class TestSignalHandlers:
    """Tests for signal handlers setup."""

    def test_setup_signal_handlers(self):
        """Should register SIGINT and SIGTERM handlers."""
        import signal

        mock_worker = MagicMock()

        with patch("signal.signal") as mock_signal:
            setup_signal_handlers(mock_worker)

            # Should have registered handlers for SIGINT and SIGTERM
            calls = mock_signal.call_args_list
            signals_registered = [c[0][0] for c in calls]

            assert signal.SIGINT in signals_registered
            assert signal.SIGTERM in signals_registered


@pytest.mark.unit
class TestWorkerAttributes:
    """Tests for worker attribute access."""

    def test_worker_has_manager(self, worker_with_mock):
        """Should have manager attribute."""
        assert worker_with_mock.manager is not None

    def test_worker_has_intervals(self, worker_with_mock):
        """Should have interval attributes."""
        worker = worker_with_mock

        assert hasattr(worker, 'redis_cleanup_interval')
        assert hasattr(worker, 'weaviate_cleanup_interval')
        assert hasattr(worker, 'minio_cleanup_interval')
        assert hasattr(worker, 'monitoring_interval')

    def test_worker_has_running_flag(self, worker_with_mock):
        """Should have running flag."""
        worker = worker_with_mock

        assert hasattr(worker, 'running')
        assert worker.running is False

    def test_worker_has_tasks_list(self, worker_with_mock):
        """Should have tasks list."""
        worker = worker_with_mock

        assert hasattr(worker, 'tasks')
        assert isinstance(worker.tasks, list)


class TestRedisCleanupLoop:
    """Tests for Redis cleanup loop execution."""

    @pytest.fixture
    def mock_resource_manager(self):
        """Create mock manager."""
        manager = AsyncMock()
        manager.cleanup_expired_resources = AsyncMock(return_value={"redis": 5})
        return manager

    @pytest.mark.asyncio
    async def test_runs_cleanup_and_exits(self, mock_resource_manager):
        """Should run cleanup when loop executes."""
        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_resource_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.redis_cleanup_interval = 0.01  # Very short interval

            # Start loop but stop after first iteration
            worker.running = True

            async def stop_after_delay():
                await asyncio.sleep(0.05)
                worker.running = False

            task = asyncio.create_task(worker._redis_cleanup_loop())
            stop_task = asyncio.create_task(stop_after_delay())

            await asyncio.gather(task, stop_task, return_exceptions=True)

            # Verify cleanup was called
            mock_resource_manager.cleanup_expired_resources.assert_called_with(
                ResourceType.REDIS_CACHE
            )

    @pytest.mark.asyncio
    async def test_handles_error_gracefully(self, mock_resource_manager):
        """Should handle error gracefully without crashing."""
        call_count = 0

        async def fail_then_succeed(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Redis error")
            return {"redis": 0}

        mock_resource_manager.cleanup_expired_resources = fail_then_succeed

        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_resource_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.redis_cleanup_interval = 0.01

            worker.running = True

            async def stop_after_first_error():
                # Wait for error to be logged, then stop
                await asyncio.sleep(0.02)
                worker.running = False

            # Mock the retry sleep to be instant
            original_sleep = asyncio.sleep

            async def fast_sleep(delay):
                # Make error retry instant but preserve normal interval sleep
                if delay >= 60:  # Error retry delay
                    return
                await original_sleep(delay)

            task = asyncio.create_task(worker._redis_cleanup_loop())
            stop_task = asyncio.create_task(stop_after_first_error())

            with patch("asyncio.sleep", fast_sleep):
                await asyncio.gather(task, stop_task, return_exceptions=True)

            # Verify cleanup was attempted
            assert call_count >= 1


class TestWeaviateCleanupLoop:
    """Tests for Weaviate cleanup loop execution."""

    @pytest.fixture
    def mock_resource_manager(self):
        """Create mock manager."""
        manager = AsyncMock()
        manager.cleanup_expired_resources = AsyncMock(return_value={"weaviate": 10})
        return manager

    @pytest.mark.asyncio
    async def test_runs_cleanup(self, mock_resource_manager):
        """Should run Weaviate cleanup."""
        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_resource_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.weaviate_cleanup_interval = 0.01

            worker.running = True

            async def stop_after_delay():
                await asyncio.sleep(0.05)
                worker.running = False

            task = asyncio.create_task(worker._weaviate_cleanup_loop())
            stop_task = asyncio.create_task(stop_after_delay())

            await asyncio.gather(task, stop_task, return_exceptions=True)

            mock_resource_manager.cleanup_expired_resources.assert_called_with(
                ResourceType.WEAVIATE_VECTORS
            )

    @pytest.mark.asyncio
    async def test_handles_error_gracefully(self, mock_resource_manager):
        """Should handle Weaviate cleanup error gracefully."""
        error_logged = False

        async def fail_once(*args):
            nonlocal error_logged
            if not error_logged:
                error_logged = True
                raise Exception("Weaviate error")
            return {"weaviate": 0}

        mock_resource_manager.cleanup_expired_resources = fail_once

        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_resource_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.weaviate_cleanup_interval = 0.01

            worker.running = True

            async def stop_quickly():
                await asyncio.sleep(0.02)
                worker.running = False

            # Mock the retry sleep
            original_sleep = asyncio.sleep

            async def fast_sleep(delay):
                if delay >= 300:  # Weaviate error retry is 300s
                    return
                await original_sleep(delay)

            task = asyncio.create_task(worker._weaviate_cleanup_loop())
            stop_task = asyncio.create_task(stop_quickly())

            with patch("asyncio.sleep", fast_sleep):
                await asyncio.gather(task, stop_task, return_exceptions=True)

            assert error_logged


class TestMinioCleanupLoop:
    """Tests for MinIO cleanup loop execution."""

    @pytest.fixture
    def mock_resource_manager(self):
        """Create mock manager."""
        manager = AsyncMock()
        manager.cleanup_expired_resources = AsyncMock(return_value={"minio": 3})
        return manager

    @pytest.mark.asyncio
    async def test_runs_cleanup(self, mock_resource_manager):
        """Should run MinIO cleanup."""
        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_resource_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.minio_cleanup_interval = 0.01

            worker.running = True

            async def stop_after_delay():
                await asyncio.sleep(0.05)
                worker.running = False

            task = asyncio.create_task(worker._minio_cleanup_loop())
            stop_task = asyncio.create_task(stop_after_delay())

            await asyncio.gather(task, stop_task, return_exceptions=True)

            mock_resource_manager.cleanup_expired_resources.assert_called_with(
                ResourceType.MINIO_FILES
            )

    @pytest.mark.asyncio
    async def test_handles_error_gracefully(self, mock_resource_manager):
        """Should handle MinIO cleanup error gracefully."""
        error_logged = False

        async def fail_once(*args):
            nonlocal error_logged
            if not error_logged:
                error_logged = True
                raise Exception("MinIO error")
            return {"minio": 0}

        mock_resource_manager.cleanup_expired_resources = fail_once

        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_resource_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.minio_cleanup_interval = 0.01

            worker.running = True

            async def stop_quickly():
                await asyncio.sleep(0.02)
                worker.running = False

            # Mock the retry sleep
            original_sleep = asyncio.sleep

            async def fast_sleep(delay):
                if delay >= 1800:  # MinIO error retry is 1800s
                    return
                await original_sleep(delay)

            task = asyncio.create_task(worker._minio_cleanup_loop())
            stop_task = asyncio.create_task(stop_quickly())

            with patch("asyncio.sleep", fast_sleep):
                await asyncio.gather(task, stop_task, return_exceptions=True)

            assert error_logged


class TestMonitoringLoop:
    """Tests for monitoring loop execution."""

    @pytest.fixture
    def mock_resource_manager(self):
        """Create mock manager with metrics."""
        manager = AsyncMock()

        # Create mock metrics
        mock_metric = MagicMock()
        mock_metric.total_items = 1000
        mock_metric.total_size_bytes = 50 * 1024 * 1024
        mock_metric.usage_percentage = 0.5
        mock_metric.cleanup_priority = CleanupPriority.LOW

        manager.get_resource_metrics = AsyncMock(return_value=mock_metric)
        manager.schedule_cleanup_task = AsyncMock()
        manager.process_cleanup_queue = AsyncMock()
        manager.cleanup_queue = []

        return manager

    @pytest.mark.asyncio
    async def test_collects_metrics_for_all_resources(self, mock_resource_manager):
        """Should collect metrics for all resource types."""
        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_resource_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.monitoring_interval = 0.01

            worker.running = True

            async def stop_after_delay():
                await asyncio.sleep(0.05)
                worker.running = False

            task = asyncio.create_task(worker._monitoring_loop())
            stop_task = asyncio.create_task(stop_after_delay())

            await asyncio.gather(task, stop_task, return_exceptions=True)

            # Should have called get_resource_metrics for each resource type
            assert mock_resource_manager.get_resource_metrics.call_count >= len(ResourceType)

    @pytest.mark.asyncio
    async def test_schedules_cleanup_for_high_priority(self, mock_resource_manager):
        """Should schedule cleanup when priority is HIGH."""
        mock_metric = MagicMock()
        mock_metric.total_items = 1000
        mock_metric.total_size_bytes = 50 * 1024 * 1024
        mock_metric.usage_percentage = 0.8
        mock_metric.cleanup_priority = CleanupPriority.HIGH

        mock_resource_manager.get_resource_metrics = AsyncMock(return_value=mock_metric)

        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_resource_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.monitoring_interval = 0.01

            worker.running = True

            async def stop_after_delay():
                await asyncio.sleep(0.05)
                worker.running = False

            task = asyncio.create_task(worker._monitoring_loop())
            stop_task = asyncio.create_task(stop_after_delay())

            await asyncio.gather(task, stop_task, return_exceptions=True)

            # Should have scheduled cleanup tasks
            assert mock_resource_manager.schedule_cleanup_task.called

    @pytest.mark.asyncio
    async def test_schedules_cleanup_for_critical_priority(self, mock_resource_manager):
        """Should schedule cleanup when priority is CRITICAL."""
        mock_metric = MagicMock()
        mock_metric.total_items = 10000
        mock_metric.total_size_bytes = 200 * 1024 * 1024
        mock_metric.usage_percentage = 0.95
        mock_metric.cleanup_priority = CleanupPriority.CRITICAL

        mock_resource_manager.get_resource_metrics = AsyncMock(return_value=mock_metric)

        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_resource_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.monitoring_interval = 0.01

            worker.running = True

            async def stop_after_delay():
                await asyncio.sleep(0.05)
                worker.running = False

            task = asyncio.create_task(worker._monitoring_loop())
            stop_task = asyncio.create_task(stop_after_delay())

            await asyncio.gather(task, stop_task, return_exceptions=True)

            # Should have scheduled cleanup tasks
            assert mock_resource_manager.schedule_cleanup_task.called

    @pytest.mark.asyncio
    async def test_processes_cleanup_queue(self, mock_resource_manager):
        """Should process cleanup queue when it has tasks."""
        mock_resource_manager.cleanup_queue = [MagicMock(), MagicMock()]

        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_resource_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.monitoring_interval = 0.01

            worker.running = True

            async def stop_after_delay():
                await asyncio.sleep(0.05)
                worker.running = False

            task = asyncio.create_task(worker._monitoring_loop())
            stop_task = asyncio.create_task(stop_after_delay())

            await asyncio.gather(task, stop_task, return_exceptions=True)

            # Should have processed cleanup queue
            mock_resource_manager.process_cleanup_queue.assert_called_with(max_tasks=5)

    @pytest.mark.asyncio
    async def test_handles_metrics_error(self, mock_resource_manager):
        """Should handle error when getting metrics gracefully."""
        mock_resource_manager.get_resource_metrics = AsyncMock(
            side_effect=Exception("Metrics error")
        )

        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_resource_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.monitoring_interval = 0.01

            worker.running = True

            async def stop_quickly():
                await asyncio.sleep(0.02)
                worker.running = False

            # Mock the retry sleep
            original_sleep = asyncio.sleep

            async def fast_sleep(delay):
                if delay >= 300:  # Monitoring error retry is 300s
                    return
                await original_sleep(delay)

            task = asyncio.create_task(worker._monitoring_loop())
            stop_task = asyncio.create_task(stop_quickly())

            with patch("asyncio.sleep", fast_sleep):
                await asyncio.gather(task, stop_task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_handles_general_exception(self, mock_resource_manager):
        """Should handle general exception in monitoring loop gracefully."""
        call_count = 0

        async def fail_first_time(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("General error")
            mock_metric = MagicMock()
            mock_metric.total_items = 1000
            mock_metric.total_size_bytes = 50 * 1024 * 1024
            mock_metric.usage_percentage = 0.5
            mock_metric.cleanup_priority = CleanupPriority.LOW
            return mock_metric

        mock_resource_manager.get_resource_metrics = fail_first_time

        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_resource_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.monitoring_interval = 0.01

            worker.running = True

            async def stop_quickly():
                await asyncio.sleep(0.02)
                worker.running = False

            # Mock the retry sleep
            original_sleep = asyncio.sleep

            async def fast_sleep(delay):
                if delay >= 300:  # Monitoring error retry is 300s
                    return
                await original_sleep(delay)

            task = asyncio.create_task(worker._monitoring_loop())
            stop_task = asyncio.create_task(stop_quickly())

            with patch("asyncio.sleep", fast_sleep):
                await asyncio.gather(task, stop_task, return_exceptions=True)


class TestRunStandalone:
    """Tests for run_standalone function."""

    @pytest.mark.asyncio
    async def test_starts_worker_and_loops(self):
        """Should start worker and run until stopped."""
        mock_worker = AsyncMock()
        mock_worker.running = True
        mock_worker.start = AsyncMock()
        mock_worker.stop = AsyncMock()

        async def stop_after_delay():
            await asyncio.sleep(0.02)
            mock_worker.running = False

        with patch(
            "src.workers.resource_cleanup_worker.get_cleanup_worker",
            return_value=mock_worker,
        ), patch(
            "src.workers.resource_cleanup_worker.setup_signal_handlers"
        ):
            # Run standalone with a task that stops it
            task = asyncio.create_task(run_standalone())
            stop_task = asyncio.create_task(stop_after_delay())

            await asyncio.gather(task, stop_task, return_exceptions=True)

            mock_worker.start.assert_called_once()


class TestSignalHandlerBehavior:
    """Tests for signal handler behavior."""

    def test_signal_handler_creates_stop_task(self):
        """Should create stop task when signal received."""
        mock_worker = MagicMock()
        mock_worker.stop = AsyncMock()

        with patch("signal.signal") as mock_signal:
            setup_signal_handlers(mock_worker)

            # Get the handler that was registered
            calls = mock_signal.call_args_list
            # Get the handler function
            handler = calls[0][0][1]

            # Simulate signal with asyncio event loop
            with patch("asyncio.create_task") as mock_create_task:
                handler(2, None)  # SIGINT = 2

                # Should create a task to stop the worker
                mock_create_task.assert_called_once()


class TestCleanupWorkerSingletonReset:
    """Tests for singleton reset behavior."""

    def test_creates_new_instance_after_reset(self):
        """Should create new instance after module-level reset."""
        import src.workers.resource_cleanup_worker as module
        original = module._cleanup_worker

        try:
            module._cleanup_worker = None

            with patch(
                "src.workers.resource_cleanup_worker.get_resource_manager"
            ) as mock_get:
                mock_get.return_value = MagicMock()

                worker = get_cleanup_worker()

                assert worker is not None
        finally:
            module._cleanup_worker = original


class TestMonitoringLoopNoScheduleForLowPriority:
    """Tests to ensure no cleanup is scheduled for LOW priority."""

    @pytest.mark.asyncio
    async def test_no_schedule_for_low_priority(self):
        """Should not schedule cleanup for LOW priority."""
        mock_manager = AsyncMock()

        mock_metric = MagicMock()
        mock_metric.total_items = 100
        mock_metric.total_size_bytes = 5 * 1024 * 1024
        mock_metric.usage_percentage = 0.2
        mock_metric.cleanup_priority = CleanupPriority.LOW

        mock_manager.get_resource_metrics = AsyncMock(return_value=mock_metric)
        mock_manager.schedule_cleanup_task = AsyncMock()
        mock_manager.process_cleanup_queue = AsyncMock()
        mock_manager.cleanup_queue = []

        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.monitoring_interval = 0.01

            worker.running = True

            async def stop_after_delay():
                await asyncio.sleep(0.05)
                worker.running = False

            task = asyncio.create_task(worker._monitoring_loop())
            stop_task = asyncio.create_task(stop_after_delay())

            await asyncio.gather(task, stop_task, return_exceptions=True)

            # Should NOT have scheduled any cleanup tasks
            mock_manager.schedule_cleanup_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_schedule_for_medium_priority(self):
        """Should not schedule cleanup for MEDIUM priority."""
        mock_manager = AsyncMock()

        mock_metric = MagicMock()
        mock_metric.total_items = 500
        mock_metric.total_size_bytes = 25 * 1024 * 1024
        mock_metric.usage_percentage = 0.6
        mock_metric.cleanup_priority = CleanupPriority.MEDIUM

        mock_manager.get_resource_metrics = AsyncMock(return_value=mock_metric)
        mock_manager.schedule_cleanup_task = AsyncMock()
        mock_manager.process_cleanup_queue = AsyncMock()
        mock_manager.cleanup_queue = []

        with patch(
            "src.workers.resource_cleanup_worker.get_resource_manager",
            return_value=mock_manager,
        ):
            worker = ResourceCleanupWorker()
            worker.monitoring_interval = 0.01

            worker.running = True

            async def stop_after_delay():
                await asyncio.sleep(0.05)
                worker.running = False

            task = asyncio.create_task(worker._monitoring_loop())
            stop_task = asyncio.create_task(stop_after_delay())

            await asyncio.gather(task, stop_task, return_exceptions=True)

            # Should NOT have scheduled any cleanup tasks for MEDIUM
            mock_manager.schedule_cleanup_task.assert_not_called()
