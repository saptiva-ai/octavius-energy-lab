"""
Unit tests for empty_response_handler module.

Tests:
- EmptyResponseScenario enum
- EmptyResponseHandler class methods
- Convenience functions
"""

import pytest

from src.services.empty_response_handler import (
    EmptyResponseHandler,
    EmptyResponseScenario,
    ensure_non_empty_content,
    get_api_error_message,
    get_docs_processing_message,
)

pytestmark = [pytest.mark.unit]


class TestEmptyResponseScenario:
    """Test EmptyResponseScenario enum."""

    def test_all_scenarios_exist(self):
        """Test all expected scenarios exist."""
        expected = [
            "API_NO_CHOICES",
            "API_EMPTY_CONTENT",
            "API_TIMEOUT",
            "API_ERROR",
            "DOCS_PROCESSING",
            "DOCS_NOT_FOUND",
            "DOCS_EMPTY",
            "STREAM_INTERRUPTED",
            "STREAM_NO_CHUNKS",
            "UNKNOWN",
        ]
        for scenario in expected:
            assert hasattr(EmptyResponseScenario, scenario)

    def test_scenario_values(self):
        """Test scenario values are correct."""
        assert EmptyResponseScenario.API_NO_CHOICES.value == "api_no_choices"
        assert EmptyResponseScenario.DOCS_PROCESSING.value == "docs_processing"
        assert EmptyResponseScenario.UNKNOWN.value == "unknown"


class TestFallbackMessages:
    """Test fallback messages configuration."""

    def test_all_scenarios_have_messages(self):
        """Test all scenarios have fallback messages."""
        for scenario in EmptyResponseScenario:
            assert scenario in EmptyResponseHandler.FALLBACK_MESSAGES

    def test_messages_are_non_empty(self):
        """Test all messages are non-empty strings."""
        for scenario, message in EmptyResponseHandler.FALLBACK_MESSAGES.items():
            assert isinstance(message, str)
            assert len(message) > 50  # Meaningful message

    def test_messages_contain_solution(self):
        """Test messages contain solution guidance."""
        for scenario, message in EmptyResponseHandler.FALLBACK_MESSAGES.items():
            assert "Solución" in message or "solución" in message.lower()


class TestGetFallbackMessage:
    """Test EmptyResponseHandler.get_fallback_message method."""

    def test_returns_message_for_scenario(self):
        """Test returns correct message for scenario."""
        message = EmptyResponseHandler.get_fallback_message(
            EmptyResponseScenario.API_TIMEOUT
        )

        assert "Tiempo de espera" in message
        assert "Solución" in message

    def test_default_scenario_is_unknown(self):
        """Test default scenario is UNKNOWN."""
        message = EmptyResponseHandler.get_fallback_message()

        expected = EmptyResponseHandler.FALLBACK_MESSAGES[
            EmptyResponseScenario.UNKNOWN
        ]
        assert message == expected

    def test_adds_file_count_context(self):
        """Test adds file count from context."""
        message = EmptyResponseHandler.get_fallback_message(
            EmptyResponseScenario.DOCS_PROCESSING,
            context={"file_count": 3}
        )

        assert "Archivos adjuntos: 3" in message

    def test_adds_model_context(self):
        """Test adds model from context."""
        message = EmptyResponseHandler.get_fallback_message(
            EmptyResponseScenario.API_ERROR,
            context={"model": "saptiva-turbo"}
        )

        assert "Modelo usado: saptiva-turbo" in message

    def test_adds_error_detail_context(self):
        """Test adds error detail from context."""
        message = EmptyResponseHandler.get_fallback_message(
            EmptyResponseScenario.API_ERROR,
            context={"error_detail": "Rate limit exceeded"}
        )

        assert "Rate limit exceeded" in message

    def test_empty_context_no_extra_info(self):
        """Test empty context adds no extra info."""
        message = EmptyResponseHandler.get_fallback_message(
            EmptyResponseScenario.API_TIMEOUT,
            context={}
        )

        # Should not have extra info section
        assert "---" not in message

    @pytest.mark.parametrize("scenario", list(EmptyResponseScenario))
    def test_all_scenarios_return_messages(self, scenario):
        """Test all scenarios return non-empty messages."""
        message = EmptyResponseHandler.get_fallback_message(scenario)
        assert len(message) > 0


class TestEnsureNonEmpty:
    """Test EmptyResponseHandler.ensure_non_empty method."""

    def test_returns_content_if_valid(self):
        """Test returns original content if non-empty."""
        content = "This is valid content"
        result = EmptyResponseHandler.ensure_non_empty(content)
        assert result == content

    def test_returns_fallback_for_none(self):
        """Test returns fallback for None content."""
        result = EmptyResponseHandler.ensure_non_empty(None)
        assert len(result) > 0
        assert "Error" in result or "error" in result.lower()

    def test_returns_fallback_for_empty_string(self):
        """Test returns fallback for empty string."""
        result = EmptyResponseHandler.ensure_non_empty("")
        assert len(result) > 0

    def test_returns_fallback_for_whitespace(self):
        """Test returns fallback for whitespace-only string."""
        result = EmptyResponseHandler.ensure_non_empty("   \n\t  ")
        assert len(result) > 0

    def test_respects_min_length(self):
        """Test respects min_length parameter."""
        # Short content with high min_length
        result = EmptyResponseHandler.ensure_non_empty(
            content="Hi",
            min_length=10,
            scenario=EmptyResponseScenario.API_EMPTY_CONTENT
        )
        # Should return fallback since "Hi" is < 10 chars
        assert len(result) > 10

    def test_uses_correct_scenario(self):
        """Test uses correct scenario for fallback."""
        result = EmptyResponseHandler.ensure_non_empty(
            content="",
            scenario=EmptyResponseScenario.DOCS_PROCESSING
        )
        assert "procesamiento" in result.lower()

    def test_includes_context(self):
        """Test includes context in fallback."""
        result = EmptyResponseHandler.ensure_non_empty(
            content=None,
            scenario=EmptyResponseScenario.DOCS_PROCESSING,
            context={"file_count": 5}
        )
        assert "5" in result


class TestLogEmptyResponseIncident:
    """Test EmptyResponseHandler.log_empty_response_incident method."""

    def test_logs_incident(self):
        """Test logs incident without error."""
        # Should not raise
        EmptyResponseHandler.log_empty_response_incident(
            scenario=EmptyResponseScenario.API_ERROR,
            context={
                "user_id": "user_123",
                "chat_id": "chat_456",
                "model": "saptiva-turbo",
            }
        )

    def test_handles_empty_context(self):
        """Test handles empty context dict."""
        EmptyResponseHandler.log_empty_response_incident(
            scenario=EmptyResponseScenario.UNKNOWN,
            context={}
        )

    def test_handles_stack_trace(self):
        """Test handles optional stack trace."""
        EmptyResponseHandler.log_empty_response_incident(
            scenario=EmptyResponseScenario.API_ERROR,
            context={"user_id": "test"},
            stack_trace="Traceback: ..."
        )


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_ensure_non_empty_content_valid(self):
        """Test ensure_non_empty_content with valid content."""
        result = ensure_non_empty_content("Valid content")
        assert result == "Valid content"

    def test_ensure_non_empty_content_empty(self):
        """Test ensure_non_empty_content with empty content."""
        result = ensure_non_empty_content(
            "",
            scenario=EmptyResponseScenario.API_EMPTY_CONTENT,
            model="test-model"
        )
        assert len(result) > 0

    def test_ensure_non_empty_content_with_kwargs(self):
        """Test ensure_non_empty_content passes kwargs as context."""
        result = ensure_non_empty_content(
            None,
            scenario=EmptyResponseScenario.API_ERROR,
            model="test-model",
            error_detail="Something failed"
        )
        assert "test-model" in result
        assert "Something failed" in result

    def test_get_docs_processing_message(self):
        """Test get_docs_processing_message."""
        message = get_docs_processing_message(file_count=3)
        assert "procesamiento" in message.lower()
        assert "3" in message

    def test_get_docs_processing_message_no_count(self):
        """Test get_docs_processing_message without file count."""
        message = get_docs_processing_message()
        assert "procesamiento" in message.lower()

    def test_get_api_error_message(self):
        """Test get_api_error_message."""
        message = get_api_error_message(error_detail="Connection refused")
        assert "error" in message.lower()
        assert "Connection refused" in message

    def test_get_api_error_message_no_detail(self):
        """Test get_api_error_message without detail."""
        message = get_api_error_message()
        assert "error" in message.lower()


class TestEdgeCases:
    """Test edge cases."""

    def test_very_long_valid_content(self):
        """Test very long valid content is returned as-is."""
        content = "x" * 10000
        result = EmptyResponseHandler.ensure_non_empty(content)
        assert result == content

    def test_unicode_content(self):
        """Test unicode content is handled correctly."""
        content = "Contenido con ñ, á, é, í, ó, ú y 日本語"
        result = EmptyResponseHandler.ensure_non_empty(content)
        assert result == content

    def test_min_length_zero(self):
        """Test min_length=0 still requires non-empty."""
        result = EmptyResponseHandler.ensure_non_empty(
            content="",
            min_length=0
        )
        # Empty string stripped is "", len < 0 is False, but content is falsy
        # So it should still return fallback
        assert len(result) > 0

    def test_content_exactly_min_length(self):
        """Test content exactly at min_length passes."""
        result = EmptyResponseHandler.ensure_non_empty(
            content="abc",
            min_length=3
        )
        assert result == "abc"
