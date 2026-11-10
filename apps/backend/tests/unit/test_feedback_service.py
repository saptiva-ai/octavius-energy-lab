"""
Unit tests for FeedbackService - Context enrichment for feedback (CA-06).

Tests the service layer that enriches feedback with:
- Original user query
- Response text
- SQL executed (if applicable)
- Intent classification
- Confidence score
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional, Dict, Any

# Import the service we're testing (will fail until implemented)
from src.services.feedback_service import (
    FeedbackService,
    FeedbackContext,
    EnrichedFeedback,
)
from src.models.feedback import MessageFeedback, FeedbackRating


class TestFeedbackContext:
    """Tests for FeedbackContext dataclass."""

    def test_context_with_all_fields(self):
        """CA-06: Context includes original_query, response_text, sql."""
        context = FeedbackContext(
            original_query="Dame la disponibilidad de Tienda Centro en diciembre 2024",
            response_text="La disponibilidad de Tienda Centro en diciembre 2024 fue 2.34%.",
            sql_executed="SELECT disponibilidad FROM v_ventas_monthly WHERE tienda='Tienda Centro'",
            intent="SQL_QUERY",
            confidence=0.95,
            data_returned={"tienda": "Tienda Centro", "metric": "disponibilidad", "value": 2.34},
        )

        assert context.original_query == "Dame la disponibilidad de Tienda Centro en diciembre 2024"
        assert context.response_text.startswith("La disponibilidad")
        assert "SELECT" in context.sql_executed
        assert context.intent == "SQL_QUERY"
        assert context.confidence == 0.95
        assert context.data_returned["tienda"] == "Tienda Centro"

    def test_context_with_minimal_fields(self):
        """Context can be created with just query and response."""
        context = FeedbackContext(
            original_query="Hola",
            response_text="¡Hola! ¿En qué puedo ayudarte?",
        )

        assert context.original_query == "Hola"
        assert context.response_text == "¡Hola! ¿En qué puedo ayudarte?"
        assert context.sql_executed is None
        assert context.intent is None
        assert context.confidence is None
        assert context.data_returned is None

    def test_context_to_dict(self):
        """Context can be serialized to dict for MongoDB storage."""
        context = FeedbackContext(
            original_query="Test query",
            response_text="Test response",
            intent="GREETING",
            confidence=0.8,
        )

        result = context.to_dict()

        assert isinstance(result, dict)
        assert result["original_query"] == "Test query"
        assert result["response_text"] == "Test response"
        assert result["intent"] == "GREETING"
        assert result["confidence"] == 0.8


class TestFeedbackService:
    """Tests for FeedbackService."""

    @pytest.fixture
    def feedback_service(self):
        """Create FeedbackService instance."""
        return FeedbackService()

    @pytest.fixture
    def mock_chat_message(self):
        """Create mock ChatMessage for testing."""
        message = MagicMock()
        message.id = "msg_12345"
        message.chat_id = "conv_123"
        message.content = "La disponibilidad de Tienda Centro en diciembre 2024 fue 2.34%."
        message.role = MagicMock(value="assistant")
        message.metadata = {
            "chart_data": {"tienda": "Tienda Centro", "metric": "disponibilidad", "value": 2.34},
            "sql_query": "SELECT disponibilidad FROM v_ventas_monthly WHERE tienda='Tienda Centro'",
            "intent": "SQL_QUERY",
            "confidence": 0.95,
        }
        return message

    @pytest.fixture
    def mock_user_message(self):
        """Create mock user message (the original query)."""
        message = MagicMock()
        message.id = "msg_12344"
        message.chat_id = "conv_123"
        message.content = "Dame la disponibilidad de Tienda Centro en diciembre 2024"
        message.role = MagicMock(value="user")
        message.created_at = datetime(2024, 12, 1, 10, 0, 0)
        return message

    @pytest.mark.asyncio
    async def test_enrich_feedback_with_context(
        self, feedback_service, mock_chat_message, mock_user_message
    ):
        """CA-06: Feedback enriched with context from message."""
        with patch.object(
            feedback_service,
            "_get_message",
            new_callable=AsyncMock,
            return_value=mock_chat_message,
        ), patch.object(
            feedback_service,
            "_get_previous_user_message",
            new_callable=AsyncMock,
            return_value=mock_user_message,
        ):
            context = await feedback_service.get_context_for_message(
                message_id="msg_12345",
                conversation_id="conv_123",
            )

            assert context is not None
            assert context.original_query == "Dame la disponibilidad de Tienda Centro en diciembre 2024"
            assert context.response_text == "La disponibilidad de Tienda Centro en diciembre 2024 fue 2.34%."
            assert context.sql_executed == "SELECT disponibilidad FROM v_ventas_monthly WHERE tienda='Tienda Centro'"
            assert context.intent == "SQL_QUERY"
            assert context.confidence == 0.95
            assert context.data_returned["tienda"] == "Tienda Centro"

    @pytest.mark.asyncio
    async def test_enrich_feedback_message_not_found(self, feedback_service):
        """Returns None context when message not found."""
        with patch.object(
            feedback_service,
            "_get_message",
            new_callable=AsyncMock,
            return_value=None,
        ):
            context = await feedback_service.get_context_for_message(
                message_id="nonexistent",
                conversation_id="conv_123",
            )

            assert context is None

    @pytest.mark.asyncio
    async def test_enrich_feedback_no_previous_user_message(
        self, feedback_service, mock_chat_message
    ):
        """Context created even without previous user message."""
        with patch.object(
            feedback_service,
            "_get_message",
            new_callable=AsyncMock,
            return_value=mock_chat_message,
        ), patch.object(
            feedback_service,
            "_get_previous_user_message",
            new_callable=AsyncMock,
            return_value=None,
        ):
            context = await feedback_service.get_context_for_message(
                message_id="msg_12345",
                conversation_id="conv_123",
            )

            assert context is not None
            assert context.original_query is None
            assert context.response_text == "La disponibilidad de Tienda Centro en diciembre 2024 fue 2.34%."

    @pytest.mark.asyncio
    async def test_enrich_feedback_no_metadata(self, feedback_service, mock_user_message):
        """Context created even when message has no metadata."""
        message = MagicMock()
        message.id = "msg_12345"
        message.content = "Hello, how can I help?"
        message.role = MagicMock(value="assistant")
        message.metadata = None

        with patch.object(
            feedback_service,
            "_get_message",
            new_callable=AsyncMock,
            return_value=message,
        ), patch.object(
            feedback_service,
            "_get_previous_user_message",
            new_callable=AsyncMock,
            return_value=mock_user_message,
        ):
            context = await feedback_service.get_context_for_message(
                message_id="msg_12345",
                conversation_id="conv_123",
            )

            assert context is not None
            assert context.response_text == "Hello, how can I help?"
            assert context.sql_executed is None
            assert context.intent is None


class TestFeedbackHandlerName:
    """Tests for handler_name extraction in feedback context."""

    @pytest.fixture
    def feedback_service(self):
        return FeedbackService()

    @pytest.fixture
    def mock_user_message(self):
        message = MagicMock()
        message.id = "msg_user_001"
        message.content = "ranking de tiendas por ventas"
        message.created_at = datetime(2024, 12, 1, 10, 0, 0)
        return message

    @pytest.mark.asyncio
    async def test_handler_name_extracted_from_metadata(
        self, feedback_service, mock_user_message
    ):
        """handler_name is extracted from message metadata when present."""
        message = MagicMock()
        message.id = "msg_asst_001"
        message.content = "Aqui esta el ranking..."
        message.metadata = {
            "handler_name": "store_ranking",
            "chart_data": {"metric_name": "ventas_total"},
        }

        with patch.object(
            feedback_service, "_get_message",
            new_callable=AsyncMock, return_value=message,
        ), patch.object(
            feedback_service, "_get_previous_user_message",
            new_callable=AsyncMock, return_value=mock_user_message,
        ):
            context = await feedback_service.get_context_for_message(
                message_id="msg_asst_001",
                conversation_id="conv_001",
            )

        assert context is not None
        assert context.handler_name == "store_ranking"

    @pytest.mark.asyncio
    async def test_handler_name_none_when_absent(
        self, feedback_service, mock_user_message
    ):
        """handler_name is None when not present in metadata."""
        message = MagicMock()
        message.id = "msg_asst_002"
        message.content = "Hola!"
        message.metadata = {"intent": "GREETING"}

        with patch.object(
            feedback_service, "_get_message",
            new_callable=AsyncMock, return_value=message,
        ), patch.object(
            feedback_service, "_get_previous_user_message",
            new_callable=AsyncMock, return_value=mock_user_message,
        ):
            context = await feedback_service.get_context_for_message(
                message_id="msg_asst_002",
                conversation_id="conv_001",
            )

        assert context is not None
        assert context.handler_name is None

    def test_handler_name_in_to_dict(self):
        """handler_name appears in to_dict() output when set."""
        context = FeedbackContext(
            original_query="ranking de tiendas",
            response_text="Aqui esta el ranking",
            handler_name="store_ranking",
        )
        d = context.to_dict()
        assert d["handler_name"] == "store_ranking"

    def test_handler_name_absent_in_to_dict(self):
        """handler_name is not in to_dict() when None."""
        context = FeedbackContext(
            original_query="hola",
            response_text="hola!",
        )
        d = context.to_dict()
        assert "handler_name" not in d


class TestEnrichedFeedback:
    """Tests for EnrichedFeedback model."""

    def test_enriched_feedback_creation(self):
        """EnrichedFeedback includes base fields plus context."""
        context = FeedbackContext(
            original_query="Test query",
            response_text="Test response",
        )

        enriched = EnrichedFeedback(
            message_id="msg_123",
            conversation_id="conv_123",
            user_id="user_456",
            rating=FeedbackRating.DOWN,
            reason="Incorrect data",
            context=context,
        )

        assert enriched.message_id == "msg_123"
        assert enriched.rating == FeedbackRating.DOWN
        assert enriched.reason == "Incorrect data"
        assert enriched.context.original_query == "Test query"

    def test_enriched_feedback_to_dict(self):
        """EnrichedFeedback serializes correctly for MongoDB."""
        context = FeedbackContext(
            original_query="Test query",
            response_text="Test response",
            intent="GREETING",
        )

        enriched = EnrichedFeedback(
            message_id="msg_123",
            conversation_id="conv_123",
            user_id="user_456",
            rating=FeedbackRating.UP,
            context=context,
        )

        result = enriched.to_dict()

        assert "message_id" in result
        assert "context" in result
        assert result["context"]["intent"] == "GREETING"
        assert result["rating"] == "up"
