"""
Comprehensive tests for routers/chat/endpoints/history_endpoints.py

Tests:
- GET /history/{chat_id} endpoint
- Research task enrichment
- Cache hits and misses
- Pagination and filtering
- Permission checks
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch, MagicMock, PropertyMock
from fastapi import FastAPI, status, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
import sys
import os

# Ensure proper imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..', 'src'))

from src.routers.chat.endpoints.history_endpoints import router as history_router
from src.schemas.chat import ChatHistoryResponse, ChatMessage
from src.models.chat import MessageRole, MessageStatus, ChatMessage as ChatMessageModel
from src.core.exceptions import NotFoundError
from .conftest import MockBeanieQueryBuilder


@pytest.fixture
def app():
    """Create a minimal FastAPI app for testing."""
    test_app = FastAPI()

    # Register exception handlers
    @test_app.exception_handler(NotFoundError)
    async def not_found_error_handler(request: Request, exc: NotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": exc.detail}
        )

    test_app.include_router(history_router)
    return test_app


@pytest.fixture
def client(app):
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_chat_messages():
    """Create mock chat messages."""
    msg1 = MagicMock()
    msg1.id = "msg-1"
    msg1.chat_id = "chat-123"
    msg1.role = MessageRole.USER
    msg1.content = "Hello, assistant!"
    msg1.status = MessageStatus.DELIVERED
    msg1.created_at = datetime.utcnow()
    msg1.updated_at = datetime.utcnow()
    msg1.metadata = {"source": "web"}
    msg1.model = None
    msg1.tokens = 5
    msg1.latency_ms = 0
    msg1.task_id = None

    msg2 = MagicMock()
    msg2.id = "msg-2"
    msg2.chat_id = "chat-123"
    msg2.role = MessageRole.ASSISTANT
    msg2.content = "Hello! How can I help you?"
    msg2.status = MessageStatus.DELIVERED
    msg2.created_at = datetime.utcnow()
    msg2.updated_at = datetime.utcnow()
    msg2.metadata = {}
    msg2.model = "saptiva-turbo"
    msg2.tokens = 10
    msg2.latency_ms = 250
    msg2.task_id = None

    return [msg1, msg2]


@pytest.mark.unit
class TestGetChatHistory:
    """Test GET /history/{chat_id} endpoint"""

    @pytest.mark.asyncio
    async def test_get_chat_history_cached(
        self,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should return cached history when available"""
        chat_id = "test-chat-123"
        cached_data = {
            "chat_id": chat_id,
            "messages": [
                {
                    "id": "msg-1",
                    "chat_id": chat_id,
                    "role": "user",
                    "content": "Hello",
                    "status": "delivered",
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "metadata": {},
                    "model": None,
                    "tokens": 5,
                    "latency_ms": 0,
                    "task_id": None
                }
            ],
            "total_count": 1,
            "has_more": False
        }

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache:
            # Setup
            mock_redis_cache = AsyncMock()
            mock_redis_cache.get_chat_history = AsyncMock(return_value=cached_data)
            mock_get_cache.return_value = mock_redis_cache

            # Execute
            response = client.get(f"/history/{chat_id}")

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            # Should not call permission check when cache hits
            mock_redis_cache.get_chat_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_chat_history_service_error(
        self,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should handle service errors gracefully"""
        chat_id = "test-chat-123"

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.history_endpoints.HistoryService') as MockHistoryService:

            # Setup
            mock_get_cache.return_value = mock_redis_cache
            mock_redis_cache.get_chat_history = AsyncMock(return_value=None)

            MockHistoryService.get_session_with_permission_check = AsyncMock(
                side_effect=Exception("Database error")
            )

            # Execute
            response = client.get(f"/history/{chat_id}")

            # Assertions
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Failed to retrieve chat history" in response.json()["detail"]

    @pytest.mark.parametrize("limit,offset", [(10, 0), (25, 10), (50, 50)])
    @pytest.mark.asyncio
    async def test_get_chat_history_pagination(
        self,
        limit,
        offset,
        client,
        mock_chat_session,
        mock_redis_cache,
        mock_chat_messages
    ):
        """Should respect limit and offset parameters"""
        chat_id = "test-chat-123"

        # Create 100 mock messages for testing pagination
        # Use Mock without spec to allow flexible attribute access
        mock_messages = []
        for i in range(100):
            created_at = datetime.utcnow()
            updated_at = datetime.utcnow()
            role = MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT

            # Create Mock object with configure_mock to set all attributes at once
            msg = Mock()
            msg.configure_mock(**{
                'id': f"msg-{i}",
                'chat_id': chat_id,
                'role': role,
                'content': f"Message {i}",
                'status': MessageStatus.DELIVERED,
                'created_at': created_at,
                'updated_at': updated_at,
                'metadata': {},
                'model': "saptiva-turbo" if i % 2 == 1 else None,
                'tokens': 10,
                'latency_ms': 100,
                'task_id': None,
                'file_ids': [],
                'files': []
            })

            mock_messages.append(msg)

        # Create robust query builder that supports chaining
        query_builder = MockBeanieQueryBuilder(
            messages=mock_messages,
            total_count=100
        )

        # Mock Task model query (for research task enrichment)
        mock_task_query = AsyncMock()
        mock_task_query.to_list = AsyncMock(return_value=[])

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.history_endpoints.HistoryService') as MockHistoryService, \
             patch('src.routers.chat.endpoints.history_endpoints.ChatMessageModel') as MockMessageModel:

            # Setup
            mock_get_cache.return_value = mock_redis_cache
            mock_redis_cache.get_chat_history = AsyncMock(return_value=None)
            mock_redis_cache.set_chat_history = AsyncMock()

            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )

            # Setup ChatMessageModel.find() to return the query builder
            # The endpoint calls: find(...).find(...).sort(...).skip(...).limit(...).to_list()
            MockMessageModel.find = MagicMock(return_value=query_builder)

            # Execute with pagination - disable research tasks to simplify
            response = client.get(f"/history/{chat_id}?limit={limit}&offset={offset}&include_research_tasks=false")

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # Verify pagination was applied correctly
            assert query_builder.skip_called_with == offset
            assert query_builder.limit_called_with == limit
            # Verify response structure
            assert "messages" in data
            assert len(data["messages"]) <= limit
            assert "total_count" in data
            assert data["total_count"] == 100

    @pytest.mark.asyncio
    async def test_get_chat_history_has_more_flag(
        self,
        client,
        mock_chat_session,
        mock_redis_cache,
        mock_chat_messages
    ):
        """Should correctly set has_more flag based on total count"""
        chat_id = "test-chat-123"

        # Create 100 mock messages for pagination testing
        # Use Mock without spec to allow flexible attribute access
        mock_messages = []
        for i in range(100):
            created_at = datetime.utcnow()
            updated_at = datetime.utcnow()
            role = MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT

            # Create Mock object with configure_mock to set all attributes at once
            msg = Mock()
            msg.configure_mock(**{
                'id': f"msg-{i}",
                'chat_id': chat_id,
                'role': role,
                'content': f"Message {i}",
                'status': MessageStatus.DELIVERED,
                'created_at': created_at,
                'updated_at': updated_at,
                'metadata': {},
                'model': "saptiva-turbo" if i % 2 == 1 else None,
                'tokens': 10,
                'latency_ms': 100,
                'task_id': None,
                'file_ids': [],
                'files': []
            })

            mock_messages.append(msg)

        # Create robust query builder that supports chaining
        # Total count is 100, so has_more should be True (0 + 10 < 100)
        query_builder = MockBeanieQueryBuilder(
            messages=mock_messages,
            total_count=100
        )

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.history_endpoints.HistoryService') as MockHistoryService, \
             patch('src.routers.chat.endpoints.history_endpoints.ChatMessageModel') as MockMessageModel:

            # Setup
            mock_get_cache.return_value = mock_redis_cache
            mock_redis_cache.get_chat_history = AsyncMock(return_value=None)
            mock_redis_cache.set_chat_history = AsyncMock()

            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )

            # Setup ChatMessageModel.find() to return the query builder
            MockMessageModel.find = MagicMock(return_value=query_builder)

            # Execute with limit=10, offset=0 - disable research tasks to simplify
            response = client.get(f"/history/{chat_id}?limit=10&offset=0&include_research_tasks=false")

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 100
            # With offset=0 and limit=10, and total_count=100: has_more = 0 + 10 < 100 = True
            assert data["has_more"] is True

    @pytest.mark.asyncio
    async def test_get_chat_history_unauthorized(self, client):
        """Should return 404 when user doesn't have access"""
        chat_id = "unauthorized-chat"

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.history_endpoints.HistoryService') as MockHistoryService:

            # Setup
            mock_redis_cache = AsyncMock()
            mock_redis_cache.get_chat_history = AsyncMock(return_value=None)
            mock_get_cache.return_value = mock_redis_cache

            # HistoryService raises HTTPException for unauthorized access
            from fastapi import HTTPException
            MockHistoryService.get_session_with_permission_check = AsyncMock(
                side_effect=HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat session not found"
                )
            )

            # Execute
            response = client.get(f"/history/{chat_id}")

            # Assertions
            assert response.status_code == status.HTTP_404_NOT_FOUND
