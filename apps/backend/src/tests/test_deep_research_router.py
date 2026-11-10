"""
Tests for deep research API endpoints.

NOTE: These tests are skipped in CI because they require complex middleware mocking
and external dependencies (Aletheia, TaskModel/MongoDB). They should be tested via
integration/E2E tests instead.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ..main import app
from ..models.task import TaskStatus

pytestmark = pytest.mark.skip(
    reason="Deep research tests require integration test setup with MongoDB and Aletheia"
)


async def mock_auth_dispatch(self, request, call_next):
    """Mock authentication middleware dispatch for testing."""
    # Inject mock user into request state
    request.state.user_id = "test-user-123"
    request.state.authenticated = True
    request.state.user_claims = {
        "sub": "test-user-123",
        "username": "test_user",
        "email": "test@example.com",
    }
    return await call_next(request)


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_auth_user():
    """Mock authenticated user."""
    return {
        "user_id": "test-user-123",
        "username": "test_user",
        "email": "test@example.com",
    }


@pytest.fixture
def valid_research_request():
    """Valid deep research request payload."""
    return {
        "query": "¿Cuál es el impacto de la IA en LATAM 2024?",
        "research_type": "deep_research",
        "stream": True,
        "params": {
            "depth_level": "medium",
            "scope": "Impact analysis of AI in Latin America",
            "max_iterations": 3,
        },
        "context": {"time_window": "2024", "origin": "test"},
    }


class TestDeepResearchEndpoints:
    """Test cases for deep research endpoints."""

    @patch("apps.api.src.routers.deep_research.TaskModel")
    @patch("apps.api.src.routers.deep_research.get_aletheia_client")
    @pytest.mark.asyncio
    async def test_start_deep_research_success(
        self,
        mock_aletheia_client,
        mock_task_model,
        client,
        valid_research_request,
        mock_auth_user,
    ):
        """Test successful deep research initiation."""
        # Mock task creation
        mock_task = MagicMock()
        mock_task.id = "task-123"
        mock_task.insert = AsyncMock()
        mock_task.save = AsyncMock()
        mock_task_model.return_value = mock_task

        # Mock Aletheia client response
        mock_aletheia = AsyncMock()
        mock_aletheia.start_deep_research.return_value = MagicMock(status="accepted")
        mock_aletheia_client.return_value = mock_aletheia

        # Mock authentication middleware
        with patch(
            "apps.api.src.middleware.auth.AuthMiddleware.dispatch",
            new=mock_auth_dispatch,
        ):
            response = client.post(
                "/api/deep-research",
                json=valid_research_request,
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "task_id" in data
        assert data["status"] == TaskStatus.RUNNING.value
        assert data["stream_url"] is not None
        assert "stream" in data["stream_url"]

    @pytest.mark.asyncio
    async def test_start_deep_research_unauthorized(
        self, client, valid_research_request
    ):
        """Test deep research without authentication."""
        response = client.post("/api/deep-research", json=valid_research_request)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_start_deep_research_invalid_payload(self, client, mock_auth_user):
        """Test deep research with invalid payload."""
        invalid_request = {
            "query": "",  # Empty query should fail validation
            "research_type": "invalid_type",
        }

        with patch(
            "apps.api.src.middleware.auth.AuthMiddleware.dispatch",
            new=mock_auth_dispatch,
        ):
            response = client.post(
                "/api/deep-research",
                json=invalid_request,
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @patch("apps.api.src.routers.deep_research.TaskModel")
    @pytest.mark.asyncio
    async def test_get_research_status_success(
        self, mock_task_model, client, mock_auth_user
    ):
        """Test successful research status retrieval."""
        # Mock task
        mock_task = MagicMock()
        mock_task.id = "task-123"
        mock_task.user_id = mock_auth_user["user_id"]
        mock_task.status = TaskStatus.RUNNING
        mock_task.created_at = "2024-01-01T00:00:00Z"
        mock_task.input_data = {"query": "test query", "stream": True}
        mock_task_model.get.return_value = mock_task

        with patch(
            "apps.api.src.middleware.auth.AuthMiddleware.dispatch",
            new=mock_auth_dispatch,
        ):
            response = client.get(
                "/api/deep-research/task-123",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["task_id"] == "task-123"
        assert data["status"] == TaskStatus.RUNNING.value

    @patch("apps.api.src.routers.deep_research.TaskModel")
    @pytest.mark.asyncio
    async def test_get_research_status_not_found(
        self, mock_task_model, client, mock_auth_user
    ):
        """Test research status for non-existent task."""
        mock_task_model.get.return_value = None

        with patch(
            "apps.api.src.middleware.auth.AuthMiddleware.dispatch",
            new=mock_auth_dispatch,
        ):
            response = client.get(
                "/api/deep-research/nonexistent-task",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("apps.api.src.routers.deep_research.TaskModel")
    @pytest.mark.asyncio
    async def test_cancel_research_task_success(
        self, mock_task_model, client, mock_auth_user
    ):
        """Test successful research task cancellation."""
        # Mock task
        mock_task = MagicMock()
        mock_task.id = "task-123"
        mock_task.user_id = mock_auth_user["user_id"]
        mock_task.status = TaskStatus.RUNNING
        mock_task.save = AsyncMock()
        mock_task_model.get.return_value = mock_task

        cancel_request = {"reason": "User cancelled"}

        with patch(
            "apps.api.src.middleware.auth.AuthMiddleware.dispatch",
            new=mock_auth_dispatch,
        ):
            response = client.post(
                "/api/deep-research/task-123/cancel",
                json=cancel_request,
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "cancelled" in data["message"].lower()

    @patch("apps.api.src.routers.deep_research.TaskModel")
    @pytest.mark.asyncio
    async def test_cancel_already_completed_task(
        self, mock_task_model, client, mock_auth_user
    ):
        """Test cancelling an already completed task."""
        # Mock completed task
        mock_task = MagicMock()
        mock_task.id = "task-123"
        mock_task.user_id = mock_auth_user["user_id"]
        mock_task.status = TaskStatus.COMPLETED
        mock_task_model.get.return_value = mock_task

        cancel_request = {"reason": "User cancelled"}

        with patch(
            "apps.api.src.middleware.auth.AuthMiddleware.dispatch",
            new=mock_auth_dispatch,
        ):
            response = client.post(
                "/api/deep-research/task-123/cancel",
                json=cancel_request,
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
