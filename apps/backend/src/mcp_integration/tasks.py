"""
MCP Task Management - Long-running tool execution with cancellation.

Handles:
- Task queue for expensive operations
- 202 Accepted pattern for long-running tools
- Cancellation tokens
- Progress tracking
- Result persistence

Architecture:
- In-memory queue for MVP (can be replaced with Redis/RQ/Celery)
- Task states: PENDING → RUNNING → COMPLETED | FAILED | CANCELLED
- Automatic cleanup after TTL
"""

import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Task priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class Task(BaseModel):
    """Task representation."""

    task_id: str
    tool: str
    payload: Dict[str, Any]
    status: TaskStatus
    priority: TaskPriority = TaskPriority.NORMAL
    user_id: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: float = 0.0  # 0.0 to 1.0
    progress_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    cancellation_requested: bool = False


class TaskManager:
    """
    Manages long-running MCP tasks.

    Features:
    - In-memory task queue (MVP - can upgrade to Redis/RQ)
    - Cancellation support
    - Progress tracking
    - Automatic cleanup after TTL
    """

    def __init__(self, ttl_hours: int = 24):
        """
        Initialize task manager.

        Args:
            ttl_hours: Task TTL in hours (default: 24)
        """
        self.tasks: Dict[str, Task] = {}
        self.ttl = timedelta(hours=ttl_hours)
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Task manager started")

    async def stop(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Task manager stopped")

    def create_task(
        self,
        tool: str,
        payload: Dict[str, Any],
        user_id: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        task_id: Optional[str] = None,
    ) -> str:
        """
        Create a new task.

        Args:
            tool: Tool name
            payload: Tool input
            user_id: User ID
            priority: Task priority

        Args:
            tool: Tool name
            payload: Tool input
            user_id: User ID
            priority: Task priority
            task_id: Optional explicit task ID (for testing / idempotency)

        Returns:
            Task ID
        """
        task_id = task_id or str(uuid4())

        task = Task(
            task_id=task_id,
            tool=tool,
            payload=payload,
            status=TaskStatus.PENDING,
            priority=priority,
            user_id=user_id,
            created_at=datetime.utcnow(),
        )

        self.tasks[task_id] = task

        logger.info(
            "Task created",
            task_id=task_id,
            tool=tool,
            priority=priority.value,
            user_id=user_id,
        )

        return task_id

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self.tasks.get(task_id)

    def update_progress(
        self,
        task_id: str,
        progress: float,
        message: Optional[str] = None,
    ):
        """
        Update task progress.

        Args:
            task_id: Task ID
            progress: Progress (0.0 to 1.0)
            message: Optional progress message
        """
        task = self.tasks.get(task_id)
        if task:
            task.progress = max(0.0, min(1.0, progress))
            if message:
                task.progress_message = message

            logger.debug(
                "Task progress updated",
                task_id=task_id,
                progress=progress,
                message=message,
            )

    def mark_running(self, task_id: str):
        """Mark task as running."""
        task = self.tasks.get(task_id)
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()

            logger.info("Task started", task_id=task_id, tool=task.tool)

    def mark_completed(
        self,
        task_id: str,
        result: Dict[str, Any],
    ):
        """Mark task as completed with result."""
        task = self.tasks.get(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            task.progress = 1.0
            task.result = result

            duration_ms = (
                (task.completed_at - task.started_at).total_seconds() * 1000
                if task.started_at
                else 0
            )

            logger.info(
                "Task completed",
                task_id=task_id,
                tool=task.tool,
                duration_ms=duration_ms,
            )

    def mark_failed(
        self,
        task_id: str,
        error: Dict[str, Any],
    ):
        """Mark task as failed with error."""
        task = self.tasks.get(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.utcnow()
            task.error = error

            logger.error(
                "Task failed",
                task_id=task_id,
                tool=task.tool,
                error_code=error.get("code"),
            )

    def request_cancellation(self, task_id: str) -> bool:
        """
        Request task cancellation.

        Returns:
            True if cancellation requested, False if task not found/already completed
        """
        task = self.tasks.get(task_id)
        if not task:
            return False

        if task.status in [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ]:
            logger.warning(
                "Cannot cancel task in terminal state",
                task_id=task_id,
                status=task.status.value,
            )
            return False

        task.cancellation_requested = True

        logger.info("Task cancellation requested", task_id=task_id, tool=task.tool)

        return True

    def mark_cancelled(self, task_id: str):
        """Mark task as cancelled."""
        task = self.tasks.get(task_id)
        if task:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.utcnow()

            logger.info("Task cancelled", task_id=task_id, tool=task.tool)

    def is_cancellation_requested(self, task_id: str) -> bool:
        """Check if cancellation was requested for this task."""
        task = self.tasks.get(task_id)
        return task.cancellation_requested if task else False

    def list_tasks(
        self,
        user_id: Optional[str] = None,
        tool: Optional[str] = None,
        status: Optional[TaskStatus] = None,
    ) -> list[Task]:
        """
        List tasks with optional filters.

        Args:
            user_id: Filter by user
            tool: Filter by tool name
            status: Filter by status

        Returns:
            List of tasks
        """
        tasks = list(self.tasks.values())

        if user_id:
            tasks = [t for t in tasks if t.user_id == user_id]

        if tool:
            tasks = [t for t in tasks if t.tool == tool]

        if status:
            tasks = [t for t in tasks if t.status == status]

        # Sort by created_at descending
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        return tasks

    async def _cleanup_loop(self):
        """Background task to cleanup old completed tasks."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                await self._cleanup_old_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Cleanup loop error", error=str(e), exc_info=True)

    async def _cleanup_old_tasks(self):
        """Remove tasks older than TTL."""
        now = datetime.utcnow()
        to_remove = []

        for task_id, task in self.tasks.items():
            if task.status in [
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            ]:
                age = now - (task.completed_at or task.created_at)
                if age > self.ttl:
                    to_remove.append(task_id)

        for task_id in to_remove:
            del self.tasks[task_id]

        if to_remove:
            logger.info("Cleaned up old tasks", count=len(to_remove))


# Global task manager instance
task_manager = TaskManager()
