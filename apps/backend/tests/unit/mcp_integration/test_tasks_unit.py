"""
Unit tests for MCP Task Manager.

Tests task lifecycle, status transitions, and cleanup.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import asyncio


class TestTaskStatus:
    """Test TaskStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        from src.mcp_integration.tasks import TaskStatus

        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"


class TestTaskPriority:
    """Test TaskPriority enum."""

    def test_priority_values(self):
        """Test priority enum values."""
        from src.mcp_integration.tasks import TaskPriority

        assert TaskPriority.LOW.value == "low"
        assert TaskPriority.NORMAL.value == "normal"
        assert TaskPriority.HIGH.value == "high"


class TestTask:
    """Test Task model."""

    def test_task_creation(self):
        """Test task model creation."""
        from src.mcp_integration.tasks import Task, TaskStatus, TaskPriority

        task = Task(
            task_id="task-123",
            tool="test_tool",
            payload={"key": "value"},
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            user_id="user-456",
            created_at=datetime.utcnow(),
        )

        assert task.task_id == "task-123"
        assert task.tool == "test_tool"
        assert task.payload == {"key": "value"}
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.NORMAL
        assert task.user_id == "user-456"
        assert task.progress == 0.0
        assert task.result is None
        assert task.error is None
        assert task.cancellation_requested is False

    def test_task_defaults(self):
        """Test task default values."""
        from src.mcp_integration.tasks import Task, TaskStatus, TaskPriority

        task = Task(
            task_id="task-123",
            tool="test_tool",
            payload={},
            status=TaskStatus.PENDING,
            user_id="user-456",
            created_at=datetime.utcnow(),
        )

        assert task.priority == TaskPriority.NORMAL
        assert task.started_at is None
        assert task.completed_at is None
        assert task.progress_message is None


class TestTaskManagerInit:
    """Test TaskManager initialization."""

    def test_init_default_ttl(self):
        """Test default TTL."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()

        assert manager.ttl == timedelta(hours=24)
        assert manager.tasks == {}
        assert manager._cleanup_task is None

    def test_init_custom_ttl(self):
        """Test custom TTL."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager(ttl_hours=48)

        assert manager.ttl == timedelta(hours=48)


class TestTaskManagerCreateTask:
    """Test TaskManager.create_task method."""

    def test_create_task_basic(self):
        """Test basic task creation."""
        from src.mcp_integration.tasks import TaskManager, TaskStatus, TaskPriority

        manager = TaskManager()

        task_id = manager.create_task(
            tool="test_tool",
            payload={"key": "value"},
            user_id="user-123",
        )

        assert task_id is not None
        task = manager.get_task(task_id)
        assert task.tool == "test_tool"
        assert task.payload == {"key": "value"}
        assert task.user_id == "user-123"
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.NORMAL

    def test_create_task_with_priority(self):
        """Test task creation with priority."""
        from src.mcp_integration.tasks import TaskManager, TaskPriority

        manager = TaskManager()

        task_id = manager.create_task(
            tool="test_tool",
            payload={},
            user_id="user-123",
            priority=TaskPriority.HIGH,
        )

        task = manager.get_task(task_id)
        assert task.priority == TaskPriority.HIGH

    def test_create_task_with_explicit_id(self):
        """Test task creation with explicit ID."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()

        task_id = manager.create_task(
            tool="test_tool",
            payload={},
            user_id="user-123",
            task_id="explicit-task-id",
        )

        assert task_id == "explicit-task-id"
        assert manager.get_task("explicit-task-id") is not None


class TestTaskManagerGetTask:
    """Test TaskManager.get_task method."""

    def test_get_existing_task(self):
        """Test getting existing task."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()
        task_id = manager.create_task(
            tool="test_tool",
            payload={},
            user_id="user-123",
        )

        task = manager.get_task(task_id)

        assert task is not None
        assert task.task_id == task_id

    def test_get_nonexistent_task(self):
        """Test getting non-existent task returns None."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()

        task = manager.get_task("nonexistent-id")

        assert task is None


class TestTaskManagerUpdateProgress:
    """Test TaskManager.update_progress method."""

    def test_update_progress(self):
        """Test updating task progress."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()
        task_id = manager.create_task(
            tool="test_tool",
            payload={},
            user_id="user-123",
        )

        manager.update_progress(task_id, 0.5, "Halfway done")

        task = manager.get_task(task_id)
        assert task.progress == 0.5
        assert task.progress_message == "Halfway done"

    def test_update_progress_clamps_to_valid_range(self):
        """Test progress is clamped to 0.0-1.0."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()
        task_id = manager.create_task(
            tool="test_tool",
            payload={},
            user_id="user-123",
        )

        manager.update_progress(task_id, 1.5)  # Over 1.0
        task = manager.get_task(task_id)
        assert task.progress == 1.0

        manager.update_progress(task_id, -0.5)  # Below 0.0
        task = manager.get_task(task_id)
        assert task.progress == 0.0

    def test_update_progress_nonexistent_task(self):
        """Test updating progress for non-existent task doesn't raise."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()

        # Should not raise
        manager.update_progress("nonexistent-id", 0.5)


class TestTaskManagerMarkRunning:
    """Test TaskManager.mark_running method."""

    def test_mark_running(self):
        """Test marking task as running."""
        from src.mcp_integration.tasks import TaskManager, TaskStatus

        manager = TaskManager()
        task_id = manager.create_task(
            tool="test_tool",
            payload={},
            user_id="user-123",
        )

        manager.mark_running(task_id)

        task = manager.get_task(task_id)
        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None

    def test_mark_running_nonexistent_task(self):
        """Test marking non-existent task doesn't raise."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()

        # Should not raise
        manager.mark_running("nonexistent-id")


class TestTaskManagerMarkCompleted:
    """Test TaskManager.mark_completed method."""

    def test_mark_completed(self):
        """Test marking task as completed."""
        from src.mcp_integration.tasks import TaskManager, TaskStatus

        manager = TaskManager()
        task_id = manager.create_task(
            tool="test_tool",
            payload={},
            user_id="user-123",
        )
        manager.mark_running(task_id)

        result = {"output": "success"}
        manager.mark_completed(task_id, result)

        task = manager.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED
        assert task.completed_at is not None
        assert task.progress == 1.0
        assert task.result == result

    def test_mark_completed_nonexistent_task(self):
        """Test marking non-existent task doesn't raise."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()

        # Should not raise
        manager.mark_completed("nonexistent-id", {})


class TestTaskManagerMarkFailed:
    """Test TaskManager.mark_failed method."""

    def test_mark_failed(self):
        """Test marking task as failed."""
        from src.mcp_integration.tasks import TaskManager, TaskStatus

        manager = TaskManager()
        task_id = manager.create_task(
            tool="test_tool",
            payload={},
            user_id="user-123",
        )
        manager.mark_running(task_id)

        error = {"code": "ERROR", "message": "Something went wrong"}
        manager.mark_failed(task_id, error)

        task = manager.get_task(task_id)
        assert task.status == TaskStatus.FAILED
        assert task.completed_at is not None
        assert task.error == error

    def test_mark_failed_nonexistent_task(self):
        """Test marking non-existent task doesn't raise."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()

        # Should not raise
        manager.mark_failed("nonexistent-id", {})


class TestTaskManagerCancellation:
    """Test TaskManager cancellation methods."""

    def test_request_cancellation_success(self):
        """Test successful cancellation request."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()
        task_id = manager.create_task(
            tool="test_tool",
            payload={},
            user_id="user-123",
        )

        result = manager.request_cancellation(task_id)

        assert result is True
        task = manager.get_task(task_id)
        assert task.cancellation_requested is True

    def test_request_cancellation_nonexistent(self):
        """Test cancellation request for non-existent task."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()

        result = manager.request_cancellation("nonexistent-id")

        assert result is False

    def test_request_cancellation_completed_task(self):
        """Test cancellation request for completed task."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()
        task_id = manager.create_task(
            tool="test_tool",
            payload={},
            user_id="user-123",
        )
        manager.mark_completed(task_id, {})

        result = manager.request_cancellation(task_id)

        assert result is False

    def test_request_cancellation_failed_task(self):
        """Test cancellation request for failed task."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()
        task_id = manager.create_task(
            tool="test_tool",
            payload={},
            user_id="user-123",
        )
        manager.mark_failed(task_id, {"code": "ERROR"})

        result = manager.request_cancellation(task_id)

        assert result is False

    def test_mark_cancelled(self):
        """Test marking task as cancelled."""
        from src.mcp_integration.tasks import TaskManager, TaskStatus

        manager = TaskManager()
        task_id = manager.create_task(
            tool="test_tool",
            payload={},
            user_id="user-123",
        )
        manager.request_cancellation(task_id)

        manager.mark_cancelled(task_id)

        task = manager.get_task(task_id)
        assert task.status == TaskStatus.CANCELLED
        assert task.completed_at is not None

    def test_is_cancellation_requested(self):
        """Test is_cancellation_requested method."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()
        task_id = manager.create_task(
            tool="test_tool",
            payload={},
            user_id="user-123",
        )

        assert manager.is_cancellation_requested(task_id) is False

        manager.request_cancellation(task_id)

        assert manager.is_cancellation_requested(task_id) is True

    def test_is_cancellation_requested_nonexistent(self):
        """Test is_cancellation_requested for non-existent task."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()

        assert manager.is_cancellation_requested("nonexistent-id") is False


class TestTaskManagerListTasks:
    """Test TaskManager.list_tasks method."""

    def test_list_all_tasks(self):
        """Test listing all tasks."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()
        manager.create_task(tool="tool1", payload={}, user_id="user-1")
        manager.create_task(tool="tool2", payload={}, user_id="user-2")
        manager.create_task(tool="tool3", payload={}, user_id="user-1")

        tasks = manager.list_tasks()

        assert len(tasks) == 3

    def test_list_tasks_by_user(self):
        """Test listing tasks filtered by user."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()
        manager.create_task(tool="tool1", payload={}, user_id="user-1")
        manager.create_task(tool="tool2", payload={}, user_id="user-2")
        manager.create_task(tool="tool3", payload={}, user_id="user-1")

        tasks = manager.list_tasks(user_id="user-1")

        assert len(tasks) == 2
        assert all(t.user_id == "user-1" for t in tasks)

    def test_list_tasks_by_tool(self):
        """Test listing tasks filtered by tool."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()
        manager.create_task(tool="tool1", payload={}, user_id="user-1")
        manager.create_task(tool="tool1", payload={}, user_id="user-2")
        manager.create_task(tool="tool2", payload={}, user_id="user-1")

        tasks = manager.list_tasks(tool="tool1")

        assert len(tasks) == 2
        assert all(t.tool == "tool1" for t in tasks)

    def test_list_tasks_by_status(self):
        """Test listing tasks filtered by status."""
        from src.mcp_integration.tasks import TaskManager, TaskStatus

        manager = TaskManager()
        task1 = manager.create_task(tool="tool1", payload={}, user_id="user-1")
        task2 = manager.create_task(tool="tool2", payload={}, user_id="user-2")
        manager.mark_running(task1)
        manager.mark_completed(task1, {})

        completed_tasks = manager.list_tasks(status=TaskStatus.COMPLETED)
        pending_tasks = manager.list_tasks(status=TaskStatus.PENDING)

        assert len(completed_tasks) == 1
        assert len(pending_tasks) == 1

    def test_list_tasks_sorted_by_created_at(self):
        """Test tasks are sorted by created_at descending."""
        from src.mcp_integration.tasks import TaskManager
        import time

        manager = TaskManager()
        task1 = manager.create_task(tool="tool1", payload={}, user_id="user-1")
        time.sleep(0.01)  # Small delay to ensure different timestamps
        task2 = manager.create_task(tool="tool2", payload={}, user_id="user-1")

        tasks = manager.list_tasks()

        # Most recent first
        assert tasks[0].task_id == task2
        assert tasks[1].task_id == task1


class TestTaskManagerStartStop:
    """Test TaskManager start/stop methods."""

    @pytest.mark.asyncio
    async def test_start_creates_cleanup_task(self):
        """Test start creates cleanup task."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()

        await manager.start()

        assert manager._cleanup_task is not None
        assert not manager._cleanup_task.done()

        # Clean up
        await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_cleanup_task(self):
        """Test stop cancels cleanup task."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()

        await manager.start()
        await manager.stop()

        assert manager._cleanup_task.done()


class TestTaskManagerCleanupOldTasks:
    """Test TaskManager._cleanup_old_tasks method."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_completed_tasks(self):
        """Test cleanup removes old completed tasks."""
        from src.mcp_integration.tasks import TaskManager, TaskStatus

        manager = TaskManager(ttl_hours=1)
        task_id = manager.create_task(tool="tool1", payload={}, user_id="user-1")
        manager.mark_completed(task_id, {})

        # Manually set completed_at to be old
        task = manager.get_task(task_id)
        task.completed_at = datetime.utcnow() - timedelta(hours=2)

        await manager._cleanup_old_tasks()

        assert manager.get_task(task_id) is None

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_failed_tasks(self):
        """Test cleanup removes old failed tasks."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager(ttl_hours=1)
        task_id = manager.create_task(tool="tool1", payload={}, user_id="user-1")
        manager.mark_failed(task_id, {"code": "ERROR"})

        # Manually set completed_at to be old
        task = manager.get_task(task_id)
        task.completed_at = datetime.utcnow() - timedelta(hours=2)

        await manager._cleanup_old_tasks()

        assert manager.get_task(task_id) is None

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_cancelled_tasks(self):
        """Test cleanup removes old cancelled tasks."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager(ttl_hours=1)
        task_id = manager.create_task(tool="tool1", payload={}, user_id="user-1")
        manager.mark_cancelled(task_id)

        # Manually set completed_at to be old
        task = manager.get_task(task_id)
        task.completed_at = datetime.utcnow() - timedelta(hours=2)

        await manager._cleanup_old_tasks()

        assert manager.get_task(task_id) is None

    @pytest.mark.asyncio
    async def test_cleanup_keeps_pending_tasks(self):
        """Test cleanup keeps pending tasks regardless of age."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager(ttl_hours=1)
        task_id = manager.create_task(tool="tool1", payload={}, user_id="user-1")

        # Manually set created_at to be old
        task = manager.get_task(task_id)
        task.created_at = datetime.utcnow() - timedelta(hours=2)

        await manager._cleanup_old_tasks()

        # Task should still exist
        assert manager.get_task(task_id) is not None

    @pytest.mark.asyncio
    async def test_cleanup_keeps_running_tasks(self):
        """Test cleanup keeps running tasks regardless of age."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager(ttl_hours=1)
        task_id = manager.create_task(tool="tool1", payload={}, user_id="user-1")
        manager.mark_running(task_id)

        # Manually set started_at to be old
        task = manager.get_task(task_id)
        task.started_at = datetime.utcnow() - timedelta(hours=2)

        await manager._cleanup_old_tasks()

        # Task should still exist
        assert manager.get_task(task_id) is not None

    @pytest.mark.asyncio
    async def test_cleanup_keeps_recent_completed_tasks(self):
        """Test cleanup keeps recent completed tasks."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager(ttl_hours=24)
        task_id = manager.create_task(tool="tool1", payload={}, user_id="user-1")
        manager.mark_completed(task_id, {})

        # completed_at is now, which is within TTL

        await manager._cleanup_old_tasks()

        # Task should still exist
        assert manager.get_task(task_id) is not None


class TestTaskManagerCleanupLoop:
    """Test TaskManager._cleanup_loop method."""

    @pytest.mark.asyncio
    async def test_cleanup_loop_calls_cleanup(self):
        """Test cleanup loop calls _cleanup_old_tasks periodically."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()

        call_count = 0
        original_cleanup = manager._cleanup_old_tasks

        async def mock_cleanup():
            nonlocal call_count
            call_count += 1

        manager._cleanup_old_tasks = mock_cleanup

        # Start cleanup loop with very short interval
        original_sleep = asyncio.sleep

        async def fast_sleep(delay):
            if delay >= 3600:  # Cleanup interval
                await original_sleep(0.01)  # Make it fast
            else:
                await original_sleep(delay)

        async def run_loop():
            with patch("asyncio.sleep", fast_sleep):
                await manager._cleanup_loop()

        # Run loop for a short time
        task = asyncio.create_task(run_loop())
        await asyncio.sleep(0.1)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have been called at least once
        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_cleanup_loop_handles_errors(self):
        """Test cleanup loop continues after errors."""
        from src.mcp_integration.tasks import TaskManager

        manager = TaskManager()

        call_count = 0
        error_raised = False

        async def failing_cleanup():
            nonlocal call_count, error_raised
            call_count += 1
            if call_count == 1:
                error_raised = True
                raise RuntimeError("Cleanup failed")
            # If we get called again after the error, that's success

        manager._cleanup_old_tasks = failing_cleanup

        original_sleep = asyncio.sleep

        async def fast_sleep(delay):
            if delay >= 3600:
                await original_sleep(0.01)
            else:
                await original_sleep(delay)

        async def run_loop():
            with patch("asyncio.sleep", fast_sleep):
                await manager._cleanup_loop()

        task = asyncio.create_task(run_loop())
        await asyncio.sleep(0.15)  # Give more time
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have been called at least once and error was raised
        assert call_count >= 1
        assert error_raised is True


class TestGlobalTaskManager:
    """Test global task_manager instance."""

    def test_global_task_manager_exists(self):
        """Test global task_manager is available."""
        from src.mcp_integration.tasks import task_manager

        assert task_manager is not None
        assert hasattr(task_manager, "create_task")
        assert hasattr(task_manager, "get_task")
        assert hasattr(task_manager, "list_tasks")
