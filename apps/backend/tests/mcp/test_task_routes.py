"""
Unit tests for MCP task management routes.

Tests the 202 Accepted pattern:
- POST /api/mcp/tasks - Submit long-running task
- GET /api/mcp/tasks/{task_id} - Poll task status
- DELETE /api/mcp/tasks/{task_id} - Cancel task
- GET /api/mcp/tasks - List tasks
"""

import os
import pytest

# Mark all tests in this file with mcp and mcp_tasks markers
pytestmark = [
    pytest.mark.mcp,
    pytest.mark.mcp_tasks,
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_MCP_TASK_ROUTES", "false").lower() != "true",
        reason="MCP task routes deshabilitados por defecto (establece RUN_MCP_TASK_ROUTES=true para habilitar).",
    ),
]
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
from fastmcp import FastMCP

from src.mcp_integration.fastapi_adapter import MCPFastAPIAdapter
from src.mcp_integration.tasks import TaskManager, TaskStatus, TaskPriority
from src.models.user import User


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    user = Mock(spec=User)
    user.id = "user_123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_auth_dependency(mock_user):
    """Mock auth dependency that returns test user."""
    async def _auth():
        return mock_user
    return _auth


@pytest.fixture
def mcp_server():
    """Create a FastMCP server with test tools."""
    mcp = FastMCP("Test MCP")

    @mcp.tool()
    async def slow_tool(value: str) -> dict:
        """A slow tool for testing async execution."""
        import asyncio
        await asyncio.sleep(2)  # Simulate slow operation
        return {"result": f"processed: {value}"}

    @mcp.tool()
    async def fast_tool(value: str) -> dict:
        """A fast tool for testing sync execution."""
        return {"result": f"fast: {value}"}

    return mcp


@pytest.fixture
def adapter(mcp_server, mock_auth_dependency):
    """Create adapter with test MCP server."""
    return MCPFastAPIAdapter(
        mcp_server=mcp_server,
        auth_dependency=mock_auth_dependency,
    )


@pytest.fixture
def test_app(adapter):
    """Create test FastAPI app with MCP router."""
    app = FastAPI()
    app.include_router(adapter.create_router())
    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


@pytest.fixture
def task_manager():
    """Create a fresh task manager for each test."""
    from src.mcp_integration.tasks import TaskManager
    manager = TaskManager(ttl_hours=1)
    return manager


class TestCreateTask:
    """Test POST /api/mcp/tasks endpoint."""

    def test_create_task_returns_202(self, client):
        """Test creating a task returns 202 Accepted."""
        response = client.post(
            "/mcp/tasks",
            json={
                "tool": "slow_tool",
                "payload": {"value": "test"},
            },
        )

        assert response.status_code == 202
        data = response.json()

        assert "task_id" in data
        assert data["status"] == "pending"
        assert "poll_url" in data
        assert "cancel_url" in data
        assert "estimated_duration_ms" in data

    def test_create_task_with_priority(self, client):
        """Test creating a task with priority."""
        response = client.post(
            "/mcp/tasks",
            json={
                "tool": "slow_tool",
                "payload": {"value": "test"},
                "priority": "high",
            },
        )

        assert response.status_code == 202

    def test_create_task_missing_tool(self, client):
        """Test creating a task without tool name."""
        response = client.post(
            "/mcp/tasks",
            json={
                "payload": {"value": "test"},
            },
        )

        assert response.status_code == 400
        assert "tool" in response.json()["detail"].lower()

    def test_create_task_nonexistent_tool(self, client):
        """Test creating a task for nonexistent tool."""
        response = client.post(
            "/mcp/tasks",
            json={
                "tool": "nonexistent_tool",
                "payload": {},
            },
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestGetTaskStatus:
    """Test GET /api/mcp/tasks/{task_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_task_status_pending(self, client, task_manager, mock_user):
        """Test getting status of pending task."""
        # Create a task directly via task manager
        task_id = task_manager.create_task(
            tool="slow_tool",
            payload={"value": "test"},
            user_id=str(mock_user.id),
        )

        # Patch the global task_manager
        with patch("src.mcp_integration.fastapi_adapter.task_manager", task_manager):
            response = client.get(f"/mcp/tasks/{task_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["task_id"] == task_id
        assert data["tool"] == "slow_tool"
        assert data["status"] == "pending"
        assert data["progress"] == 0.0
        assert data["result"] is None
        assert data["error"] is None

    @pytest.mark.asyncio
    async def test_get_task_status_completed(self, client, task_manager, mock_user):
        """Test getting status of completed task."""
        task_id = task_manager.create_task(
            tool="slow_tool",
            payload={"value": "test"},
            user_id=str(mock_user.id),
        )

        # Mark as completed
        task_manager.mark_running(task_id)
        task_manager.mark_completed(task_id, {"result": "success"})

        with patch("src.mcp_integration.fastapi_adapter.task_manager", task_manager):
            response = client.get(f"/mcp/tasks/{task_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "completed"
        assert data["progress"] == 1.0
        assert data["result"] == {"result": "success"}

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, client):
        """Test getting status of nonexistent task."""
        response = client.get("/mcp/tasks/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_task_status_wrong_user(self, client, task_manager):
        """Test getting status of another user's task."""
        task_id = task_manager.create_task(
            tool="slow_tool",
            payload={"value": "test"},
            user_id="other_user",  # Different user
        )

        with patch("src.mcp_integration.fastapi_adapter.task_manager", task_manager):
            response = client.get(f"/mcp/tasks/{task_id}")

        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"].lower()


class TestCancelTask:
    """Test DELETE /api/mcp/tasks/{task_id} endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_task_pending(self, client, task_manager, mock_user):
        """Test cancelling a pending task."""
        task_id = task_manager.create_task(
            tool="slow_tool",
            payload={"value": "test"},
            user_id=str(mock_user.id),
        )

        with patch("src.mcp_integration.fastapi_adapter.task_manager", task_manager):
            response = client.delete(f"/mcp/tasks/{task_id}")

        assert response.status_code == 202
        data = response.json()

        assert data["task_id"] == task_id
        assert data["status"] == "cancellation_requested"

        # Verify cancellation was requested
        assert task_manager.is_cancellation_requested(task_id) is True

    @pytest.mark.asyncio
    async def test_cancel_task_running(self, client, task_manager, mock_user):
        """Test cancelling a running task."""
        task_id = task_manager.create_task(
            tool="slow_tool",
            payload={"value": "test"},
            user_id=str(mock_user.id),
        )

        task_manager.mark_running(task_id)

        with patch("src.mcp_integration.fastapi_adapter.task_manager", task_manager):
            response = client.delete(f"/mcp/tasks/{task_id}")

        assert response.status_code == 202
        assert task_manager.is_cancellation_requested(task_id) is True

    @pytest.mark.asyncio
    async def test_cancel_task_completed(self, client, task_manager, mock_user):
        """Test cancelling a completed task (should fail)."""
        task_id = task_manager.create_task(
            tool="slow_tool",
            payload={"value": "test"},
            user_id=str(mock_user.id),
        )

        task_manager.mark_running(task_id)
        task_manager.mark_completed(task_id, {"result": "success"})

        with patch("src.mcp_integration.fastapi_adapter.task_manager", task_manager):
            response = client.delete(f"/mcp/tasks/{task_id}")

        assert response.status_code == 202
        data = response.json()

        assert data["status"] == "completed"
        assert "terminal state" in data["message"]

    @pytest.mark.asyncio
    async def test_cancel_task_not_found(self, client):
        """Test cancelling nonexistent task."""
        response = client.delete("/mcp/tasks/nonexistent")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_task_wrong_user(self, client, task_manager):
        """Test cancelling another user's task."""
        task_id = task_manager.create_task(
            tool="slow_tool",
            payload={"value": "test"},
            user_id="other_user",
        )

        with patch("src.mcp_integration.fastapi_adapter.task_manager", task_manager):
            response = client.delete(f"/mcp/tasks/{task_id}")

        assert response.status_code == 403


class TestListTasks:
    """Test GET /api/mcp/tasks endpoint."""

    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, client):
        """Test listing tasks when none exist."""
        response = client.get("/mcp/tasks")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        # May be empty or contain tasks from other tests

    @pytest.mark.asyncio
    async def test_list_tasks_with_tasks(self, client, task_manager, mock_user):
        """Test listing tasks for current user."""
        # Create multiple tasks
        task_id_1 = task_manager.create_task(
            tool="slow_tool",
            payload={"value": "test1"},
            user_id=str(mock_user.id),
        )

        task_id_2 = task_manager.create_task(
            tool="fast_tool",
            payload={"value": "test2"},
            user_id=str(mock_user.id),
        )

        # Create task for other user
        task_manager.create_task(
            tool="slow_tool",
            payload={"value": "test3"},
            user_id="other_user",
        )

        with patch("src.mcp_integration.fastapi_adapter.task_manager", task_manager):
            response = client.get("/mcp/tasks")

        assert response.status_code == 200
        data = response.json()

        # Should only return current user's tasks
        assert len(data) == 2
        task_ids = [t["task_id"] for t in data]
        assert task_id_1 in task_ids
        assert task_id_2 in task_ids

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_status(self, client, task_manager, mock_user):
        """Test listing tasks filtered by status."""
        # Create tasks with different statuses
        task_id_pending = task_manager.create_task(
            tool="slow_tool",
            payload={"value": "test1"},
            user_id=str(mock_user.id),
        )

        task_id_completed = task_manager.create_task(
            tool="slow_tool",
            payload={"value": "test2"},
            user_id=str(mock_user.id),
        )
        task_manager.mark_running(task_id_completed)
        task_manager.mark_completed(task_id_completed, {"result": "done"})

        with patch("src.mcp_integration.fastapi_adapter.task_manager", task_manager):
            # Filter for completed tasks
            response = client.get("/mcp/tasks?status=completed")

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 1
        assert data[0]["task_id"] == task_id_completed
        assert data[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_tool(self, client, task_manager, mock_user):
        """Test listing tasks filtered by tool."""
        task_manager.create_task(
            tool="slow_tool",
            payload={"value": "test1"},
            user_id=str(mock_user.id),
        )

        task_id_fast = task_manager.create_task(
            tool="fast_tool",
            payload={"value": "test2"},
            user_id=str(mock_user.id),
        )

        with patch("src.mcp_integration.fastapi_adapter.task_manager", task_manager):
            response = client.get("/mcp/tasks?tool=fast_tool")

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 1
        assert data[0]["task_id"] == task_id_fast
        assert data[0]["tool"] == "fast_tool"

    @pytest.mark.asyncio
    async def test_list_tasks_invalid_status(self, client):
        """Test listing tasks with invalid status filter."""
        response = client.get("/mcp/tasks?status=invalid")

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()


class TestTaskExecution:
    """Test background task execution."""

    @pytest.mark.asyncio
    async def test_task_execution_success(self, adapter, mock_user, task_manager):
        """Test successful background task execution."""
        import asyncio

        # Patch task_manager globally
        with patch("src.mcp_integration.fastapi_adapter.task_manager", task_manager):
            task_id = "test_task_123"
            task_manager.create_task(
                tool="fast_tool",
                payload={"value": "test"},
                user_id=str(mock_user.id),
            )

            # Execute task
            await adapter._execute_task(task_id, "fast_tool", {"value": "test"}, mock_user)

        # Verify task completed
        task = task_manager.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED
        assert task.result == {"result": "fast: test"}

    @pytest.mark.asyncio
    async def test_task_execution_validation_error(self, adapter, mock_user, task_manager):
        """Test task execution with validation error."""
        with patch("src.mcp_integration.fastapi_adapter.task_manager", task_manager):
            task_id = task_manager.create_task(
                tool="fast_tool",
                payload={},  # Missing required 'value' field
                user_id=str(mock_user.id),
            )

            await adapter._execute_task(task_id, "fast_tool", {}, mock_user)

        task = task_manager.get_task(task_id)
        assert task.status == TaskStatus.FAILED
        assert task.error["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_task_execution_with_cancellation(self, adapter, mock_user, task_manager):
        """Test task execution with cancellation."""
        with patch("src.mcp_integration.fastapi_adapter.task_manager", task_manager):
            task_id = task_manager.create_task(
                tool="slow_tool",
                payload={"value": "test"},
                user_id=str(mock_user.id),
            )

            # Request cancellation immediately
            task_manager.request_cancellation(task_id)

            await adapter._execute_task(task_id, "slow_tool", {"value": "test"}, mock_user)

        task = task_manager.get_task(task_id)
        # Task should be cancelled after completion check
        assert task.status in [TaskStatus.CANCELLED, TaskStatus.COMPLETED]
