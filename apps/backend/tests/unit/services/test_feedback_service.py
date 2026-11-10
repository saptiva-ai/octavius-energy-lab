"""
Unit tests for feedback_service module.

Tests:
- FeedbackContext dataclass
- EnrichedFeedback dataclass
- FeedbackService class
- feedback_service singleton
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.feedback import FeedbackRating
from src.services.feedback_service import (
    EnrichedFeedback,
    FeedbackContext,
    FeedbackService,
    feedback_service,
)

pytestmark = [pytest.mark.unit]


class TestFeedbackContext:
    """Test FeedbackContext dataclass."""

    def test_default_values(self):
        """Test default values are None."""
        context = FeedbackContext()
        assert context.original_query is None
        assert context.response_text is None
        assert context.sql_executed is None
        assert context.intent is None
        assert context.confidence is None
        assert context.data_returned is None

    def test_create_with_values(self):
        """Test creating with values."""
        context = FeedbackContext(
            original_query="What is availability?",
            response_text="Availability is...",
            sql_executed="SELECT * FROM metrics",
            intent="bank_metrics",
            confidence=0.95,
            data_returned={"metric": "disponibilidad"},
        )
        assert context.original_query == "What is availability?"
        assert context.response_text == "Availability is..."
        assert context.sql_executed == "SELECT * FROM metrics"
        assert context.intent == "bank_metrics"
        assert context.confidence == 0.95
        assert context.data_returned == {"metric": "disponibilidad"}

    def test_to_dict_with_all_values(self):
        """Test to_dict includes all non-None values."""
        context = FeedbackContext(
            original_query="What is availability?",
            response_text="Availability is...",
            sql_executed="SELECT * FROM metrics",
            intent="bank_metrics",
            confidence=0.95,
            data_returned={"metric": "disponibilidad"},
        )
        result = context.to_dict()

        assert result["original_query"] == "What is availability?"
        assert result["response_text"] == "Availability is..."
        assert result["sql_executed"] == "SELECT * FROM metrics"
        assert result["intent"] == "bank_metrics"
        assert result["confidence"] == 0.95
        assert result["data_returned"] == {"metric": "disponibilidad"}

    def test_to_dict_excludes_none_values(self):
        """Test to_dict excludes None values."""
        context = FeedbackContext(
            original_query="What is availability?",
            response_text=None,
        )
        result = context.to_dict()

        assert "original_query" in result
        assert "response_text" not in result
        assert "sql_executed" not in result

    def test_to_dict_empty_context(self):
        """Test to_dict with empty context."""
        context = FeedbackContext()
        result = context.to_dict()
        assert result == {}


class TestEnrichedFeedback:
    """Test EnrichedFeedback dataclass."""

    def test_create_with_required_fields(self):
        """Test creating with required fields."""
        feedback = EnrichedFeedback(
            message_id="msg_123",
            conversation_id="conv_456",
            user_id="user_789",
            rating=FeedbackRating.UP,
        )
        assert feedback.message_id == "msg_123"
        assert feedback.conversation_id == "conv_456"
        assert feedback.user_id == "user_789"
        assert feedback.rating == FeedbackRating.UP
        assert feedback.reason is None
        assert feedback.context is None

    def test_create_with_all_fields(self):
        """Test creating with all fields."""
        context = FeedbackContext(original_query="Test query")
        feedback = EnrichedFeedback(
            message_id="msg_123",
            conversation_id="conv_456",
            user_id="user_789",
            rating=FeedbackRating.DOWN,
            reason="Incorrect answer",
            context=context,
        )
        assert feedback.reason == "Incorrect answer"
        assert feedback.context is not None

    def test_to_dict_with_required_fields(self):
        """Test to_dict with required fields only."""
        feedback = EnrichedFeedback(
            message_id="msg_123",
            conversation_id="conv_456",
            user_id="user_789",
            rating=FeedbackRating.UP,
        )
        result = feedback.to_dict()

        assert result["message_id"] == "msg_123"
        assert result["conversation_id"] == "conv_456"
        assert result["user_id"] == "user_789"
        assert result["rating"] == FeedbackRating.UP.value
        assert "reason" not in result
        assert "context" not in result

    def test_to_dict_with_reason(self):
        """Test to_dict includes reason when set."""
        feedback = EnrichedFeedback(
            message_id="msg_123",
            conversation_id="conv_456",
            user_id="user_789",
            rating=FeedbackRating.DOWN,
            reason="Wrong data",
        )
        result = feedback.to_dict()

        assert result["reason"] == "Wrong data"

    def test_to_dict_with_context(self):
        """Test to_dict includes context when set."""
        context = FeedbackContext(
            original_query="Test query",
            intent="bank_metrics",
        )
        feedback = EnrichedFeedback(
            message_id="msg_123",
            conversation_id="conv_456",
            user_id="user_789",
            rating=FeedbackRating.UP,
            context=context,
        )
        result = feedback.to_dict()

        assert "context" in result
        assert result["context"]["original_query"] == "Test query"
        assert result["context"]["intent"] == "bank_metrics"

    def test_to_dict_rating_string_value(self):
        """Test to_dict handles string rating value."""
        feedback = EnrichedFeedback(
            message_id="msg_123",
            conversation_id="conv_456",
            user_id="user_789",
            rating="thumbs_up",  # String instead of enum
        )
        result = feedback.to_dict()
        assert result["rating"] == "thumbs_up"


class TestFeedbackServiceGetContextForMessage:
    """Test FeedbackService.get_context_for_message method."""

    @pytest.mark.asyncio
    async def test_returns_none_when_message_not_found(self):
        """Test returns None when message not found."""
        service = FeedbackService()

        with patch.object(
            service, "_get_message", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            result = await service.get_context_for_message(
                message_id="msg_123",
                conversation_id="conv_456",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_returns_context_with_message_data(self):
        """Test returns context with message data."""
        service = FeedbackService()

        mock_message = MagicMock()
        mock_message.content = "Assistant response"
        mock_message.metadata = {
            "sql_query": "SELECT * FROM metrics",
            "intent": "bank_metrics",
            "confidence": 0.95,
            "chart_data": {"metric": "disponibilidad"},
        }

        mock_user_message = MagicMock()
        mock_user_message.content = "User question"

        with patch.object(
            service, "_get_message", new_callable=AsyncMock
        ) as mock_get, patch.object(
            service, "_get_previous_user_message", new_callable=AsyncMock
        ) as mock_get_user:
            mock_get.return_value = mock_message
            mock_get_user.return_value = mock_user_message

            result = await service.get_context_for_message(
                message_id="msg_123",
                conversation_id="conv_456",
            )

            assert isinstance(result, FeedbackContext)
            assert result.original_query == "User question"
            assert result.response_text == "Assistant response"
            assert result.sql_executed == "SELECT * FROM metrics"
            assert result.intent == "bank_metrics"
            assert result.confidence == 0.95
            assert result.data_returned == {"metric": "disponibilidad"}

    @pytest.mark.asyncio
    async def test_handles_no_metadata(self):
        """Test handles message without metadata."""
        service = FeedbackService()

        mock_message = MagicMock()
        mock_message.content = "Response"
        mock_message.metadata = None

        with patch.object(
            service, "_get_message", new_callable=AsyncMock
        ) as mock_get, patch.object(
            service, "_get_previous_user_message", new_callable=AsyncMock
        ) as mock_get_user:
            mock_get.return_value = mock_message
            mock_get_user.return_value = None

            result = await service.get_context_for_message(
                message_id="msg_123",
                conversation_id="conv_456",
            )

            assert result.response_text == "Response"
            assert result.sql_executed is None
            assert result.original_query is None

    @pytest.mark.asyncio
    async def test_handles_empty_metadata(self):
        """Test handles message with empty metadata."""
        service = FeedbackService()

        mock_message = MagicMock()
        mock_message.content = "Response"
        mock_message.metadata = {}

        with patch.object(
            service, "_get_message", new_callable=AsyncMock
        ) as mock_get, patch.object(
            service, "_get_previous_user_message", new_callable=AsyncMock
        ) as mock_get_user:
            mock_get.return_value = mock_message
            mock_get_user.return_value = None

            result = await service.get_context_for_message(
                message_id="msg_123",
                conversation_id="conv_456",
            )

            assert result.sql_executed is None
            assert result.intent is None


class TestFeedbackServiceEnrichFeedback:
    """Test FeedbackService.enrich_feedback method."""

    @pytest.mark.asyncio
    async def test_creates_enriched_feedback(self):
        """Test creates EnrichedFeedback with context."""
        service = FeedbackService()
        mock_context = FeedbackContext(original_query="Test")

        with patch.object(
            service, "get_context_for_message", new_callable=AsyncMock
        ) as mock_get_context:
            mock_get_context.return_value = mock_context

            result = await service.enrich_feedback(
                message_id="msg_123",
                conversation_id="conv_456",
                user_id="user_789",
                rating=FeedbackRating.UP,
                reason="Great answer",
            )

            assert isinstance(result, EnrichedFeedback)
            assert result.message_id == "msg_123"
            assert result.conversation_id == "conv_456"
            assert result.user_id == "user_789"
            assert result.rating == FeedbackRating.UP
            assert result.reason == "Great answer"
            assert result.context is mock_context

    @pytest.mark.asyncio
    async def test_handles_no_context(self):
        """Test handles when context is None."""
        service = FeedbackService()

        with patch.object(
            service, "get_context_for_message", new_callable=AsyncMock
        ) as mock_get_context:
            mock_get_context.return_value = None

            result = await service.enrich_feedback(
                message_id="msg_123",
                conversation_id="conv_456",
                user_id="user_789",
                rating=FeedbackRating.DOWN,
            )

            assert result.context is None
            assert result.reason is None


class TestFeedbackServiceGetMessage:
    """Test FeedbackService._get_message method."""

    @pytest.mark.asyncio
    async def test_returns_message(self):
        """Test returns message when found."""
        service = FeedbackService()
        mock_message = MagicMock()

        with patch(
            "src.services.feedback_service.ChatMessage"
        ) as mock_chat_message:
            mock_chat_message.get = AsyncMock(return_value=mock_message)

            result = await service._get_message("msg_123")

            assert result is mock_message

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        """Test returns None on error."""
        service = FeedbackService()

        with patch(
            "src.services.feedback_service.ChatMessage"
        ) as mock_chat_message:
            mock_chat_message.get = AsyncMock(side_effect=Exception("DB error"))

            result = await service._get_message("msg_123")

            assert result is None


class TestFeedbackServiceGetPreviousUserMessage:
    """Test FeedbackService._get_previous_user_message method."""

    @pytest.mark.asyncio
    async def test_returns_previous_user_message(self):
        """Test returns the user message before the rated message."""
        service = FeedbackService()

        mock_user_msg = MagicMock()
        mock_user_msg.created_at = datetime(2024, 1, 1, 10, 0, 0)

        mock_rated_msg = MagicMock()
        mock_rated_msg.created_at = datetime(2024, 1, 1, 10, 5, 0)

        mock_query = MagicMock()
        mock_query.sort = MagicMock(return_value=mock_query)
        mock_query.limit = MagicMock(return_value=mock_query)
        mock_query.to_list = AsyncMock(return_value=[mock_user_msg])

        with patch(
            "src.services.feedback_service.ChatMessage"
        ) as mock_chat_message:
            mock_chat_message.find = MagicMock(return_value=mock_query)
            mock_chat_message.get = AsyncMock(return_value=mock_rated_msg)

            result = await service._get_previous_user_message(
                conversation_id="conv_123",
                before_message_id="msg_456",
            )

            assert result is mock_user_msg

    @pytest.mark.asyncio
    async def test_returns_none_when_no_user_messages(self):
        """Test returns None when no user messages exist."""
        service = FeedbackService()

        mock_query = MagicMock()
        mock_query.sort = MagicMock(return_value=mock_query)
        mock_query.limit = MagicMock(return_value=mock_query)
        mock_query.to_list = AsyncMock(return_value=[])

        with patch(
            "src.services.feedback_service.ChatMessage"
        ) as mock_chat_message:
            mock_chat_message.find = MagicMock(return_value=mock_query)

            result = await service._get_previous_user_message(
                conversation_id="conv_123",
                before_message_id="msg_456",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_fallback_when_rated_message_not_found(self):
        """Test returns most recent user message as fallback."""
        service = FeedbackService()

        mock_user_msg = MagicMock()

        mock_query = MagicMock()
        mock_query.sort = MagicMock(return_value=mock_query)
        mock_query.limit = MagicMock(return_value=mock_query)
        mock_query.to_list = AsyncMock(return_value=[mock_user_msg])

        with patch(
            "src.services.feedback_service.ChatMessage"
        ) as mock_chat_message:
            mock_chat_message.find = MagicMock(return_value=mock_query)
            mock_chat_message.get = AsyncMock(return_value=None)

            result = await service._get_previous_user_message(
                conversation_id="conv_123",
                before_message_id="msg_456",
            )

            assert result is mock_user_msg

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        """Test returns None on error."""
        service = FeedbackService()

        with patch(
            "src.services.feedback_service.ChatMessage"
        ) as mock_chat_message:
            mock_chat_message.find = MagicMock(
                side_effect=Exception("DB error")
            )

            result = await service._get_previous_user_message(
                conversation_id="conv_123",
                before_message_id="msg_456",
            )

            assert result is None


class TestFeedbackServiceSingleton:
    """Test feedback_service singleton."""

    def test_singleton_is_feedback_service(self):
        """Test singleton is FeedbackService instance."""
        assert isinstance(feedback_service, FeedbackService)
