"""
Integration test for history bug fix.

This test reproduces the bug where assistant messages don't appear in the unified history.

Bug: Only user messages were being recorded in history_events, assistant messages were missing.
Fix: Add HistoryService.record_chat_message() call in add_assistant_message method.
"""

import pytest
from datetime import datetime
from bson import ObjectId

from src.models.chat import ChatSession as ChatSessionModel, MessageRole, MessageStatus
from src.models.history import HistoryEvent, HistoryEventType
from src.services.chat_service import ChatService
from src.services.history_service import HistoryService


@pytest.mark.asyncio
@pytest.mark.integration
class TestHistoryBugFix:
    """Tests to verify the history bug is fixed."""

    async def test_assistant_messages_appear_in_unified_history(self):
        """
        Test that assistant messages are recorded in the unified history.

        This test reproduces the reported bug where only user messages
        appeared in the chat history.

        Expected behavior:
        - User message recorded in history_events ✓
        - Assistant message recorded in history_events ✓ (was missing before fix)
        """
        # Arrange: Create test session
        chat_session = ChatSessionModel(
            id=str(ObjectId()),
            user_id="test-user-123",
            title="Test Chat",
            model="saptiva-turbo",
            message_count=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        await chat_session.insert()

        from src.core.config import get_settings
        settings = get_settings()
        chat_service = ChatService(settings=settings)

        # Act: Simulate a conversation
        # 1. User sends message
        user_msg = await chat_service.add_user_message(
            chat_session=chat_session,
            content="Hola, ¿cómo estás?",
            metadata={"file_ids": [], "files": []}
        )

        # 2. Assistant responds
        assistant_msg = await chat_service.add_assistant_message(
            chat_session=chat_session,
            content="¡Hola! Estoy bien, gracias. ¿En qué puedo ayudarte hoy?",
            model="saptiva-turbo",
            tokens=20,  # Total token count
            latency_ms=450
        )

        # Assert: Check unified history timeline
        timeline = await HistoryService.get_chat_timeline(
            chat_id=chat_session.id,
            limit=10,
            offset=0,
            event_types=[HistoryEventType.CHAT_MESSAGE],
            use_cache=False  # Ensure fresh data
        )

        events = timeline["events"]

        # Should have 2 events (user + assistant)
        assert len(events) == 2, (
            f"Expected 2 events in timeline (user + assistant), "
            f"got {len(events)}. This indicates the bug is NOT fixed."
        )

        # Verify user message is in history
        user_events = [e for e in events if e.get("chat_data", {}).get("role") == "user"]
        assert len(user_events) == 1, "User message not found in history"
        assert user_events[0]["chat_data"]["content"] == "Hola, ¿cómo estás?"

        # Verify assistant message is in history (THIS SHOULD FAIL BEFORE FIX)
        assistant_events = [e for e in events if e.get("chat_data", {}).get("role") == "assistant"]
        assert len(assistant_events) == 1, (
            "Assistant message not found in history. "
            "Bug: add_assistant_message is not calling HistoryService.record_chat_message()"
        )
        assert assistant_events[0]["chat_data"]["content"] == "¡Hola! Estoy bien, gracias. ¿En qué puedo ayudarte hoy?"

        # Verify chronological order
        assert events[0]["timestamp"] <= events[1]["timestamp"], "Events not in chronological order"

        # Cleanup
        await chat_session.delete()
        await HistoryEvent.find(HistoryEvent.chat_id == chat_session.id).delete()

    async def test_multi_turn_conversation_history(self):
        """
        Test that a multi-turn conversation is fully recorded in history.

        Conversation:
        User: "What is Python?"
        Assistant: "Python is a programming language..."
        User: "Show me an example"
        Assistant: "Here's an example: print('hello')"

        All 4 messages should appear in unified history.
        """
        # Arrange
        chat_session = ChatSessionModel(
            id=str(ObjectId()),
            user_id="test-user-456",
            title="Python Tutorial",
            model="saptiva-cortex",
            message_count=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        await chat_session.insert()

        from src.core.config import get_settings
        settings = get_settings()
        chat_service = ChatService(settings=settings)

        # Act: Simulate 2-turn conversation
        # Turn 1
        await chat_service.add_user_message(
            chat_session=chat_session,
            content="What is Python?",
            metadata={"file_ids": [], "files": []}
        )

        await chat_service.add_assistant_message(
            chat_session=chat_session,
            content="Python is a high-level programming language known for its simplicity.",
            model="saptiva-cortex",
            tokens=25,  # Total token count
            latency_ms=600
        )

        # Turn 2
        await chat_service.add_user_message(
            chat_session=chat_session,
            content="Show me an example",
            metadata={"file_ids": [], "files": []}
        )

        await chat_service.add_assistant_message(
            chat_session=chat_session,
            content="Here's an example:\n\nprint('Hello, World!')",
            model="saptiva-cortex",
            tokens=18,  # Total token count
            latency_ms=400
        )

        # Assert: Check timeline has all 4 messages
        timeline = await HistoryService.get_chat_timeline(
            chat_id=chat_session.id,
            limit=50,
            offset=0,
            event_types=[HistoryEventType.CHAT_MESSAGE],
            use_cache=False
        )

        events = timeline["events"]

        # Should have 4 messages total
        assert len(events) == 4, f"Expected 4 messages, got {len(events)}"

        # Count by role
        user_count = len([e for e in events if e.get("chat_data", {}).get("role") == "user"])
        assistant_count = len([e for e in events if e.get("chat_data", {}).get("role") == "assistant"])

        assert user_count == 2, f"Expected 2 user messages, got {user_count}"
        assert assistant_count == 2, f"Expected 2 assistant messages, got {assistant_count}"

        # Verify conversation order
        contents = [e["chat_data"]["content"] for e in events]
        assert "What is Python?" in contents[0]
        assert "Python is a high-level" in contents[1]
        assert "Show me an example" in contents[2]
        assert "Hello, World!" in contents[3]

        # Cleanup
        await chat_session.delete()
        await HistoryEvent.find(HistoryEvent.chat_id == chat_session.id).delete()

    async def test_history_event_metadata_preserved(self):
        """
        Test that assistant message metadata is properly stored in history_events.

        Metadata includes:
        - tokens (prompt, completion, total)
        - latency_ms
        - model
        - status
        """
        # Arrange
        chat_session = ChatSessionModel(
            id=str(ObjectId()),
            user_id="test-user-789",
            title="Metadata Test",
            model="saptiva-turbo",
            message_count=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        await chat_session.insert()

        from src.core.config import get_settings
        settings = get_settings()
        chat_service = ChatService(settings=settings)

        # Act: Add assistant message with full metadata
        assistant_msg = await chat_service.add_assistant_message(
            chat_session=chat_session,
            content="This is a response with metadata",
            model="saptiva-turbo",
            tokens=30,  # Total token count
            latency_ms=1250,
            metadata={"temperature": 0.7, "max_tokens": 100}
        )

        # Assert: Verify metadata in history
        timeline = await HistoryService.get_chat_timeline(
            chat_id=chat_session.id,
            limit=10,
            offset=0,
            event_types=[HistoryEventType.CHAT_MESSAGE],
            use_cache=False
        )

        events = timeline["events"]
        assert len(events) == 1, "Assistant message not recorded"

        event = events[0]
        chat_data = event.get("chat_data", {})

        # Verify metadata is present
        assert chat_data.get("model") == "saptiva-turbo"
        assert chat_data.get("tokens") == 30  # Integer, not dict
        assert chat_data.get("latency_ms") == 1250

        # Verify message content
        assert chat_data.get("content") == "This is a response with metadata"
        assert chat_data.get("role") == "assistant"

        # Cleanup
        await chat_session.delete()
        await HistoryEvent.find(HistoryEvent.chat_id == chat_session.id).delete()

    async def test_history_cache_invalidation(self):
        """
        Test that cache is properly invalidated when assistant messages are added.

        This ensures that fresh data is returned after new messages.
        """
        # Arrange
        chat_session = ChatSessionModel(
            id=str(ObjectId()),
            user_id="test-user-cache",
            title="Cache Test",
            model="saptiva-turbo",
            message_count=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        await chat_session.insert()

        from src.core.config import get_settings
        settings = get_settings()
        chat_service = ChatService(settings=settings)

        # Act: Add first message and cache it
        await chat_service.add_user_message(
            chat_session=chat_session,
            content="First message",
            metadata={"file_ids": [], "files": []}
        )

        # Get timeline (will be cached)
        timeline1 = await HistoryService.get_chat_timeline(
            chat_id=chat_session.id,
            limit=10,
            offset=0,
            event_types=[HistoryEventType.CHAT_MESSAGE],
            use_cache=True
        )

        assert len(timeline1["events"]) == 1

        # Add assistant message (should invalidate cache)
        await chat_service.add_assistant_message(
            chat_session=chat_session,
            content="Second message (assistant)",
            model="saptiva-turbo",
            tokens=10,  # Total token count
            latency_ms=300
        )

        # Get timeline again (should have 2 messages, not cached 1)
        timeline2 = await HistoryService.get_chat_timeline(
            chat_id=chat_session.id,
            limit=10,
            offset=0,
            event_types=[HistoryEventType.CHAT_MESSAGE],
            use_cache=True
        )

        # Assert: Cache was invalidated, new data returned
        assert len(timeline2["events"]) == 2, (
            f"Cache not invalidated properly. Expected 2 events, got {len(timeline2['events'])}"
        )

        # Cleanup
        await chat_session.delete()
        await HistoryEvent.find(HistoryEvent.chat_id == chat_session.id).delete()


@pytest.mark.asyncio
@pytest.mark.integration
class TestHistoryEndpointConsistency:
    """Test that both history endpoints return consistent data."""

    async def test_direct_vs_unified_endpoint_consistency(self):
        """
        Test that /api/history/{chat_id} and /api/history/{chat_id}/unified
        return the same messages (just in different formats).

        Before fix: unified endpoint was missing assistant messages.
        After fix: both should show all messages.
        """
        # Arrange
        chat_session = ChatSessionModel(
            id=str(ObjectId()),
            user_id="test-consistency",
            title="Consistency Test",
            model="saptiva-turbo",
            message_count=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        await chat_session.insert()

        from src.core.config import get_settings
        settings = get_settings()
        chat_service = ChatService(settings=settings)

        # Act: Create conversation
        await chat_service.add_user_message(
            chat_session=chat_session,
            content="Hello",
            metadata={"file_ids": [], "files": []}
        )

        await chat_service.add_assistant_message(
            chat_session=chat_session,
            content="Hi there!",
            model="saptiva-turbo",
            tokens=5,  # Total token count
            latency_ms=200
        )

        # Get messages from direct endpoint (chat_messages collection)
        direct_messages = await HistoryService.get_chat_messages(
            chat_id=chat_session.id,
            limit=10,
            offset=0,
            include_system=False
        )

        # Get messages from unified endpoint (history_events collection)
        unified_timeline = await HistoryService.get_chat_timeline(
            chat_id=chat_session.id,
            limit=10,
            offset=0,
            event_types=[HistoryEventType.CHAT_MESSAGE],
            use_cache=False
        )

        # Assert: Both endpoints show same number of messages
        direct_count = len(direct_messages["messages"])
        unified_count = len(unified_timeline["events"])

        assert direct_count == unified_count == 2, (
            f"Inconsistency between endpoints: "
            f"direct={direct_count}, unified={unified_count}. "
            f"Expected both to be 2."
        )

        # Verify content matches
        # Note: direct_messages["messages"] returns ChatMessage objects, not dicts
        direct_contents = {msg.content if hasattr(msg, 'content') else msg["content"]
                          for msg in direct_messages["messages"]}
        unified_contents = {evt["chat_data"]["content"] for evt in unified_timeline["events"]}

        assert direct_contents == unified_contents, "Content mismatch between endpoints"

        # Cleanup
        await chat_session.delete()
        await HistoryEvent.find(HistoryEvent.chat_id == chat_session.id).delete()
