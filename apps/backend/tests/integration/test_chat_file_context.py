"""
Integration tests for File Context Persistence - MVP-FILE-CONTEXT

Tests the complete /api/chat endpoint with file persistence across multiple messages.
Uses real database but mocks LLM calls.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
import jwt
from httpx import AsyncClient, ASGITransport
from fastapi import status
from unittest.mock import patch, AsyncMock
from typing import Dict

from src.main import app
from src.models.chat import ChatSession as ChatSessionModel, ChatMessage as ChatMessageModel
from src.models.document import Document, DocumentStatus
from src.models.user import User
from src.core.config import get_settings
from src.services.auth_service import register_user
from src.core.exceptions import ConflictError
from src.schemas.user import UserCreate


@pytest_asyncio.fixture
async def test_user_chat(clean_db) -> Dict[str, str]:
    """Create a test user for chat tests and return credentials."""
    username = "test-file-context"
    email = "test-file-context@example.com"
    password = "Demo1234"

    # Register user
    auth_response = await register_user(
        UserCreate(
            username=username,
            email=email,
            password=password
        )
    )

    return {
        "username": username,
        "email": email,
        "password": password,
        "user_id": auth_response.user.id
    }


@pytest_asyncio.fixture
async def auth_token(test_user_chat: Dict[str, str]) -> str:
    """Create auth token for test user"""
    settings = get_settings()

    now = datetime.utcnow()
    payload = {
        "sub": test_user_chat["user_id"],
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=1),
        "username": test_user_chat["username"],
        "email": test_user_chat["email"],
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@pytest_asyncio.fixture
async def test_document(test_user_chat: Dict[str, str]):
    """Create a test document for file context tests"""
    from src.services.cache_service import get_redis_client

    document_text = "# Test Document\n\nThis is a test PDF document for context persistence testing."

    document = Document(
        filename="test.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        minio_key="test-key",
        minio_bucket="test",
        status=DocumentStatus.READY,
        user_id=test_user_chat["user_id"],
        pages=[{
            "page": 1,
            "text_md": document_text,
            "has_table": False
        }]
    )
    await document.insert()

    # Cache document text in Redis
    try:
        redis_client = await get_redis_client()
        if redis_client:
            redis_key = f"doc:text:{str(document.id)}"
            await redis_client.set(redis_key, document_text, ex=3600)  # 1 hour TTL
    except Exception as e:
        print(f"Warning: Could not cache document in Redis: {e}")

    yield document

    # Cleanup
    try:
        doc_to_delete = await Document.find_one(Document.id == document.id)
        if doc_to_delete:
            await doc_to_delete.delete()
        # Clean Redis cache
        redis_client = await get_redis_client()
        if redis_client:
            await redis_client.delete(f"doc:text:{str(document.id)}")
    except Exception:
        pass


@pytest.mark.asyncio
@pytest.mark.integration
async def test_first_message_stores_file_ids_in_session(auth_token, test_document):
    """
    Integration Test: First message with file_ids should store them in ChatSession
    """
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }

    # Mock LLM call
    with patch('src.services.saptiva_client.SaptivaClient.chat_completion', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "This is a test document about context persistence."

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            # Send first message with file_ids
            response = await client.post(
                "/api/chat",
                headers=headers,
                json={
                    "message": "¿De qué trata este documento?",
                    "file_ids": [str(test_document.id)],
                    "model": "Saptiva Turbo"
                }
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            # Verify response
            assert "chat_id" in data
            assert "content" in data
            chat_id = data["chat_id"]

            # Verify session was created and file_ids were stored
            session = await ChatSessionModel.get(chat_id)
            assert session is not None
            assert hasattr(session, 'attached_file_ids')
            assert len(session.attached_file_ids) == 1
            assert str(test_document.id) in session.attached_file_ids

            # Cleanup
            await ChatMessageModel.find(ChatMessageModel.chat_id == chat_id).delete()
            await session.delete()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_second_message_includes_session_file_ids(auth_token, test_document):
    """
    Integration Test: Second message WITHOUT file_ids should still include session's files
    """
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }

    with patch('src.services.saptiva_client.SaptivaClient.chat_completion', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "Based on the document, here is my answer."

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            # Message 1: With file_ids
            response1 = await client.post(
                "/api/chat",
                headers=headers,
                json={
                    "message": "Primera pregunta sobre el documento",
                    "file_ids": [str(test_document.id)],
                    "model": "Saptiva Turbo"
                }
            )
            assert response1.status_code == status.HTTP_200_OK
            chat_id = response1.json()["chat_id"]

            # Message 2: WITHOUT file_ids (simulating follow-up)
            response2 = await client.post(
                "/api/chat",
                headers=headers,
                json={
                    "chat_id": chat_id,
                    "message": "Dame más detalles",  # No file_ids!
                    "model": "Saptiva Turbo"
                }
            )
            assert response2.status_code == status.HTTP_200_OK

            # Verify LLM was called with document context
            # Check that mock_llm was called and its payload included document content
            assert mock_llm.call_count == 2
            second_call_args = mock_llm.call_args_list[1]

            # The payload should include document context even though file_ids weren't in request
            # This verifies the merge logic worked
            payload = second_call_args.kwargs
            messages = payload.get('messages', [])

            # Should have system message with document context
            system_messages = [m for m in messages if m.get('role') == 'system']
            assert len(system_messages) > 0

            # Verify system message contains document text
            system_content = system_messages[0].get('content', '')
            assert 'Test Document' in system_content or 'test.pdf' in system_content.lower()

            # Cleanup
            await ChatMessageModel.find(ChatMessageModel.chat_id == chat_id).delete()
            session = await ChatSessionModel.get(chat_id)
            if session:
                await session.delete()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multi_turn_conversation_maintains_file_context(auth_token, test_document):
    """
    Integration Test: Multiple messages maintain file context throughout conversation
    """
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }

    with patch('src.services.saptiva_client.SaptivaClient.chat_completion', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "Response based on document context."

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            # Message 1: Upload file
            response1 = await client.post(
                "/api/chat",
                headers=headers,
                json={
                    "message": "Pregunta 1",
                    "file_ids": [str(test_document.id)],
                    "model": "Saptiva Turbo"
                }
            )
            assert response1.status_code == status.HTTP_200_OK
            chat_id = response1.json()["chat_id"]

            # Messages 2-5: No file_ids
            for i in range(2, 6):
                response = await client.post(
                    "/api/chat",
                    headers=headers,
                    json={
                        "chat_id": chat_id,
                        "message": f"Pregunta {i}",
                        "model": "Saptiva Turbo"
                    }
                )
                assert response.status_code == status.HTTP_200_OK

            # Verify session still has file_ids after 5 messages
            session = await ChatSessionModel.get(chat_id)
            assert session is not None
            assert len(session.attached_file_ids) == 1
            assert str(test_document.id) in session.attached_file_ids

            # Verify all 5 LLM calls had document context
            assert mock_llm.call_count == 5

            for call_args in mock_llm.call_args_list:
                payload = call_args.kwargs
                messages = payload.get('messages', [])
                system_messages = [m for m in messages if m.get('role') == 'system']
                assert len(system_messages) > 0

            # Cleanup
            await ChatMessageModel.find(ChatMessageModel.chat_id == chat_id).delete()
            await session.delete()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_adding_second_file_replaces_previous(auth_token, test_document, test_user_chat):
    """
    Integration Test: Adding a second file mid-conversation replaces previous files
    """
    from src.services.cache_service import get_redis_client

    # Create second document
    document2_text = "# Second Document\n\nThis is the second document."
    document2 = Document(
        filename="second.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        minio_key="test-key-2",
        minio_bucket="test",
        status=DocumentStatus.READY,
        user_id=test_user_chat["user_id"],
        pages=[{
            "page": 1,
            "text_md": document2_text,
            "has_table": False
        }]
    )
    await document2.insert()

    # Cache document text in Redis
    try:
        redis_client = await get_redis_client()
        if redis_client:
            redis_key = f"doc:text:{str(document2.id)}"
            await redis_client.set(redis_key, document2_text, ex=3600)
    except Exception as e:
        print(f"Warning: Could not cache document2 in Redis: {e}")

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }

    try:
        with patch('src.services.saptiva_client.SaptivaClient.chat_completion', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Analysis based on documents."

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
                # Message 1: First file
                response1 = await client.post(
                    "/api/chat",
                    headers=headers,
                    json={
                        "message": "Analiza el primer documento",
                        "file_ids": [str(test_document.id)],
                        "model": "Saptiva Turbo"
                    }
                )
                assert response1.status_code == status.HTTP_200_OK
                chat_id = response1.json()["chat_id"]

                # Message 2: Add second file
                response2 = await client.post(
                    "/api/chat",
                    headers=headers,
                    json={
                        "chat_id": chat_id,
                        "message": "Ahora compara con este segundo documento",
                        "file_ids": [str(document2.id)],
                        "model": "Saptiva Turbo"
                    }
                )
                assert response2.status_code == status.HTTP_200_OK

                # Verify session stores only the latest file (replaces previous)
                session = await ChatSessionModel.get(chat_id)
                assert session is not None
                assert len(session.attached_file_ids) == 1
                assert str(document2.id) in session.attached_file_ids
                assert str(test_document.id) not in session.attached_file_ids

                # Message 3: No files - should reuse latest document context
                response3 = await client.post(
                    "/api/chat",
                    headers=headers,
                    json={
                        "chat_id": chat_id,
                        "message": "¿Qué tienen en común?",
                        "model": "Saptiva Turbo"
                    }
                )
                assert response3.status_code == status.HTTP_200_OK

                # Verify third call reused second document only
                third_call_args = mock_llm.call_args_list[2]
                payload = third_call_args.kwargs
                messages = payload.get('messages', [])
                system_messages = [m for m in messages if m.get('role') == 'system']
                system_content = system_messages[0].get('content', '')

                # Should mention only the second document
                assert 'second.pdf' in system_content.lower()
                assert 'test.pdf' not in system_content.lower()

                # Cleanup
                await ChatMessageModel.find(ChatMessageModel.chat_id == chat_id).delete()
                await session.delete()
    finally:
        try:
            from src.services.cache_service import get_redis_client
            doc2_to_delete = await Document.find_one(Document.id == document2.id)
            if doc2_to_delete:
                await doc2_to_delete.delete()
            # Clean Redis cache
            redis_client = await get_redis_client()
            if redis_client:
                await redis_client.delete(f"doc:text:{str(document2.id)}")
        except Exception:
            pass


@pytest.mark.asyncio
@pytest.mark.integration
async def test_new_conversation_has_empty_attached_files(auth_token):
    """
    Integration Test: New conversation should start with empty attached_file_ids
    """
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }

    with patch('src.services.saptiva_client.SaptivaClient.chat_completion', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "Hello! How can I help?"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            # Send message without files
            response = await client.post(
                "/api/chat",
                headers=headers,
                json={
                    "message": "Hello, this is a test",
                    "model": "Saptiva Turbo"
                }
            )

            assert response.status_code == status.HTTP_200_OK
            chat_id = response.json()["chat_id"]

            # Verify session has no attached files
            session = await ChatSessionModel.get(chat_id)
            assert session is not None
            assert len(session.attached_file_ids) == 0

            # Cleanup
            await ChatMessageModel.find(ChatMessageModel.chat_id == chat_id).delete()
            await session.delete()
