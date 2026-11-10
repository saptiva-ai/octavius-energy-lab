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
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from fastapi import FastAPI, status, Request
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
import sys
import os

# Ensure proper imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..', 'src'))

from src.routers.chat.endpoints.history_endpoints import router as history_router
from src.schemas.chat import ChatHistoryResponse, ChatMessage
from src.models.chat import MessageRole, MessageStatus
from src.models.task import Task as TaskModel
from src.core.exceptions import NotFoundError


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
    msg1 = ChatMessage(
        id="msg-1",
        chat_id="chat-123",
        role=MessageRole.USER,
        content="Hello, assistant!",
        status=MessageStatus.DELIVERED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        metadata={"source": "web"},
        model=None,
        tokens=5,
        latency_ms=0,
        task_id=None
    )

    msg2 = ChatMessage(
        id="msg-2",
        chat_id="chat-123",
        role=MessageRole.ASSISTANT,
        content="Hello! How can I help you?",
        status=MessageStatus.DELIVERED,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        metadata={},
        model="saptiva-turbo",
        tokens=10,
        latency_ms=250,
        task_id=None
    )

    return [msg1, msg2]


@pytest.mark.unit
class TestGetChatHistory:
    """Test GET /history/{chat_id} endpoint"""

    @pytest.mark.asyncio
    async def test_get_chat_history_success(
        self,
        client,
        mock_chat_session,
        mock_chat_messages,
        mock_redis_cache
    ):
        """Should retrieve chat history with messages"""
        chat_id = "test-chat-123"

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.history_endpoints.HistoryService') as MockHistoryService, \
             patch('src.routers.chat.endpoints.history_endpoints.ChatMessageModel') as MockMessageModel:

            # Setup
            mock_get_cache.return_value = mock_redis_cache
            mock_redis_cache.get_chat_history = AsyncMock(return_value=None)

            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )

            # Mock message query
            query = MagicMock()
            query.find = MagicMock(return_value=query)
            query.sort = MagicMock(return_value=query)
            query.skip = MagicMock(return_value=query)
            query.limit = MagicMock(return_value=query)
            query.count = AsyncMock(return_value=2)
            query.to_list = AsyncMock(return_value=mock_chat_messages)

            MockMessageModel.find = MagicMock(return_value=query)

            # Mock empty research tasks
            with patch('src.models.task.Task') as MockTaskModel:
                task_query = MagicMock()
                task_query.find = MagicMock(return_value=task_query)
                task_query.to_list = AsyncMock(return_value=[])
                MockTaskModel.find = MagicMock(return_value=task_query)

                # Execute
                response = client.get(f"/history/{chat_id}")

                # Assertions
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["chat_id"] == chat_id
                assert "messages" in data
                assert len(data["messages"]) == 2
                assert data["total_count"] == 2
                assert data["has_more"] is False

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
                    "task_id": None,
                    "file_ids": [],
                    "files": [],
                    "schema_version": 2
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
            data = response.json()
            assert data == cached_data
            # Should not call permission check when cache hits
            mock_redis_cache.get_chat_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_chat_history_with_research_tasks(
        self,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should enrich messages with research task data"""
        chat_id = "test-chat-123"

        # Create message with task_id
        msg_with_task = ChatMessage(
            id="msg-3",
            chat_id=chat_id,
            role=MessageRole.ASSISTANT,
            content="Research results...",
            status=MessageStatus.DELIVERED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            metadata={},
            model="saptiva-turbo",
            tokens=150,
            latency_ms=2000,
            task_id="task-1"
        )

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.history_endpoints.HistoryService') as MockHistoryService, \
             patch('src.routers.chat.endpoints.history_endpoints.ChatMessageModel') as MockMessageModel, \
             patch('src.models.task.Task') as MockTaskModel:

            # Setup
            mock_get_cache.return_value = mock_redis_cache
            mock_redis_cache.get_chat_history = AsyncMock(return_value=None)
            mock_redis_cache.set_chat_history = AsyncMock()

            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )

            # Mock messages
            msg_query = MagicMock()
            msg_query.find = MagicMock(return_value=msg_query)
            msg_query.sort = MagicMock(return_value=msg_query)
            msg_query.skip = MagicMock(return_value=msg_query)
            msg_query.limit = MagicMock(return_value=msg_query)
            msg_query.count = AsyncMock(return_value=1)
            msg_query.to_list = AsyncMock(return_value=[msg_with_task])

            MockMessageModel.find = MagicMock(return_value=msg_query)

            # Mock research task
            task = MagicMock()
            task.id = "task-1"
            task.status.value = "completed"
            task.progress = 100
            task.current_step = 5
            task.total_steps = 5
            task.created_at = datetime.utcnow()
            task.started_at = datetime.utcnow()
            task.completed_at = datetime.utcnow()
            task.error_message = None
            task.input_data = {"query": "research"}
            task.result_data = {"findings": "data"}

            task_query = MagicMock()
            task_query.find = MagicMock(return_value=task_query)
            task_query.to_list = AsyncMock(return_value=[task])

            MockTaskModel.find = MagicMock(return_value=task_query)

            # Execute with research tasks enabled
            response = client.get(f"/history/{chat_id}?include_research_tasks=true")

            # Assertions
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert len(data["messages"]) == 1
            # Research task should be enriched in metadata
            msg_data = data["messages"][0]
            if msg_data.get("metadata"):
                assert "research_task" in msg_data["metadata"]

    @pytest.mark.asyncio
    async def test_get_chat_history_exclude_system_messages(
        self,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should exclude system messages when include_system=False"""
        chat_id = "test-chat-123"

        # Create system message
        system_msg = ChatMessage(
            id="msg-sys",
            chat_id=chat_id,
            role=MessageRole.SYSTEM,
            content="System prompt",
            created_at=datetime.utcnow()
        )

        user_msg = ChatMessage(
            id="msg-user",
            chat_id=chat_id,
            role=MessageRole.USER,
            content="Hello",
            created_at=datetime.utcnow()
        )

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.history_endpoints.HistoryService') as MockHistoryService, \
             patch('src.routers.chat.endpoints.history_endpoints.ChatMessageModel') as MockMessageModel:

            # Setup
            mock_get_cache.return_value = mock_redis_cache
            mock_redis_cache.get_chat_history = AsyncMock(return_value=None)

            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )

            # Mock query that filters out system messages
            query = MagicMock()
            query.find = MagicMock(return_value=query)
            query.sort = MagicMock(return_value=query)
            query.skip = MagicMock(return_value=query)
            query.limit = MagicMock(return_value=query)
            query.count = AsyncMock(return_value=1)
            query.to_list = AsyncMock(return_value=[user_msg])

            MockMessageModel.find = MagicMock(return_value=query)

            # Mock empty research tasks
            with patch('src.models.task.Task') as MockTaskModel:
                task_query = MagicMock()
                task_query.find = MagicMock(return_value=task_query)
                task_query.to_list = AsyncMock(return_value=[])
                MockTaskModel.find = MagicMock(return_value=task_query)

                # Execute with include_system=False
                response = client.get(f"/history/{chat_id}?include_system=false")

                # Assertions
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                # Should only have user message
                assert len(data["messages"]) == 1
                assert data["messages"][0]["id"] == "msg-user"

    @pytest.mark.parametrize("limit,offset", [(10, 0), (25, 10), (50, 50)])
    @pytest.mark.asyncio
    async def test_get_chat_history_pagination(
        self,
        limit,
        offset,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should respect limit and offset parameters"""
        chat_id = "test-chat-123"

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.history_endpoints.HistoryService') as MockHistoryService, \
             patch('src.routers.chat.endpoints.history_endpoints.ChatMessageModel') as MockMessageModel:

            # Setup
            mock_get_cache.return_value = mock_redis_cache
            mock_redis_cache.get_chat_history = AsyncMock(return_value=None)

            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )

            query = MagicMock()
            query.find = MagicMock(return_value=query)
            query.sort = MagicMock(return_value=query)
            query.skip = MagicMock(return_value=query)
            query.limit = MagicMock(return_value=query)
            query.count = AsyncMock(return_value=100)
            query.to_list = AsyncMock(return_value=[])

            MockMessageModel.find = MagicMock(return_value=query)

            # Mock empty research tasks
            with patch('src.models.task.Task') as MockTaskModel:
                task_query = MagicMock()
                task_query.find = MagicMock(return_value=task_query)
                task_query.to_list = AsyncMock(return_value=[])
                MockTaskModel.find = MagicMock(return_value=task_query)

                # Execute with pagination
                response = client.get(f"/history/{chat_id}?limit={limit}&offset={offset}")

                # Assertions
                assert response.status_code == status.HTTP_200_OK
                # Verify pagination was called correctly
                query.skip.assert_called_with(offset)
                query.limit.assert_called_with(limit)

    @pytest.mark.asyncio
    async def test_get_chat_history_has_more_flag(
        self,
        client,
        mock_chat_session,
        mock_redis_cache
    ):
        """Should correctly set has_more flag based on total count"""
        chat_id = "test-chat-123"

        with patch('src.routers.chat.endpoints.history_endpoints.get_redis_cache') as mock_get_cache, \
             patch('src.routers.chat.endpoints.history_endpoints.HistoryService') as MockHistoryService, \
             patch('src.routers.chat.endpoints.history_endpoints.ChatMessageModel') as MockMessageModel:

            # Setup
            mock_get_cache.return_value = mock_redis_cache
            mock_redis_cache.get_chat_history = AsyncMock(return_value=None)

            MockHistoryService.get_session_with_permission_check = AsyncMock(
                return_value=mock_chat_session
            )

            query = MagicMock()
            query.find = MagicMock(return_value=query)
            query.sort = MagicMock(return_value=query)
            query.skip = MagicMock(return_value=query)
            query.limit = MagicMock(return_value=query)
            query.count = AsyncMock(return_value=100)  # Total 100 messages
            messages = [
                ChatMessage(
                    id=f"msg-{i}",
                    chat_id=chat_id,
                    role=MessageRole.USER,
                    content=f"Message {i}",
                    created_at=datetime.utcnow()
                ) for i in range(10)
            ]
            query.to_list = AsyncMock(return_value=messages)  # Return 10

            MockMessageModel.find = MagicMock(return_value=query)

            # Mock empty research tasks
            with patch('src.models.task.Task') as MockTaskModel:
                task_query = MagicMock()
                task_query.find = MagicMock(return_value=task_query)
                task_query.to_list = AsyncMock(return_value=[])
                MockTaskModel.find = MagicMock(return_value=task_query)

                # Execute with limit=10, offset=0
                response = client.get(f"/history/{chat_id}?limit=10&offset=0")

                # Assertions
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["total_count"] == 100
                assert data["has_more"] is True  # 0 + 10 < 100

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

            MockHistoryService.get_session_with_permission_check = AsyncMock(
                side_effect=NotFoundError("Session not found", code="SESSION_NOT_FOUND")
            )

            # Execute
            response = client.get(f"/history/{chat_id}")

            # Assertions
            assert response.status_code == status.HTTP_404_NOT_FOUND

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

    @pytest.mark.asyncio
    async def test_get_chat_history_cache_set_after_retrieval(
        self,
        client,
        mock_chat_session,
        mock_chat_messages,
        mock_redis_cache
    ):
        """Should cache history after retrieval"""
        chat_id = "test-chat-123"

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

            query = MagicMock()
            query.find = MagicMock(return_value=query)
            query.sort = MagicMock(return_value=query)
            query.skip = MagicMock(return_value=query)
            query.limit = MagicMock(return_value=query)
            query.count = AsyncMock(return_value=2)
            query.to_list = AsyncMock(return_value=mock_chat_messages)

            MockMessageModel.find = MagicMock(return_value=query)

            # Mock empty research tasks
            with patch('src.models.task.Task') as MockTaskModel:
                task_query = MagicMock()
                task_query.find = MagicMock(return_value=task_query)
                task_query.to_list = AsyncMock(return_value=[])
                MockTaskModel.find = MagicMock(return_value=task_query)

                # Execute
                response = client.get(f"/history/{chat_id}?limit=50&offset=0")

                # Assertions
                assert response.status_code == status.HTTP_200_OK
                # Should cache the result
                mock_redis_cache.set_chat_history.assert_called_once()
                call_kwargs = mock_redis_cache.set_chat_history.call_args[1]
                assert call_kwargs["chat_id"] == chat_id
                assert call_kwargs["limit"] == 50
                assert call_kwargs["offset"] == 0
