"""
Comprehensive tests for routers/chat/endpoints/message_endpoints.py

Tests:
- POST /chat endpoint (streaming and non-streaming)
- POST /chat/{chat_id}/escalate endpoint
- ChatContext building and validation
- Handler chain delegation
- Error handling and exceptions
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

from src.routers.chat.endpoints.message_endpoints import router as message_router
from src.schemas.chat import ChatRequest, ChatResponse
from src.schemas.common import ApiResponse
from src.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    BadRequestError,
)


@pytest.fixture
def app_chat_service_mock(mock_chat_session, mock_chat_message):
    """Create a mock ChatService that tests can configure."""
    mock_chat_service = AsyncMock()
    mock_chat_service.get_or_create_session = AsyncMock(return_value=mock_chat_session)
    mock_chat_service.get_session = AsyncMock(return_value=mock_chat_session)
    mock_chat_service.add_user_message = AsyncMock(return_value=mock_chat_message)
    mock_chat_service.add_assistant_message = AsyncMock(return_value=mock_chat_message)
    return mock_chat_service


@pytest.fixture
def app(mock_settings, app_chat_service_mock):
    """Create a minimal FastAPI app for testing."""
    from src.core.config import get_settings
    from src.core.dependencies import get_chat_service, get_saptiva_client

    test_app = FastAPI()

    # Register exception handlers
    @test_app.exception_handler(AuthenticationError)
    async def auth_error_handler(request: Request, exc: AuthenticationError):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": exc.detail}
        )

    @test_app.exception_handler(ConflictError)
    async def conflict_error_handler(request: Request, exc: ConflictError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.detail}
        )

    @test_app.exception_handler(NotFoundError)
    async def not_found_error_handler(request: Request, exc: NotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.detail}
        )

    test_app.include_router(message_router)

    # Override dependencies for all tests
    test_app.dependency_overrides[get_settings] = lambda: mock_settings

    # Mock SaptivaClient to avoid database access
    mock_saptiva = AsyncMock()
    mock_saptiva.chat = AsyncMock(return_value={"content": "Test response"})
    test_app.dependency_overrides[get_saptiva_client] = lambda: mock_saptiva

    # Use the shared mock ChatService
    test_app.dependency_overrides[get_chat_service] = lambda: app_chat_service_mock

    return test_app


@pytest.fixture
def client(app):
    """FastAPI test client."""
    return TestClient(app)


@pytest.mark.unit
class TestSendChatMessage:
    """Test POST /chat endpoint"""

    @pytest.mark.asyncio
    async def test_send_chat_message_streaming_mode(
        self,
        client,
        mock_settings,
        mock_chat_streaming_request
    ):
        """Should return EventSourceResponse for streaming requests"""
        request_data = mock_chat_streaming_request.model_dump()

        with patch('src.routers.chat.endpoints.message_endpoints.StreamingHandler') as MockStreamingHandler, \
             patch('src.routers.chat.endpoints.message_endpoints.EventSourceResponse') as MockEventSource:

            # Setup streaming handler
            mock_handler = AsyncMock()
            mock_handler.handle_stream = AsyncMock()
            MockStreamingHandler.return_value = mock_handler

            # Execute
            response = client.post(
                "/chat",
                json=request_data,
                headers={"Accept": "text/event-stream"}
            )

            # Assertions - should trigger streaming handler
            MockStreamingHandler.assert_called_once()
            mock_handler.handle_stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_chat_message_handler_failure(
        self,
        client,
        mock_settings,
        mock_chat_session,
        mock_chat_message,
        mock_redis_cache
    ):
        """Should return 500 error when no handler processes message"""
        request_data = {
            "message": "Test message",
            "model": "saptiva-turbo",
            "stream": False
        }

        with patch('src.routers.chat.endpoints.message_endpoints.build_chat_context') as mock_build_ctx, \
             patch('src.routers.chat.endpoints.message_endpoints.ChatService') as MockChatService, \
             patch('src.routers.chat.endpoints.message_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.message_endpoints.SessionContextManager') as MockSessionMgr, \
             patch('src.routers.chat.endpoints.message_endpoints.create_handler_chain') as mock_chain:

            # Setup context
            mock_context = MagicMock()
            mock_context.request_id = "req-123"
            mock_context.user_id = "user-456"
            mock_context.model = "saptiva-turbo"
            mock_context.document_ids = []
            mock_context.message = "Test message"
            mock_context.chat_id = None
            mock_context.with_session = MagicMock(return_value=mock_context)

            mock_build_ctx.return_value = mock_context
            mock_get_cache.return_value = mock_redis_cache

            # Mock services
            mock_chat_service = AsyncMock()
            mock_chat_service.get_or_create_session = AsyncMock(return_value=mock_chat_session)
            mock_chat_service.add_user_message = AsyncMock(return_value=mock_chat_message)
            MockChatService.return_value = mock_chat_service

            MockSessionMgr.prepare_session_context = AsyncMock(return_value=[])

            # Handler returns None (failure)
            handler_chain = AsyncMock()
            handler_chain.handle = AsyncMock(return_value=None)
            mock_chain.return_value = handler_chain

            # Execute
            response = client.post("/chat", json=request_data)

            # Assertions
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_send_chat_message_general_exception(
        self,
        client,
        mock_settings
    ):
        """Should handle general exceptions and return 500"""
        request_data = {
            "message": "Test message",
            "model": "saptiva-turbo",
            "stream": False
        }

        with patch('src.routers.chat.endpoints.message_endpoints.build_chat_context') as mock_build_ctx:
            # Simulate exception during context building
            mock_build_ctx.side_effect = ValueError("Invalid context")

            response = client.post("/chat", json=request_data)

            # Assertions
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Chat processing failed" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_send_chat_message_invalid_model(self, client):
        """Should reject or handle requests with empty model gracefully"""
        request_data = {
            "message": "Hello",
            "model": "",
            "stream": False
        }

        # Model field is optional in schema, so empty string gets normalized or passed through
        # The endpoint should handle it gracefully - either reject it or use a default
        with patch('src.routers.chat.endpoints.message_endpoints.build_chat_context') as mock_build:
            # Simulate exception if model is invalid
            mock_build.side_effect = ValueError("Invalid or missing model")
            response = client.post("/chat", json=request_data)

            # Should return error (either 400 or 500 depending on error handling)
            assert response.status_code in [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ]

    @pytest.mark.asyncio
    async def test_send_chat_message_invalid_request_missing_message(self, client):
        """Should reject requests without message"""
        request_data = {
            "model": "saptiva-turbo",
            "stream": False
        }

        response = client.post("/chat", json=request_data)

        # Assertions - should return validation error
        assert response.status_code in [status.HTTP_422_UNPROCESSABLE_ENTITY, status.HTTP_400_BAD_REQUEST]


@pytest.mark.unit
class TestEscalateToResearch:
    """Test POST /chat/{chat_id}/escalate endpoint"""

    @pytest.mark.asyncio
    async def test_escalate_research_kill_switch_enabled(
        self,
        client,
        mock_settings,
        mock_chat_session
    ):
        """Should reject escalation when kill switch is active"""
        chat_id = "test-chat-id"
        mock_settings.deep_research_kill_switch = True

        response = client.post(f"/chat/{chat_id}/escalate")

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is False
        assert data["data"]["kill_switch_active"] is True

    @pytest.mark.asyncio
    async def test_escalate_to_research_success(
        self,
        client,
        mock_chat_session,
        mock_settings,
        app_chat_service_mock
    ):
        """Should successfully escalate conversation to research mode"""
        chat_id = "test-chat-id"
        mock_settings.deep_research_kill_switch = False
        mock_chat_session.research_escalated = False

        # Execute
        response = client.post(f"/chat/{chat_id}/escalate")

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data.get("success") is True
        # Verify service was called
        app_chat_service_mock.get_session.assert_called()

    @pytest.mark.asyncio
    async def test_escalate_research_session_not_found(
        self,
        client,
        mock_settings,
        app_chat_service_mock
    ):
        """Should return 404 when chat session not found"""
        chat_id = "nonexistent-chat"
        mock_settings.deep_research_kill_switch = False

        # Configure mock to return None for session
        app_chat_service_mock.get_session = AsyncMock(return_value=None)

        response = client.post(f"/chat/{chat_id}/escalate")

        # Assertions - endpoint should return 404 when session not found
        assert response.status_code == status.HTTP_404_NOT_FOUND
