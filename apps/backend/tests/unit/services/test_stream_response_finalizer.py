"""
Unit tests for StreamResponseFinalizer - Post-streaming finalization service.

Tests cover:
- Producer task cleanup (done vs not-done)
- Response post-processing
- Message persistence and done event creation
- Full finalization flow
- Error handling
"""

import asyncio
import json
from asyncio import CancelledError, Task
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.streaming.stream_response_finalizer import (
    FinalizerContext,
    FinalizerResult,
    StreamResponseFinalizer,
)


@pytest.fixture
def mock_context():
    """Create mock ChatContext."""
    ctx = MagicMock()
    ctx.user_id = "user-123"
    ctx.session_id = "session-123"
    ctx.model = "gpt-4"
    ctx.document_ids = ["doc-1", "doc-2"]
    return ctx


@pytest.fixture
def mock_chat_session():
    """Create mock ChatSession."""
    session = MagicMock()
    session.id = "chat-456"
    return session


@pytest.fixture
def mock_chat_service():
    """Create mock ChatService."""
    service = AsyncMock()
    message = MagicMock()
    message.id = "msg-789"
    service.add_assistant_message.return_value = message
    return service


@pytest.fixture
def mock_cache():
    """Create mock Redis cache."""
    cache = AsyncMock()
    cache.invalidate_chat_history = AsyncMock()
    return cache


@pytest.fixture
def finalizer_context(mock_context, mock_chat_session, mock_chat_service, mock_cache):
    """Create FinalizerContext with all dependencies."""
    return FinalizerContext(
        context=mock_context,
        chat_session=mock_chat_session,
        chat_service=mock_chat_service,
        cache=mock_cache,
        doc_warnings=["Warning 1"],
    )


@pytest.mark.unit
class TestFinalizerDataclasses:
    """Tests for FinalizerContext and FinalizerResult dataclasses."""

    def test_finalizer_context_creation(self, mock_context, mock_chat_session):
        """Should create FinalizerContext with all fields."""
        ctx = FinalizerContext(
            context=mock_context,
            chat_session=mock_chat_session,
            chat_service=MagicMock(),
            cache=MagicMock(),
            doc_warnings=["warning"],
        )

        assert ctx.context == mock_context
        assert ctx.chat_session == mock_chat_session
        assert ctx.doc_warnings == ["warning"]

    def test_finalizer_context_with_none_values(self, mock_context, mock_chat_session):
        """Should create FinalizerContext with None optional fields."""
        ctx = FinalizerContext(
            context=mock_context,
            chat_session=mock_chat_session,
            chat_service=MagicMock(),
            cache=MagicMock(),
            doc_warnings=None,
        )

        assert ctx.doc_warnings is None

    def test_finalizer_result_success(self):
        """Should create successful FinalizerResult."""
        result = FinalizerResult(
            full_response="Hello world",
            assistant_message=MagicMock(),
            done_event={"event": "done"},
        )

        assert result.full_response == "Hello world"
        assert result.error is None
        assert result.fallback_chunk is None

    def test_finalizer_result_with_error(self):
        """Should create FinalizerResult with error."""
        error = Exception("Something failed")
        result = FinalizerResult(
            full_response="",
            assistant_message=None,
            done_event={},
            error=error,
        )

        assert result.error == error

    def test_finalizer_result_with_fallback_chunk(self):
        """Should create FinalizerResult with fallback chunk."""
        fallback = {"event": "chunk", "data": "fallback content"}
        result = FinalizerResult(
            full_response="fallback content",
            assistant_message=MagicMock(),
            done_event={"event": "done"},
            fallback_chunk=fallback,
        )

        assert result.fallback_chunk == fallback


@pytest.mark.unit
class TestCleanupProducer:
    """Tests for cleanup_producer method."""

    @pytest.mark.asyncio
    async def test_cleanup_completed_task(self):
        """Should extract result from completed task."""
        # Create mock producer result
        mock_result = MagicMock()
        mock_result.full_response = "Completed response"
        mock_result.error = None

        # Create completed task
        async def completed_coro():
            return mock_result

        task = asyncio.create_task(completed_coro())
        await asyncio.sleep(0.01)  # Let task complete

        result = await StreamResponseFinalizer.cleanup_producer(task)

        assert result == mock_result

    @pytest.mark.asyncio
    async def test_cleanup_running_task_cancels(self):
        """Should cancel and handle running task."""
        # Create long-running task
        async def long_running():
            await asyncio.sleep(10)
            return MagicMock()

        task = asyncio.create_task(long_running())
        await asyncio.sleep(0.01)  # Let task start

        result = await StreamResponseFinalizer.cleanup_producer(task)

        assert result is None
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_cleanup_with_producer_error(self):
        """Should raise error if producer had an error."""
        error = Exception("Producer failed")
        mock_result = MagicMock()
        mock_result.error = error

        async def completed_with_error():
            return mock_result

        task = asyncio.create_task(completed_with_error())
        await asyncio.sleep(0.01)

        with pytest.raises(Exception, match="Producer failed"):
            await StreamResponseFinalizer.cleanup_producer(task)

    @pytest.mark.asyncio
    async def test_cleanup_no_result_no_error(self):
        """Should handle None result without error."""
        async def returns_none():
            return None

        task = asyncio.create_task(returns_none())
        await asyncio.sleep(0.01)

        result = await StreamResponseFinalizer.cleanup_producer(task)

        assert result is None


@pytest.mark.unit
class TestPostProcessResponse:
    """Tests for post_process_response method."""

    def test_post_process_with_content(self, finalizer_context):
        """Should post-process response with content."""
        mock_producer_result = MagicMock()
        mock_producer_result.full_response = "Original response"

        with patch(
            "src.services.streaming.stream_response_finalizer.ResponsePostProcessor"
        ) as mock_processor:
            mock_post_result = MagicMock()
            mock_post_result.content = "Processed response"
            mock_post_result.was_empty = False
            mock_post_result.table_appended = None
            mock_processor.process.return_value = mock_post_result

            full_response, post_result, fallback = (
                StreamResponseFinalizer.post_process_response(
                    mock_producer_result, finalizer_context
                )
            )

            assert full_response == "Processed response"
            assert post_result == mock_post_result
            assert fallback is None

    def test_post_process_with_empty_response_creates_fallback(self, finalizer_context):
        """Should create fallback chunk for empty response."""
        mock_producer_result = MagicMock()
        mock_producer_result.full_response = ""

        with patch(
            "src.services.streaming.stream_response_finalizer.ResponsePostProcessor"
        ) as mock_processor:
            mock_post_result = MagicMock()
            mock_post_result.content = "Fallback content"
            mock_post_result.was_empty = True
            mock_post_result.table_appended = None
            mock_processor.process.return_value = mock_post_result

            full_response, _, fallback = StreamResponseFinalizer.post_process_response(
                mock_producer_result, finalizer_context
            )

            assert full_response == "Fallback content"
            assert fallback is not None
            assert fallback["event"] == "chunk"
            assert "Fallback content" in fallback["data"]

    def test_post_process_none_producer_result(self, finalizer_context):
        """Should handle None producer result gracefully."""
        with patch(
            "src.services.streaming.stream_response_finalizer.ResponsePostProcessor"
        ) as mock_processor:
            mock_post_result = MagicMock()
            mock_post_result.content = ""
            mock_post_result.was_empty = True
            mock_post_result.table_appended = None
            mock_processor.process.return_value = mock_post_result

            full_response, _, fallback = (
                StreamResponseFinalizer.post_process_response(None, finalizer_context)
            )

            assert full_response == ""

    def test_post_process_passes_correct_context(self, finalizer_context):
        """Should pass correct context to ResponsePostProcessor."""
        mock_producer_result = MagicMock()
        mock_producer_result.full_response = "Test"

        with patch(
            "src.services.streaming.stream_response_finalizer.ResponsePostProcessor"
        ) as mock_processor:
            mock_post_result = MagicMock()
            mock_post_result.content = "Test"
            mock_post_result.was_empty = False
            mock_post_result.table_appended = None
            mock_processor.process.return_value = mock_post_result

            StreamResponseFinalizer.post_process_response(
                mock_producer_result, finalizer_context
            )

            call_kwargs = mock_processor.process.call_args.kwargs
            assert call_kwargs["response"] == "Test"
            assert call_kwargs["has_documents"] is True
            assert call_kwargs["doc_warnings"] == ["Warning 1"]
            assert call_kwargs["context"]["user_id"] == "user-123"
            assert call_kwargs["context"]["stream_mode"] is True


@pytest.mark.unit
class TestPersistAndFinalize:
    """Tests for persist_and_finalize method."""

    @pytest.mark.asyncio
    async def test_persist_without_chart_artifact(self, finalizer_context):
        """Should pass None artifact_id (no chart artifacts in de-banked flow)."""
        with patch(
            "src.services.streaming.stream_response_finalizer.MessagePersistenceService"
        ) as mock_persist:
            mock_persist.build_assistant_metadata.return_value = {"streaming": True}
            mock_persist.build_done_event.return_value = {"event": "done"}

            await StreamResponseFinalizer.persist_and_finalize(
                full_response="Response without chart",
                ctx=finalizer_context,
            )

            call_kwargs = mock_persist.build_assistant_metadata.call_args.kwargs
            assert call_kwargs["artifact_id"] is None

    @pytest.mark.asyncio
    async def test_persist_threads_retail_analytics(
        self, mock_context, mock_chat_session, mock_chat_service, mock_cache
    ):
        """El AnalyticsResponse crudo de ctx.retail_analytics debe llegar tanto a
        build_assistant_metadata (persistencia) como a build_done_event (SSE),
        para que el frontend lo reciba en el mismo turno sin esperar refresh."""
        analytics = {"metric_name": "disponibilidad", "chart_type": "bar"}
        ctx = FinalizerContext(
            context=mock_context,
            chat_session=mock_chat_session,
            chat_service=mock_chat_service,
            cache=mock_cache,
            doc_warnings=None,
            retail_analytics=analytics,
        )

        with patch(
            "src.services.streaming.stream_response_finalizer.MessagePersistenceService"
        ) as mock_persist:
            mock_persist.build_assistant_metadata.return_value = {"streaming": True}
            mock_persist.build_done_event.return_value = {"event": "done"}

            await StreamResponseFinalizer.persist_and_finalize(
                full_response="Response",
                ctx=ctx,
            )

            metadata_call_kwargs = mock_persist.build_assistant_metadata.call_args.kwargs
            assert metadata_call_kwargs["retail_analytics"] == analytics

            done_event_call_kwargs = mock_persist.build_done_event.call_args.kwargs
            assert done_event_call_kwargs["metadata"] == {"retail_analytics": analytics}

    @pytest.mark.asyncio
    async def test_persist_saves_message(self, finalizer_context):
        """Should save assistant message via chat service."""
        with patch(
            "src.services.streaming.stream_response_finalizer.MessagePersistenceService"
        ) as mock_persist:
            mock_persist.build_assistant_metadata.return_value = {"streaming": True}
            mock_persist.build_done_event.return_value = {"event": "done"}

            await StreamResponseFinalizer.persist_and_finalize(
                full_response="Test response",
                ctx=finalizer_context,
            )

            finalizer_context.chat_service.add_assistant_message.assert_called_once()
            call_kwargs = (
                finalizer_context.chat_service.add_assistant_message.call_args.kwargs
            )
            assert call_kwargs["content"] == "Test response"
            assert call_kwargs["model"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_persist_invalidates_cache(self, finalizer_context):
        """Should invalidate chat history cache."""
        with patch(
            "src.services.streaming.stream_response_finalizer.MessagePersistenceService"
        ) as mock_persist:
            mock_persist.build_assistant_metadata.return_value = {}
            mock_persist.build_done_event.return_value = {}

            await StreamResponseFinalizer.persist_and_finalize(
                full_response="Response",
                ctx=finalizer_context,
            )

            finalizer_context.cache.invalidate_chat_history.assert_called_once_with(
                "chat-456"
            )

    @pytest.mark.asyncio
    async def test_persist_returns_message_and_done_event(self, finalizer_context):
        """Should return assistant message and done event."""
        with patch(
            "src.services.streaming.stream_response_finalizer.MessagePersistenceService"
        ) as mock_persist:
            mock_persist.build_assistant_metadata.return_value = {}
            mock_persist.build_done_event.return_value = {
                "event": "done",
                "message_id": "msg-789",
            }

            message, done_event = await StreamResponseFinalizer.persist_and_finalize(
                full_response="Response",
                ctx=finalizer_context,
            )

            assert message is not None
            assert done_event["event"] == "done"


@pytest.mark.unit
class TestFinalize:
    """Tests for finalize method - main orchestration."""

    @pytest.mark.asyncio
    async def test_finalize_success_flow(self, finalizer_context):
        """Should complete full finalization successfully."""
        mock_producer_result = MagicMock()
        mock_producer_result.full_response = "Complete response"
        mock_producer_result.error = None

        async def producer_coro():
            return mock_producer_result

        task = asyncio.create_task(producer_coro())
        await asyncio.sleep(0.01)

        with patch(
            "src.services.streaming.stream_response_finalizer.ResponsePostProcessor"
        ) as mock_processor, patch(
            "src.services.streaming.stream_response_finalizer.MessagePersistenceService"
        ) as mock_persist:
            mock_post_result = MagicMock()
            mock_post_result.content = "Complete response"
            mock_post_result.was_empty = False
            mock_post_result.table_appended = None
            mock_processor.process.return_value = mock_post_result

            mock_persist.build_assistant_metadata.return_value = {}
            mock_persist.build_done_event.return_value = {"event": "done"}

            result = await StreamResponseFinalizer.finalize(task, finalizer_context)

            assert result.full_response == "Complete response"
            assert result.error is None
            assert result.assistant_message is not None

    @pytest.mark.asyncio
    async def test_finalize_with_producer_error(self, finalizer_context):
        """Should return error result when producer fails."""
        error = Exception("Producer error")
        mock_producer_result = MagicMock()
        mock_producer_result.error = error

        async def error_producer():
            return mock_producer_result

        task = asyncio.create_task(error_producer())
        await asyncio.sleep(0.01)

        result = await StreamResponseFinalizer.finalize(task, finalizer_context)

        assert result.error is not None
        assert result.full_response == ""

    @pytest.mark.asyncio
    async def test_finalize_with_fallback_chunk(self, finalizer_context):
        """Should include fallback chunk when response was empty."""
        mock_producer_result = MagicMock()
        mock_producer_result.full_response = ""
        mock_producer_result.error = None

        async def empty_producer():
            return mock_producer_result

        task = asyncio.create_task(empty_producer())
        await asyncio.sleep(0.01)

        with patch(
            "src.services.streaming.stream_response_finalizer.ResponsePostProcessor"
        ) as mock_processor, patch(
            "src.services.streaming.stream_response_finalizer.MessagePersistenceService"
        ) as mock_persist:
            mock_post_result = MagicMock()
            mock_post_result.content = "Fallback"
            mock_post_result.was_empty = True
            mock_post_result.table_appended = None
            mock_processor.process.return_value = mock_post_result

            mock_persist.build_assistant_metadata.return_value = {}
            mock_persist.build_done_event.return_value = {}

            result = await StreamResponseFinalizer.finalize(task, finalizer_context)

            assert result.fallback_chunk is not None
            assert result.fallback_chunk["event"] == "chunk"

    @pytest.mark.asyncio
    async def test_finalize_catches_unexpected_error(self, finalizer_context):
        """Should catch and return unexpected errors."""
        mock_producer_result = MagicMock()
        mock_producer_result.full_response = "Response"
        mock_producer_result.error = None

        async def producer():
            return mock_producer_result

        task = asyncio.create_task(producer())
        await asyncio.sleep(0.01)

        with patch(
            "src.services.streaming.stream_response_finalizer.ResponsePostProcessor"
        ) as mock_processor:
            mock_processor.process.side_effect = RuntimeError("Unexpected error")

            result = await StreamResponseFinalizer.finalize(task, finalizer_context)

            assert result.error is not None
            assert isinstance(result.error, RuntimeError)
            assert result.full_response == ""
