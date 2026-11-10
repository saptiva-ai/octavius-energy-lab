"""
Unit tests for ResponsePostProcessor service.

Domain-agnostic post-processing: empty-response fallback and output
sanitization (strips leaked internal patterns).
"""

import pytest
from unittest.mock import MagicMock, patch

from src.services.streaming.response_postprocessor import (
    PostProcessResult,
    ResponsePostProcessor,
)

pytestmark = [pytest.mark.unit]


class TestPostProcessResultDataclass:
    """Tests for PostProcessResult dataclass."""

    def test_creation(self):
        """Test basic creation of PostProcessResult."""
        result = PostProcessResult(
            content="Hello world",
            was_empty=False,
            was_sanitized=False,
            chars_removed=0,
            fallback_scenario=None,
        )

        assert result.content == "Hello world"
        assert result.was_empty is False
        assert result.was_sanitized is False
        assert result.chars_removed == 0
        assert result.fallback_scenario is None

    def test_creation_with_sanitization(self):
        """Test creation flagged as sanitized."""
        result = PostProcessResult(
            content="Response",
            was_empty=False,
            was_sanitized=True,
            chars_removed=50,
            fallback_scenario=None,
        )

        assert result.was_sanitized is True
        assert result.chars_removed == 50

    def test_creation_with_fallback(self):
        """Test creation with fallback scenario."""
        result = PostProcessResult(
            content="Fallback message",
            was_empty=True,
            was_sanitized=False,
            chars_removed=0,
            fallback_scenario="STREAM_NO_CHUNKS",
        )

        assert result.was_empty is True
        assert result.fallback_scenario == "STREAM_NO_CHUNKS"


class TestHandleEmptyResponse:
    """Tests for handle_empty_response method."""

    def test_non_empty_response(self):
        """Test handling non-empty response."""
        result, scenario = ResponsePostProcessor.handle_empty_response("Valid response")

        assert result == "Valid response"
        assert scenario is None

    def test_whitespace_only_response(self):
        """Test handling whitespace-only response."""
        mock_scenario = MagicMock()
        mock_scenario.name = "STREAM_NO_CHUNKS"

        with (
            patch(
                "src.services.empty_response_handler.EmptyResponseHandler"
            ) as mock_handler,
            patch(
                "src.services.empty_response_handler.EmptyResponseScenario"
            ) as mock_enum,
        ):
            mock_enum.STREAM_NO_CHUNKS = mock_scenario
            mock_handler.get_fallback_message.return_value = "Fallback message"

            result, scenario = ResponsePostProcessor.handle_empty_response("   ")

            assert result == "Fallback message"
            assert scenario == "STREAM_NO_CHUNKS"

    def test_empty_string_response(self):
        """Test handling empty string response."""
        mock_scenario = MagicMock()
        mock_scenario.name = "STREAM_NO_CHUNKS"

        with (
            patch(
                "src.services.empty_response_handler.EmptyResponseHandler"
            ) as mock_handler,
            patch(
                "src.services.empty_response_handler.EmptyResponseScenario"
            ) as mock_enum,
        ):
            mock_enum.STREAM_NO_CHUNKS = mock_scenario
            mock_handler.get_fallback_message.return_value = "Fallback"

            result, scenario = ResponsePostProcessor.handle_empty_response("")

            assert result == "Fallback"
            assert scenario == "STREAM_NO_CHUNKS"

    def test_with_doc_warnings(self):
        """Test handling empty response with document warnings."""
        mock_scenario = MagicMock()
        mock_scenario.name = "DOCS_PROCESSING"

        with (
            patch(
                "src.services.empty_response_handler.EmptyResponseHandler"
            ) as mock_handler,
            patch(
                "src.services.empty_response_handler.EmptyResponseScenario"
            ) as mock_enum,
        ):
            mock_enum.DOCS_PROCESSING = mock_scenario
            mock_handler.get_fallback_message.return_value = "Processing warning"

            result, scenario = ResponsePostProcessor.handle_empty_response(
                "",
                doc_warnings=["Warning 1", "Warning 2"],
            )

            assert scenario == "DOCS_PROCESSING"

    def test_with_documents_no_warnings(self):
        """Test handling empty response with documents but no warnings."""
        mock_scenario = MagicMock()
        mock_scenario.name = "DOCS_NOT_FOUND"

        with (
            patch(
                "src.services.empty_response_handler.EmptyResponseHandler"
            ) as mock_handler,
            patch(
                "src.services.empty_response_handler.EmptyResponseScenario"
            ) as mock_enum,
        ):
            mock_enum.DOCS_NOT_FOUND = mock_scenario
            mock_handler.get_fallback_message.return_value = "Docs not found"

            result, scenario = ResponsePostProcessor.handle_empty_response(
                "",
                has_documents=True,
            )

            assert scenario == "DOCS_NOT_FOUND"

    def test_with_context(self):
        """Test handling empty response with context."""
        mock_scenario = MagicMock()
        mock_scenario.name = "STREAM_NO_CHUNKS"

        with (
            patch(
                "src.services.empty_response_handler.EmptyResponseHandler"
            ) as mock_handler,
            patch(
                "src.services.empty_response_handler.EmptyResponseScenario"
            ) as mock_enum,
        ):
            mock_enum.STREAM_NO_CHUNKS = mock_scenario
            mock_handler.get_fallback_message.return_value = "Contextual fallback"

            context = {"user_id": "123", "session_id": "456"}
            result, scenario = ResponsePostProcessor.handle_empty_response(
                "",
                context=context,
            )

            mock_handler.get_fallback_message.assert_called_once_with(
                scenario=mock_scenario,
                context=context,
            )

    def test_logs_incident(self):
        """Test that empty response incident is logged."""
        mock_scenario = MagicMock()
        mock_scenario.name = "STREAM_NO_CHUNKS"

        with (
            patch(
                "src.services.empty_response_handler.EmptyResponseHandler"
            ) as mock_handler,
            patch(
                "src.services.empty_response_handler.EmptyResponseScenario"
            ) as mock_enum,
        ):
            mock_enum.STREAM_NO_CHUNKS = mock_scenario
            mock_handler.get_fallback_message.return_value = "Fallback"

            ResponsePostProcessor.handle_empty_response("")

            mock_handler.log_empty_response_incident.assert_called_once()


class TestSanitize:
    """Tests for sanitize method."""

    def test_empty_input_passthrough(self):
        """Empty input returns unchanged with 0 chars removed."""
        result, chars_removed = ResponsePostProcessor.sanitize("")

        assert result == ""
        assert chars_removed == 0

    def test_no_leak_no_change(self):
        """Clean content is returned unchanged."""
        with patch(
            "src.services.text_sanitizer.sanitize_response_content"
        ) as mock_sanitize:
            mock_sanitize.return_value = "Clean content"

            result, chars_removed = ResponsePostProcessor.sanitize("Clean content")

            assert result == "Clean content"
            assert chars_removed == 0

    def test_removes_leaked_chars(self):
        """Leaked internal patterns are stripped and counted."""
        with patch(
            "src.services.text_sanitizer.sanitize_response_content"
        ) as mock_sanitize:
            mock_sanitize.return_value = "Clean"

            result, chars_removed = ResponsePostProcessor.sanitize("Clean<<leak>>")

            assert result == "Clean"
            assert chars_removed > 0


class TestProcess:
    """Tests for process method (full pipeline)."""

    def test_process_valid_response(self):
        """Test processing a valid response."""
        with patch.object(
            ResponsePostProcessor, "sanitize", return_value=("Valid response", 0)
        ):
            result = ResponsePostProcessor.process("Valid response")

            assert result.content == "Valid response"
            assert result.was_empty is False
            assert result.was_sanitized is False
            assert result.chars_removed == 0
            assert result.fallback_scenario is None

    def test_process_empty_response(self):
        """Test processing an empty response triggers fallback."""
        with patch.object(
            ResponsePostProcessor,
            "handle_empty_response",
            return_value=("Fallback message", "STREAM_NO_CHUNKS"),
        ):
            result = ResponsePostProcessor.process("")

            assert result.was_empty is True
            assert result.fallback_scenario == "STREAM_NO_CHUNKS"

    def test_process_sanitizes_response(self):
        """Test processing strips leaked patterns and flags sanitization."""
        with patch.object(
            ResponsePostProcessor, "sanitize", return_value=("Clean response", 12)
        ):
            result = ResponsePostProcessor.process("Clean response<<leak>>")

            assert result.content == "Clean response"
            assert result.was_sanitized is True
            assert result.chars_removed == 12

    def test_process_without_sanitization(self):
        """Test processing with sanitization disabled leaves content intact."""
        result = ResponsePostProcessor.process(
            "Response with internal marker",
            sanitize=False,
        )

        assert result.content == "Response with internal marker"
        assert result.was_sanitized is False
