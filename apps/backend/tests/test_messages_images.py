"""
Tests for messages with image attachments.

Validates "no inheritance" policy: second image must replace first, not accumulate.

Política de adjuntos: un mensaje guarda exactamente los adjuntos enviados en su payload.
No existe "herencia" de adjuntos desde turnos previos.
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient


@pytest_asyncio.fixture(scope="function", autouse=True)
async def initialize_db():
    """Initialize database connection for tests.

    This fixture ensures Beanie ODM is initialized before running tests.
    """
    from src.core.database import Database

    try:
        await Database.connect_to_mongo()
    except Exception:
        pass  # Already connected

    yield

    # Cleanup after tests
    from src.models.chat import ChatSession, ChatMessage

    try:
        # Clean up test data
        await ChatSession.find(ChatSession.user_id == "test-user").delete()
        await ChatMessage.find(ChatMessage.chat_id == "test-chat").delete()
    except Exception:
        pass  # Best effort cleanup


def fake_png_bytes(label: str) -> bytes:
    """Generate fake PNG bytes for testing (distinct per label)."""
    return f"PNG_FAKE_DATA:{label}".encode()


@pytest.mark.asyncio
async def test_second_image_replaces_first_in_message():
    """
    Test that the second message's file_ids do NOT inherit from the first.

    Scenario:
        1. Upload two distinct "images" (primera.png, segunda.png)
        2. Send first message with primera.png
        3. Send second message with segunda.png
        4. Verify that segunda.png message has ONLY segunda.png, not primera
    """
    # This test validates the database layer directly
    from src.models.chat import ChatMessage, MessageRole, ChatSession
    from src.services.chat_service import ChatService
    from src.core.config import get_settings

    settings = get_settings()
    chat_service = ChatService(settings)

    # Create test session
    session = await ChatSession(
        user_id="test-user",
        title="Test Session",
        model="Saptiva Turbo",
        state="active"
    ).insert()

    # Simulate first message with file_id_1
    file_id_1 = "file_001_primera"
    metadata_1 = {
        "file_ids": [file_id_1],
        "files": [{
            "file_id": file_id_1,
            "filename": "primera.png",
            "bytes": 1024,
            "mimetype": "image/png"
        }]
    }

    msg_1 = await chat_service.add_user_message(
        session,
        "¿Qué dice esta imagen?",
        metadata=metadata_1
    )

    assert msg_1.file_ids == [file_id_1]
    assert len(msg_1.files) == 1
    assert msg_1.files[0].filename == "primera.png"

    # Simulate second message with file_id_2 (different file)
    file_id_2 = "file_002_segunda"
    metadata_2 = {
        "file_ids": [file_id_2],
        "files": [{
            "file_id": file_id_2,
            "filename": "segunda.png",
            "bytes": 2048,
            "mimetype": "image/png"
        }]
    }

    msg_2 = await chat_service.add_user_message(
        session,
        "¿Y ahora qué dice?",
        metadata=metadata_2
    )

    # CRITICAL: Second message should have ONLY file_id_2, not file_id_1
    assert msg_2.file_ids == [file_id_2], \
        f"Expected only ['{file_id_2}'], got {msg_2.file_ids}"
    assert len(msg_2.files) == 1
    assert msg_2.files[0].filename == "segunda.png"

    # Verify first message was not modified
    msg_1_check = await ChatMessage.get(msg_1.id)
    assert msg_1_check.file_ids == [file_id_1]

    # Cleanup
    await session.delete()
    await msg_1.delete()
    await msg_2.delete()


@pytest.mark.asyncio
async def test_llm_serializer_includes_only_message_images():
    """
    Test that LLM serializer includes ONLY the images from each message.

    Validates no cross-message image inheritance.
    """
    from src.models.chat import ChatMessage, MessageRole
    from src.services.llm_message_serializer import serialize_message_for_llm

    # Message 1: with image
    msg_1 = ChatMessage(
        chat_id="test-chat",
        role=MessageRole.USER,
        content="Primera pregunta con imagen",
        file_ids=["file_001"]
    )

    # Message 2: with different image
    msg_2 = ChatMessage(
        chat_id="test-chat",
        role=MessageRole.USER,
        content="Segunda pregunta con otra imagen",
        file_ids=["file_002"]
    )

    # Mock presign to return predictable URLs
    with patch("src.services.llm_message_serializer.presign_file_url") as mock_presign:
        mock_presign.side_effect = lambda fid, uid: f"https://example.com/{fid}.png"

        # Serialize first message
        serialized_1 = await serialize_message_for_llm(msg_1, "test-user")
        assert serialized_1["role"] == "user"
        content_1 = serialized_1["content"]
        assert isinstance(content_1, list)

        image_parts_1 = [p for p in content_1 if p.get("type") == "input_image"]
        assert len(image_parts_1) == 1
        assert "file_001" in image_parts_1[0]["image_url"]

        # Serialize second message
        serialized_2 = await serialize_message_for_llm(msg_2, "test-user")
        content_2 = serialized_2["content"]
        image_parts_2 = [p for p in content_2 if p.get("type") == "input_image"]

        # CRITICAL: Second message should have ONLY file_002
        assert len(image_parts_2) == 1
        assert "file_002" in image_parts_2[0]["image_url"]
        assert "file_001" not in image_parts_2[0]["image_url"]


@pytest.mark.asyncio
async def test_build_llm_messages_no_accumulation():
    """
    Test that build_llm_messages_from_history maintains isolation per message.

    Each message carries only its own file_ids, no accumulation across turns.
    """
    from src.models.chat import ChatMessage, MessageRole
    from src.services.llm_message_serializer import build_llm_messages_from_history

    messages = [
        ChatMessage(
            chat_id="test-chat",
            role=MessageRole.USER,
            content="Turno 1",
            file_ids=["file_A"]
        ),
        ChatMessage(
            chat_id="test-chat",
            role=MessageRole.ASSISTANT,
            content="Respuesta 1",
            file_ids=[]
        ),
        ChatMessage(
            chat_id="test-chat",
            role=MessageRole.USER,
            content="Turno 2",
            file_ids=["file_B"]
        ),
    ]

    with patch("src.services.llm_message_serializer.presign_file_url") as mock_presign:
        mock_presign.side_effect = lambda fid, uid: f"https://example.com/{fid}.png"

        llm_messages = await build_llm_messages_from_history(messages, "test-user")

        assert len(llm_messages) == 3

        # First user message: only file_A
        content_0 = llm_messages[0]["content"]
        images_0 = [p for p in content_0 if isinstance(content_0, list) and p.get("type") == "input_image"]
        if images_0:
            assert len(images_0) == 1
            assert "file_A" in images_0[0]["image_url"]

        # Second user message: only file_B (no file_A)
        content_2 = llm_messages[2]["content"]
        images_2 = [p for p in content_2 if isinstance(content_2, list) and p.get("type") == "input_image"]
        if images_2:
            assert len(images_2) == 1
            assert "file_B" in images_2[0]["image_url"]
            # CRITICAL: file_A should NOT appear in second message
            assert all("file_A" not in p["image_url"] for p in images_2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
