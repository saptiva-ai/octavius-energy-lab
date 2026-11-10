"""
Integration tests for chat history pagination and escalate endpoints.

These tests use real MongoDB and Redis connections via Docker Compose
to validate end-to-end behavior of the chat history and escalate endpoints.

Tests:
- GET /history/{chat_id} with pagination (limit, offset)
- GET /history/{chat_id} with has_more flag calculation
- POST /chat/{chat_id}/escalate with kill switch handling

Note: These tests complement the unit tests in test_history_endpoints_v2.py
and test_message_endpoints_v2.py, providing end-to-end validation.
"""

import pytest
from datetime import datetime, timedelta
from fastapi import status
from httpx import AsyncClient
import asyncio
import os

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_CHAT_HISTORY", "false").lower() != "true",
    reason="Integration chat history deshabilitado por defecto (requires full stack)",
)

from src.models.chat import ChatSession, ChatMessage, MessageRole, MessageStatus


@pytest.fixture
async def test_user_with_token(integration_client):
    """Create a test user and return access token"""
    # Register user
    register_data = {
        "username": "pagination_test_user",
        "email": "pagination@test.com",
        "password": "SecurePass123!",
        "full_name": "Pagination Test User"
    }

    response = await integration_client.post("/auth/register", json=register_data)
    assert response.status_code == status.HTTP_201_CREATED

    # Login to get token
    login_data = {
        "identifier": "pagination_test_user",
        "password": "SecurePass123!"
    }
    response = await integration_client.post("/auth/login", json=login_data)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    return data["access_token"], data["user"]["id"]


@pytest.fixture
async def test_chat_session_with_messages(test_user_with_token, integration_client):
    """Create a chat session with 100 messages for pagination testing"""
    access_token, user_id = test_user_with_token

    # Create chat session directly in database
    session = ChatSession(
        user_id=user_id,
        title="Pagination Test Session",
        model="saptiva-turbo",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    await session.save()

    # Create 100 messages
    messages = []
    base_time = datetime.utcnow() - timedelta(hours=1)

    for i in range(100):
        message = ChatMessage(
            chat_id=str(session.id),
            role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
            content=f"Test message {i}",
            status=MessageStatus.DELIVERED,
            created_at=base_time + timedelta(seconds=i),
            updated_at=base_time + timedelta(seconds=i),
            metadata={},
            model="saptiva-turbo" if i % 2 == 1 else None,
            tokens=10,
            latency_ms=100
        )
        await message.save()
        messages.append(message)

    return str(session.id), access_token, messages


@pytest.mark.integration
@pytest.mark.asyncio
class TestChatHistoryPaginationIntegration:
    """Integration tests for chat history pagination endpoints"""

    async def test_get_chat_history_with_pagination_limit_10(
        self,
        integration_client: AsyncClient,
        test_chat_session_with_messages
    ):
        """Should return correct number of messages with limit=10"""
        chat_id, access_token, messages = test_chat_session_with_messages

        headers = {"Authorization": f"Bearer {access_token}"}
        response = await integration_client.get(
            f"/history/{chat_id}?limit=10&offset=0",
            headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "messages" in data
        assert len(data["messages"]) == 10
        assert data["total_count"] == 100
        assert data["has_more"] is True  # 0 + 10 < 100

    async def test_get_chat_history_with_pagination_offset(
        self,
        integration_client: AsyncClient,
        test_chat_session_with_messages
    ):
        """Should return correct messages with offset"""
        chat_id, access_token, messages = test_chat_session_with_messages

        headers = {"Authorization": f"Bearer {access_token}"}
        response = await integration_client.get(
            f"/history/{chat_id}?limit=25&offset=10",
            headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data["messages"]) == 25
        assert data["total_count"] == 100
        assert data["has_more"] is True  # 10 + 25 < 100

    async def test_get_chat_history_has_more_false_at_end(
        self,
        integration_client: AsyncClient,
        test_chat_session_with_messages
    ):
        """Should set has_more=False when at end of messages"""
        chat_id, access_token, messages = test_chat_session_with_messages

        headers = {"Authorization": f"Bearer {access_token}"}
        response = await integration_client.get(
            f"/history/{chat_id}?limit=50&offset=50",
            headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data["messages"]) == 50
        assert data["total_count"] == 100
        assert data["has_more"] is False  # 50 + 50 = 100 (no more)

    async def test_get_chat_history_unauthorized_without_token(
        self,
        integration_client: AsyncClient,
        test_chat_session_with_messages
    ):
        """Should return 401 when accessing without authentication"""
        chat_id, _, _ = test_chat_session_with_messages

        response = await integration_client.get(f"/history/{chat_id}")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_chat_history_not_found_invalid_chat(
        self,
        integration_client: AsyncClient,
        test_user_with_token
    ):
        """Should return 404 for non-existent chat session"""
        access_token, _ = test_user_with_token

        headers = {"Authorization": f"Bearer {access_token}"}
        response = await integration_client.get(
            "/history/nonexistent-chat-id",
            headers=headers
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.integration
@pytest.mark.asyncio
class TestEscalateToResearchIntegration:
    """Integration tests for escalate to research endpoint"""

    async def test_escalate_to_research_with_kill_switch_disabled(
        self,
        integration_client: AsyncClient,
        test_chat_session_with_messages
    ):
        """Should successfully escalate when kill switch is disabled"""
        chat_id, access_token, _ = test_chat_session_with_messages

        # Note: This test assumes DEEP_RESEARCH_KILL_SWITCH=false in test environment
        # If your test env has kill switch enabled, this test will verify that behavior

        headers = {"Authorization": f"Bearer {access_token}"}
        response = await integration_client.post(
            f"/chat/{chat_id}/escalate",
            headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "success" in data

        # If kill switch is disabled, success should be True
        # If enabled, success will be False with kill_switch_active flag
        if data["success"]:
            assert "data" in data
        else:
            assert data["data"]["kill_switch_active"] is True

    async def test_escalate_research_session_not_found(
        self,
        integration_client: AsyncClient,
        test_user_with_token
    ):
        """Should return 404 when escalating non-existent session"""
        access_token, _ = test_user_with_token

        headers = {"Authorization": f"Bearer {access_token}"}
        response = await integration_client.post(
            "/chat/nonexistent-chat-id/escalate",
            headers=headers
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    async def test_escalate_unauthorized_without_token(
        self,
        integration_client: AsyncClient,
        test_chat_session_with_messages
    ):
        """Should return 401 when escalating without authentication"""
        chat_id, _, _ = test_chat_session_with_messages

        response = await integration_client.post(f"/chat/{chat_id}/escalate")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.integration
@pytest.mark.asyncio
class TestChatHistoryPaginationEdgeCases:
    """Integration tests for edge cases in pagination"""

    async def test_pagination_with_very_large_limit(
        self,
        integration_client: AsyncClient,
        test_chat_session_with_messages
    ):
        """Should handle limit larger than total messages"""
        chat_id, access_token, messages = test_chat_session_with_messages

        headers = {"Authorization": f"Bearer {access_token}"}
        response = await integration_client.get(
            f"/history/{chat_id}?limit=500&offset=0",
            headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Should return all 100 messages, not 500
        assert len(data["messages"]) == 100
        assert data["has_more"] is False

    async def test_pagination_with_offset_beyond_messages(
        self,
        integration_client: AsyncClient,
        test_chat_session_with_messages
    ):
        """Should return empty list when offset exceeds total messages"""
        chat_id, access_token, messages = test_chat_session_with_messages

        headers = {"Authorization": f"Bearer {access_token}"}
        response = await integration_client.get(
            f"/history/{chat_id}?limit=10&offset=150",
            headers=headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert len(data["messages"]) == 0
        assert data["total_count"] == 100
        assert data["has_more"] is False
