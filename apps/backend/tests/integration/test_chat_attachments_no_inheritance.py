"""
Integration tests for Attachments No Inheritance Policy.

Validates that each chat message uses ONLY its own file_ids,
without inheriting attachments from previous turns.

Policy: "Nada de herencias implícitas de adjuntos"
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
from src.schemas.user import UserCreate


@pytest_asyncio.fixture
async def test_user_attachments(clean_db) -> Dict[str, str]:
    """Create a test user for attachment tests and return credentials."""
    username = "test-attachments"
    email = "test-attachments@example.com"
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
async def auth_token_attachments(test_user_attachments: Dict[str, str]) -> str:
    """Create auth token for test user"""
    settings = get_settings()

    now = datetime.utcnow()
    payload = {
        "sub": test_user_attachments["user_id"],
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=1),
        "username": test_user_attachments["username"],
        "email": test_user_attachments["email"],
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@pytest_asyncio.fixture
async def first_image(test_user_attachments: Dict[str, str]):
    """Create first test image document"""
    from src.services.cache_service import get_redis_client

    document_text = "MEME TEST IMAGE\nPrimera Imagen"

    document = Document(
        filename="meme.png",
        content_type="image/png",
        size_bytes=1024,
        minio_key="test-meme-key",
        minio_bucket="test",
        status=DocumentStatus.READY,
        user_id=test_user_attachments["user_id"],
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
            await redis_client.set(redis_key, document_text, ex=3600)
    except Exception as e:
        print(f"Warning: Could not cache first_image in Redis: {e}")

    yield document

    # Cleanup
    try:
        doc_to_delete = await Document.find_one(Document.id == document.id)
        if doc_to_delete:
            await doc_to_delete.delete()
        redis_client = await get_redis_client()
        if redis_client:
            await redis_client.delete(f"doc:text:{str(document.id)}")
    except Exception:
        pass


@pytest_asyncio.fixture
async def second_image(test_user_attachments: Dict[str, str]):
    """Create second test image document"""
    from src.services.cache_service import get_redis_client

    document_text = "COVER TEST IMAGE\nSegunda Imagen"

    document = Document(
        filename="cover.png",
        content_type="image/png",
        size_bytes=2048,
        minio_key="test-cover-key",
        minio_bucket="test",
        status=DocumentStatus.READY,
        user_id=test_user_attachments["user_id"],
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
            await redis_client.set(redis_key, document_text, ex=3600)
    except Exception as e:
        print(f"Warning: Could not cache second_image in Redis: {e}")

    yield document

    # Cleanup
    try:
        doc_to_delete = await Document.find_one(Document.id == document.id)
        if doc_to_delete:
            await doc_to_delete.delete()
        redis_client = await get_redis_client()
        if redis_client:
            await redis_client.delete(f"doc:text:{str(document.id)}")
    except Exception:
        pass


@pytest.mark.asyncio
@pytest.mark.integration
async def test_second_image_replaces_first_no_inheritance(
    auth_token_attachments,
    first_image,
    second_image
):
    """
    E2E Test: Second message with different image should NOT inherit first image.

    Flow:
    1. Send message with first_image (meme.png)
    2. Send message with second_image (cover.png)
    3. Verify second LLM call receives ONLY cover.png, not meme.png

    This validates the "no inheritance" policy.
    """
    headers = {
        "Authorization": f"Bearer {auth_token_attachments}",
        "Content-Type": "application/json"
    }

    with patch('src.services.saptiva_client.SaptivaClient.chat_completion', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "Analyzing the image..."

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            # Message 1: Send with first image (meme.png)
            response1 = await client.post(
                "/api/chat",
                headers=headers,
                json={
                    "message": "¿Qué dice esta imagen?",
                    "file_ids": [str(first_image.id)],
                    "model": "Saptiva Turbo"
                }
            )

            assert response1.status_code == status.HTTP_200_OK
            data1 = response1.json()
            chat_id = data1["chat_id"]

            # Verify first message was stored with first_image
            first_msg = await ChatMessageModel.find_one(
                ChatMessageModel.chat_id == chat_id,
                ChatMessageModel.role == "user"
            )
            assert first_msg is not None
            assert str(first_image.id) in first_msg.file_ids
            assert len(first_msg.file_ids) == 1

            # Message 2: Send with second image (cover.png)
            response2 = await client.post(
                "/api/chat",
                headers=headers,
                json={
                    "chat_id": chat_id,
                    "message": "¿Y ahora qué dice?",
                    "file_ids": [str(second_image.id)],
                    "model": "Saptiva Turbo"
                }
            )

            assert response2.status_code == status.HTTP_200_OK

            # CRITICAL VALIDATION: Second message should have ONLY second_image
            second_user_msgs = await ChatMessageModel.find(
                ChatMessageModel.chat_id == chat_id,
                ChatMessageModel.role == "user"
            ).to_list()

            assert len(second_user_msgs) == 2, "Should have 2 user messages"
            second_msg = second_user_msgs[1]

            # NO INHERITANCE: second message should have ONLY second_image.id
            assert len(second_msg.file_ids) == 1, f"Expected 1 file_id, got {len(second_msg.file_ids)}"
            assert str(second_image.id) in second_msg.file_ids, "Should have second_image.id"
            assert str(first_image.id) not in second_msg.file_ids, \
                "CRITICAL: Should NOT inherit first_image.id from previous message"

            # VERIFY LLM PAYLOAD: Second call should receive ONLY second image context
            assert mock_llm.call_count == 2, "Should have called LLM twice"

            second_call_args = mock_llm.call_args_list[1]
            second_payload = second_call_args.kwargs
            second_messages = second_payload.get('messages', [])

            # Check system message for document context
            system_messages = [m for m in second_messages if m.get('role') == 'system']
            if system_messages:
                system_content = system_messages[0].get('content', '')

                # Should have second image context
                assert 'cover.png' in system_content.lower() or 'Segunda Imagen' in system_content, \
                    "Second LLM call should include second image context"

                # Should NOT have first image context
                assert 'meme.png' not in system_content.lower(), \
                    "CRITICAL: Second LLM call should NOT include first image context (no inheritance)"
                assert 'Primera Imagen' not in system_content, \
                    "CRITICAL: Second LLM call should NOT include first image text (no inheritance)"

            # Cleanup
            await ChatMessageModel.find(ChatMessageModel.chat_id == chat_id).delete()
            session = await ChatSessionModel.get(chat_id)
            if session:
                await session.delete()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_message_without_files_reuses_previous_context(
    auth_token_attachments,
    first_image
):
    """
    E2E Test: Message without file_ids should reuse previous message's files.

    Flow:
    1. Send message with first_image
    2. Send message WITHOUT file_ids
    3. Verify second message uses first image context automatically
    """
    headers = {
        "Authorization": f"Bearer {auth_token_attachments}",
        "Content-Type": "application/json"
    }

    with patch('src.services.saptiva_client.SaptivaClient.chat_completion', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "Response..."

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            # Message 1: With image
            response1 = await client.post(
                "/api/chat",
                headers=headers,
                json={
                    "message": "Analiza esta imagen",
                    "file_ids": [str(first_image.id)],
                    "model": "Saptiva Turbo"
                }
            )
            assert response1.status_code == status.HTTP_200_OK
            chat_id = response1.json()["chat_id"]

            # Message 2: WITHOUT file_ids
            response2 = await client.post(
                "/api/chat",
                headers=headers,
                json={
                    "chat_id": chat_id,
                    "message": "Dame más detalles",  # No file_ids
                    "model": "Saptiva Turbo"
                }
            )
            assert response2.status_code == status.HTTP_200_OK

            # Verify second message has empty file_ids
            user_messages = await ChatMessageModel.find(
                ChatMessageModel.chat_id == chat_id,
                ChatMessageModel.role == "user"
            ).to_list()

            assert len(user_messages) == 2
            second_msg = user_messages[1]
            assert len(second_msg.file_ids) == 1, \
                "Second message should reuse previous image when no new files provided"
            assert str(first_image.id) in second_msg.file_ids, \
                "Second message should include first_image.id when reusing context"

            # Verify LLM call reused previous document context
            assert mock_llm.call_count == 2
            second_call_args = mock_llm.call_args_list[1]
            second_payload = second_call_args.kwargs
            second_messages = second_payload.get('messages', [])

            system_messages = [m for m in second_messages if m.get('role') == 'system']
            if system_messages:
                system_content = system_messages[0].get('content', '')
                # Should mention the reused image
                assert 'meme.png' in system_content.lower(), \
                    "Second LLM call should include previous image when reusing context"

            # Cleanup
            await ChatMessageModel.find(ChatMessageModel.chat_id == chat_id).delete()
            session = await ChatSessionModel.get(chat_id)
            if session:
                await session.delete()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_three_images_each_turn_has_only_its_own(
    auth_token_attachments,
    test_user_attachments
):
    """
    E2E Test: Three consecutive messages with different images.
    Each turn should have ONLY its own image, no accumulation.

    Flow:
    1. Message with image A
    2. Message with image B
    3. Message with image C
    4. Verify each message stored only its own file_id
    5. Verify each LLM call received only that message's image
    """
    from src.services.cache_service import get_redis_client

    # Create three test images
    images = []
    for i, (filename, text) in enumerate([
        ("image_a.png", "Image A content"),
        ("image_b.png", "Image B content"),
        ("image_c.png", "Image C content")
    ]):
        doc = Document(
            filename=filename,
            content_type="image/png",
            size_bytes=1024 * (i + 1),
            minio_key=f"test-key-{i}",
            minio_bucket="test",
            status=DocumentStatus.READY,
            user_id=test_user_attachments["user_id"],
            pages=[{"page": 1, "text_md": text, "has_table": False}]
        )
        await doc.insert()

        # Cache in Redis
        try:
            redis_client = await get_redis_client()
            if redis_client:
                await redis_client.set(f"doc:text:{str(doc.id)}", text, ex=3600)
        except Exception:
            pass

        images.append(doc)

    headers = {
        "Authorization": f"Bearer {auth_token_attachments}",
        "Content-Type": "application/json"
    }

    try:
        with patch('src.services.saptiva_client.SaptivaClient.chat_completion', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Analyzing..."

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
                chat_id = None

                # Send 3 messages, each with different image
                for i, image in enumerate(images):
                    payload = {
                        "message": f"Analiza imagen {chr(65 + i)}",  # A, B, C
                        "file_ids": [str(image.id)],
                        "model": "Saptiva Turbo"
                    }
                    if chat_id:
                        payload["chat_id"] = chat_id

                    response = await client.post(
                        "/api/chat",
                        headers=headers,
                        json=payload
                    )
                    assert response.status_code == status.HTTP_200_OK

                    if not chat_id:
                        chat_id = response.json()["chat_id"]

                # Verify each user message has ONLY its own file_id
                user_messages = await ChatMessageModel.find(
                    ChatMessageModel.chat_id == chat_id,
                    ChatMessageModel.role == "user"
                ).sort("+created_at").to_list()

                assert len(user_messages) == 3, "Should have 3 user messages"

                for i, (msg, expected_image) in enumerate(zip(user_messages, images)):
                    assert len(msg.file_ids) == 1, \
                        f"Message {i + 1} should have exactly 1 file_id, got {len(msg.file_ids)}"
                    assert str(expected_image.id) in msg.file_ids, \
                        f"Message {i + 1} should have image {chr(65 + i)}"

                    # Verify no other images
                    for j, other_image in enumerate(images):
                        if i != j:
                            assert str(other_image.id) not in msg.file_ids, \
                                f"Message {i + 1} should NOT have image {chr(65 + j)} (no inheritance)"

                # Verify LLM calls
                assert mock_llm.call_count == 3, "Should have 3 LLM calls"

                for i, call_args in enumerate(mock_llm.call_args_list):
                    payload = call_args.kwargs
                    messages = payload.get('messages', [])
                    system_messages = [m for m in messages if m.get('role') == 'system']

                    if system_messages:
                        system_content = system_messages[0].get('content', '')
                        expected_filename = f"image_{chr(97 + i)}.png"  # a, b, c

                        # Should have current image
                        assert expected_filename in system_content.lower() or \
                               f"Image {chr(65 + i)} content" in system_content, \
                            f"LLM call {i + 1} should include image {chr(65 + i)}"

                        # Should NOT have other images
                        for j in range(3):
                            if i != j:
                                other_filename = f"image_{chr(97 + j)}.png"
                                assert other_filename not in system_content.lower(), \
                                    f"LLM call {i + 1} should NOT include image {chr(65 + j)} (no inheritance)"

                # Cleanup
                if chat_id:
                    await ChatMessageModel.find(ChatMessageModel.chat_id == chat_id).delete()
                    session = await ChatSessionModel.get(chat_id)
                    if session:
                        await session.delete()

    finally:
        # Cleanup all test images
        for image in images:
            try:
                doc_to_delete = await Document.find_one(Document.id == image.id)
                if doc_to_delete:
                    await doc_to_delete.delete()
                redis_client = await get_redis_client()
                if redis_client:
                    await redis_client.delete(f"doc:text:{str(image.id)}")
            except Exception:
                pass

