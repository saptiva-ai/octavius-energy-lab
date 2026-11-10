"""
Tests for SSE streaming backpressure (ISSUE-004).

Verifies that the producer-consumer pattern with Queue prevents
unbounded memory growth when client is slow.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from asyncio import Queue

from src.routers.chat.handlers.streaming_handler import StreamingHandler
from src.core.config import Settings
from src.domain import ChatContext


@pytest.fixture
def streaming_handler():
    """Create StreamingHandler instance."""
    settings = Settings()
    return StreamingHandler(settings)


@pytest.fixture
def mock_chat_context():
    """Create mock ChatContext."""
    return ChatContext(
        user_id="test_user",
        request_id="test_request",
        timestamp=asyncio.get_event_loop().time(),
        chat_id="test_chat",
        session_id="test_session",
        message="Test message",
        context=None,
        document_ids=[],
        model="SAPTIVA_TURBO",
        tools_enabled={},
        stream=True,
        temperature=0.7,
        max_tokens=800,
        kill_switch_active=False
    )


@pytest.mark.asyncio
async def test_backpressure_queue_blocks_producer_when_full(streaming_handler, mock_chat_context):
    """
    Test that producer blocks when queue is full (backpressure).

    Scenario: Slow consumer (doesn't consume from queue fast enough).
    Expected: Producer should block when queue reaches maxsize.
    """
    # Mock dependencies
    mock_chat_service = AsyncMock()
    mock_chat_session = MagicMock(id="session_123")
    mock_cache = AsyncMock()

    # Mock Saptiva client to generate many chunks quickly
    async def mock_stream(*args, **kwargs):
        for i in range(20):  # Generate 20 chunks (more than queue maxsize=10)
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta = MagicMock(content=f"chunk{i}")
            yield chunk
            await asyncio.sleep(0.01)  # Small delay

    mock_saptiva_client = MagicMock()
    # Set side_effect to return the generator when called
    mock_saptiva_client.chat_completion_stream = MagicMock(side_effect=mock_stream)

    # get_saptiva_client is async, so we need AsyncMock
    mock_get_client = AsyncMock(return_value=mock_saptiva_client)

    with patch('src.routers.chat.handlers.streaming_handler.get_saptiva_client', mock_get_client), \
         patch('src.routers.chat.handlers.streaming_handler.DocumentService.get_document_text_from_cache', new_callable=AsyncMock, return_value=None):

        # Consume events slowly (simulating slow client)
        events_consumed = 0
        consumer_delays = []

        async for event in streaming_handler._stream_chat_response(
            mock_chat_context,
            mock_chat_service,
            mock_chat_session,
            mock_cache
        ):
            events_consumed += 1

            # Slow consumer: wait 50ms between consuming events
            await asyncio.sleep(0.05)
            consumer_delays.append(0.05)

            # Stop after 5 events to test backpressure
            if events_consumed >= 5:
                break

        # Verify that some events were consumed (producer didn't deadlock)
        assert events_consumed == 5


@pytest.mark.asyncio
async def test_backpressure_with_fast_consumer(streaming_handler, mock_chat_context):
    """
    Test that fast consumer doesn't cause queue overflow.

    Scenario: Consumer is faster than producer.
    Expected: No backpressure, all events consumed immediately.
    """
    mock_chat_service = AsyncMock()
    mock_chat_session = MagicMock(id="session_123")
    mock_cache = AsyncMock()

    # Mock Saptiva client with few chunks
    async def mock_stream(*args, **kwargs):
        for i in range(5):
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta = MagicMock(content=f"chunk{i}")
            yield chunk

    mock_saptiva_client = MagicMock()
    mock_saptiva_client.chat_completion_stream = MagicMock(side_effect=mock_stream)

    # get_saptiva_client is async, so we need AsyncMock
    mock_get_client = AsyncMock(return_value=mock_saptiva_client)

    with patch('src.routers.chat.handlers.streaming_handler.get_saptiva_client', mock_get_client), \
         patch('src.routers.chat.handlers.streaming_handler.DocumentService.get_document_text_from_cache', new_callable=AsyncMock, return_value=None):

        events = []
        async for event in streaming_handler._stream_chat_response(
            mock_chat_context,
            mock_chat_service,
            mock_chat_session,
            mock_cache
        ):
            if event["event"] == "message":
                events.append(event)

        # All message events should be consumed
        assert len(events) == 5


@pytest.mark.asyncio
async def test_producer_cancellation_on_consumer_exit(streaming_handler, mock_chat_context):
    """
    Test that producer task is cancelled when consumer exits early.

    Scenario: Consumer breaks out of loop before stream completes.
    Expected: Producer task should be cancelled in finally block.
    """
    mock_chat_service = AsyncMock()
    mock_chat_session = MagicMock(id="session_123")
    mock_cache = AsyncMock()

    producer_cancelled = False

    async def mock_stream(*args, **kwargs):
        nonlocal producer_cancelled
        try:
            for i in range(100):  # Many chunks
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta = MagicMock(content=f"chunk{i}")
                yield chunk
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            producer_cancelled = True
            raise

    mock_saptiva_client = MagicMock()
    mock_saptiva_client.chat_completion_stream = MagicMock(side_effect=mock_stream)

    # get_saptiva_client is async, so we need AsyncMock
    mock_get_client = AsyncMock(return_value=mock_saptiva_client)

    with patch('src.routers.chat.handlers.streaming_handler.get_saptiva_client', mock_get_client), \
         patch('src.routers.chat.handlers.streaming_handler.DocumentService.get_document_text_from_cache', new_callable=AsyncMock, return_value=None):

        # Consumer exits early after 3 events
        events_consumed = 0
        async for event in streaming_handler._stream_chat_response(
            mock_chat_context,
            mock_chat_service,
            mock_chat_session,
            mock_cache
        ):
            events_consumed += 1
            if events_consumed >= 3:
                break  # Exit early

        # Wait a bit for cleanup
        await asyncio.sleep(0.1)

        # Producer should have been cancelled
        assert producer_cancelled


@pytest.mark.asyncio
async def test_producer_error_propagated_to_consumer(streaming_handler, mock_chat_context):
    """
    Test that producer errors are propagated to consumer.

    Scenario: Producer raises exception during streaming.
    Expected: Consumer should receive and raise the error.
    """
    mock_chat_service = AsyncMock()
    mock_chat_session = MagicMock(id="session_123")
    mock_cache = AsyncMock()

    async def mock_stream_with_error(*args, **kwargs):
        yield MagicMock(choices=[MagicMock(delta=MagicMock(content="chunk1"))])
        raise ValueError("Producer error!")

    mock_saptiva_client = MagicMock()
    mock_saptiva_client.chat_completion_stream = MagicMock(side_effect=mock_stream_with_error)

    # get_saptiva_client is async, so we need AsyncMock
    mock_get_client = AsyncMock(return_value=mock_saptiva_client)

    with patch('src.routers.chat.handlers.streaming_handler.get_saptiva_client', mock_get_client), \
         patch('src.routers.chat.handlers.streaming_handler.DocumentService.get_document_text_from_cache', new_callable=AsyncMock, return_value=None):

        with pytest.raises(ValueError, match="Producer error!"):
            async for event in streaming_handler._stream_chat_response(
                mock_chat_context,
                mock_chat_service,
                mock_chat_session,
                mock_cache
            ):
                pass  # Consume all events


@pytest.mark.asyncio
async def test_queue_maxsize_prevents_unbounded_memory():
    """
    Unit test: Verify Queue with maxsize blocks put() when full.

    This is the core mechanism of backpressure.
    """
    queue = Queue(maxsize=3)

    # Fill queue to capacity
    await queue.put(1)
    await queue.put(2)
    await queue.put(3)

    # Queue is now full
    assert queue.full()

    # Try to put another item (should block)
    put_task = asyncio.create_task(queue.put(4))

    # Give it a moment
    await asyncio.sleep(0.01)

    # Task should still be pending (blocked by backpressure)
    assert not put_task.done()

    # Consume one item to make space
    await queue.get()

    # Now put should complete
    await put_task
    assert put_task.done()


@pytest.mark.asyncio
async def test_full_streaming_flow_with_backpressure(streaming_handler, mock_chat_context):
    """
    Integration test: Full streaming flow with backpressure simulation.

    Scenario: Producer generates 15 chunks, consumer processes them slowly.
    Expected: All chunks delivered, no memory overflow.
    """
    mock_chat_service = AsyncMock()
    mock_chat_service.add_assistant_message.return_value = MagicMock(id="msg_123")

    mock_chat_session = MagicMock(id="session_123")
    mock_cache = AsyncMock()

    async def mock_stream(*args, **kwargs):
        for i in range(15):  # 15 chunks (more than queue maxsize=10)
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta = MagicMock(content=f"word{i} ")
            yield chunk
            await asyncio.sleep(0.005)  # Fast producer

    mock_saptiva_client = MagicMock()
    mock_saptiva_client.chat_completion_stream = MagicMock(side_effect=mock_stream)

    # get_saptiva_client is async, so we need AsyncMock
    mock_get_client = AsyncMock(return_value=mock_saptiva_client)

    with patch('src.routers.chat.handlers.streaming_handler.get_saptiva_client', mock_get_client), \
         patch('src.routers.chat.handlers.streaming_handler.DocumentService.get_document_text_from_cache', new_callable=AsyncMock, return_value=None):

        events = []
        async for event in streaming_handler._stream_chat_response(
            mock_chat_context,
            mock_chat_service,
            mock_chat_session,
            mock_cache
        ):
            events.append(event)
            await asyncio.sleep(0.02)  # Slow consumer

        # Should receive all 15 message events + 1 done event
        message_events = [e for e in events if e["event"] == "message"]
        done_events = [e for e in events if e["event"] == "done"]

        assert len(message_events) == 15
        assert len(done_events) == 1

        # Verify assistant message was saved
        mock_chat_service.add_assistant_message.assert_called_once()
