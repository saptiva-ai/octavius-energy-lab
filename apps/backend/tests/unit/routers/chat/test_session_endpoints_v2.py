"""
Comprehensive tests for routers/chat/endpoints/session_endpoints.py

Tests:
- GET /sessions endpoint with pagination
- GET /sessions/{session_id}/research endpoint
- PATCH /sessions/{chat_id} endpoint
- DELETE /sessions/{chat_id} endpoint
- Permission checks and cache invalidation
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from fastapi import FastAPI, status, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
import sys
import os

# Ensure proper imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..', 'src'))

from src.routers.chat.endpoints.session_endpoints import router as session_router
from src.schemas.chat import ChatSessionListResponse, ChatSessionUpdateRequest
from src.schemas.common import ApiResponse
from src.core.exceptions import (
    AuthenticationError,
    NotFoundError,
)


@pytest.fixture
def app():
    """Create a minimal FastAPI app for testing."""
    test_app = FastAPI()

    # Register exception handlers
    @test_app.exception_handler(AuthenticationError)
    async def auth_error_handler(request: Request, exc: AuthenticationError):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": exc.detail}
        )

    @test_app.exception_handler(NotFoundError)
    async def not_found_error_handler(request: Request, exc: NotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.detail}
        )

    test_app.include_router(session_router)
    return test_app


@pytest.fixture
def client(app):
    """FastAPI test client."""
    return TestClient(app)


@pytest.mark.unit
class TestGetChatSessions:
    """Test GET /sessions endpoint"""

    @pytest.mark.asyncio
    async def test_get_chat_sessions_empty(self, client):
        """Should return empty list when user has no sessions"""
        with patch('src.routers.chat.endpoints.session_endpoints.HistoryService') as MockHistoryService:
            # Setup
            MockHistoryService.get_chat_sessions = AsyncMock(return_value={
                "sessions": [],
                "total_count": 0,
                "has_more": False
            })

            # Execute
            response = client.get("/sessions")

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert len(data["sessions"]) == 0
            assert data["total_count"] == 0

    @pytest.mark.parametrize("limit,offset", [(10, 0), (20, 10), (50, 50)])
    @pytest.mark.asyncio
    async def test_get_chat_sessions_different_pagination(
        self,
        limit,
        offset,
        client
    ):
        """Should handle various pagination parameters"""
        with patch('src.routers.chat.endpoints.session_endpoints.HistoryService') as MockHistoryService:
            # Setup
            MockHistoryService.get_chat_sessions = AsyncMock(return_value={
                "sessions": [],
                "total_count": 100,
                "has_more": True
            })

            # Execute
            response = client.get(f"/sessions?limit={limit}&offset={offset}")

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            call_kwargs = MockHistoryService.get_chat_sessions.call_args[1]
            assert call_kwargs["limit"] == limit
            assert call_kwargs["offset"] == offset

    @pytest.mark.asyncio
    async def test_get_chat_sessions_service_error(self, client):
        """Should handle service errors gracefully"""
        with patch('src.routers.chat.endpoints.session_endpoints.HistoryService') as MockHistoryService:
            # Setup - service error
            MockHistoryService.get_chat_sessions = AsyncMock(
                side_effect=Exception("Database error")
            )

            # Execute
            response = client.get("/sessions")

            # Assertions
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Failed to retrieve chat sessions" in response.json()["detail"]


@pytest.mark.unit
class TestGetSessionResearchTasks:
    """Test GET /sessions/{session_id}/research endpoint"""

    @pytest.mark.asyncio
    async def test_get_research_tasks_cached(
        self,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should return cached research tasks"""
        session_id = "test-session-123"
        cached_data = {
            "tasks": [{"task_id": "task-1", "status": "completed"}],
            "total_count": 1,
            "has_more": False
        }

        with patch('src.routers.chat.endpoints.session_endpoints.HistoryService') as MockHistoryService, \
             patch('src.routers.chat.endpoints.session_endpoints.get_redis_cache') as mock_get_cache:

            # Setup
            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )
            mock_redis_cache.get_research_tasks = AsyncMock(return_value=cached_data)
            mock_get_cache.return_value = mock_redis_cache

            # Execute
            response = client.get(f"/sessions/{session_id}/research")

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data == cached_data
            # Should not call database when cache hit
            mock_redis_cache.get_research_tasks.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_research_tasks_unauthorized(self, client):
        """Should return 404 when user doesn't have access to session"""
        session_id = "unauthorized-session"

        with patch('src.routers.chat.endpoints.session_endpoints.HistoryService') as MockHistoryService:
            # Setup - permission denied (HistoryService raises HTTPException with 404)
            from fastapi import HTTPException
            MockHistoryService.get_session_with_permission_check = AsyncMock(
                side_effect=HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat session not found"
                )
            )

            # Execute
            response = client.get(f"/sessions/{session_id}/research")

            # Assertions
            assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.unit
class TestUpdateChatSession:
    """Test PATCH /sessions/{chat_id} endpoint"""

    @pytest.mark.asyncio
    async def test_update_session_title(
        self,
        client,
        mock_chat_session
    ):
        """Should update session title"""
        chat_id = "test-chat-id"
        new_title = "Updated Chat Title"

        with patch('src.routers.chat.endpoints.session_endpoints.HistoryService') as MockHistoryService:
            # Setup
            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )

            # Execute
            response = client.patch(
                f"/sessions/{chat_id}",
                json={"title": new_title}
            )

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert "title" in data["data"]["updated_fields"]
            mock_chat_session.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_session_pinned_status(
        self,
        client,
        mock_chat_session
    ):
        """Should update session pinned status"""
        chat_id = "test-chat-id"

        with patch('src.routers.chat.endpoints.session_endpoints.HistoryService') as MockHistoryService:
            # Setup
            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )

            # Execute
            response = client.patch(
                f"/sessions/{chat_id}",
                json={"pinned": True}
            )

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert "pinned" in data["data"]["updated_fields"]

    @pytest.mark.asyncio
    async def test_update_session_no_changes(
        self,
        client,
        mock_chat_session
    ):
        """Should handle update request with no changes"""
        chat_id = "test-chat-id"

        with patch('src.routers.chat.endpoints.session_endpoints.HistoryService') as MockHistoryService:
            # Setup
            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )

            # Execute - empty update
            response = client.patch(
                f"/sessions/{chat_id}",
                json={}
            )

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True

    @pytest.mark.asyncio
    async def test_update_session_service_error(
        self,
        client,
        mock_chat_session
    ):
        """Should handle service errors during update"""
        chat_id = "test-chat-id"

        with patch('src.routers.chat.endpoints.session_endpoints.HistoryService') as MockHistoryService:
            # Setup
            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )
            mock_chat_session.update = AsyncMock(side_effect=Exception("DB error"))

            # Execute
            response = client.patch(
                f"/sessions/{chat_id}",
                json={"title": "New Title"}
            )

            # Assertions
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.unit
class TestDeleteChatSession:
    """Test DELETE /sessions/{chat_id} endpoint"""

    @pytest.mark.asyncio
    async def test_delete_session_success(
        self,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should successfully delete session and all messages"""
        chat_id = "test-chat-id"

        with patch('src.routers.chat.endpoints.session_endpoints.HistoryService') as MockHistoryService, \
             patch('src.routers.chat.endpoints.session_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.session_endpoints.ChatMessageModel') as MockMessageModel:

            # Setup
            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )
            mock_get_cache.return_value = mock_redis_cache

            # Mock message deletion
            query = AsyncMock()
            query.find = AsyncMock(return_value=query)
            query.delete = AsyncMock()
            MockMessageModel.find = MagicMock(return_value=query)

            # Execute
            response = client.delete(f"/sessions/{chat_id}")

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert "deleted" in data["message"].lower()

            # Verify operations
            mock_chat_session.delete.assert_called_once()
            mock_redis_cache.invalidate_all_for_chat.assert_called_once_with(chat_id)

    @pytest.mark.asyncio
    async def test_delete_session_service_error(
        self,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should handle errors during deletion"""
        chat_id = "test-chat-id"

        with patch('src.routers.chat.endpoints.session_endpoints.HistoryService') as MockHistoryService, \
             patch('src.routers.chat.endpoints.session_endpoints.get_redis_cache') as mock_get_cache:

            # Setup
            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )
            mock_get_cache.return_value = mock_redis_cache
            mock_chat_session.delete = AsyncMock(side_effect=Exception("DB error"))

            # Execute
            response = client.delete(f"/sessions/{chat_id}")

            # Assertions
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Failed to delete chat session" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_session_cache_invalidation(
        self,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should properly invalidate all caches for deleted session"""
        chat_id = "test-chat-id-with-cache"

        with patch('src.routers.chat.endpoints.session_endpoints.HistoryService') as MockHistoryService, \
             patch('src.routers.chat.endpoints.session_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.session_endpoints.ChatMessageModel') as MockMessageModel:

            # Setup
            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )
            mock_get_cache.return_value = mock_redis_cache

            query = AsyncMock()
            query.find = AsyncMock(return_value=query)
            query.delete = AsyncMock()
            MockMessageModel.find = MagicMock(return_value=query)

            # Execute
            response = client.delete(f"/sessions/{chat_id}")

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            # Verify cache was invalidated
            mock_redis_cache.invalidate_all_for_chat.assert_called_once_with(chat_id)
