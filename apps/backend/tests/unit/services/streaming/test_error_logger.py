"""
Unit tests for error_logger module.

Tests:
- ErrorContext dataclass
- StreamingErrorLogger methods
"""

from unittest.mock import MagicMock, patch

import pytest

from src.services.streaming.error_logger import (
    ErrorContext,
    StreamingErrorLogger,
)

pytestmark = [pytest.mark.unit]


class TestErrorContext:
    """Test ErrorContext dataclass."""

    def test_create_minimal(self):
        """Test creating context with minimal fields."""
        ctx = ErrorContext(user_id="user_123")

        assert ctx.user_id == "user_123"
        assert ctx.model is None
        assert ctx.stream is None
        assert ctx.chat_id is None
        assert ctx.session_id is None
        assert ctx.message_preview is None
        assert ctx.request_id is None

    def test_create_full(self):
        """Test creating context with all fields."""
        ctx = ErrorContext(
            user_id="user_123",
            model="saptiva-turbo",
            stream=True,
            chat_id="chat_456",
            session_id="session_789",
            message_preview="Hello...",
            request_id="req_abc",
        )

        assert ctx.user_id == "user_123"
        assert ctx.model == "saptiva-turbo"
        assert ctx.stream is True
        assert ctx.chat_id == "chat_456"
        assert ctx.session_id == "session_789"
        assert ctx.message_preview == "Hello..."
        assert ctx.request_id == "req_abc"


class TestBuildErrorDetails:
    """Test StreamingErrorLogger.build_error_details method."""

    def test_includes_exception_info(self):
        """Test includes exception type and message."""
        exc = ValueError("Test error message")
        ctx = ErrorContext(user_id="user_123")

        details = StreamingErrorLogger.build_error_details(exc, ctx)

        assert details["error_type"] == "ValueError"
        assert details["error_message"] == "Test error message"
        assert "traceback" in details

    def test_includes_context_info(self):
        """Test includes context information."""
        exc = Exception("Error")
        ctx = ErrorContext(
            user_id="user_123",
            model="saptiva-turbo",
            stream=True,
        )

        details = StreamingErrorLogger.build_error_details(exc, ctx)

        assert details["user_id"] == "user_123"
        assert details["model"] == "saptiva-turbo"
        assert details["stream"] is True

    def test_defaults_model_to_default(self):
        """Test model defaults to 'default' when None."""
        exc = Exception("Error")
        ctx = ErrorContext(user_id="user_123")

        details = StreamingErrorLogger.build_error_details(exc, ctx)

        assert details["model"] == "default"

    def test_includes_optional_fields(self):
        """Test optional fields are included when present."""
        exc = Exception("Error")
        ctx = ErrorContext(
            user_id="user_123",
            chat_id="chat_456",
            session_id="session_789",
            message_preview="Hello",
            request_id="req_abc",
        )

        details = StreamingErrorLogger.build_error_details(exc, ctx)

        assert details["chat_id"] == "chat_456"
        assert details["session_id"] == "session_789"
        assert details["message_preview"] == "Hello"
        assert details["request_id"] == "req_abc"

    def test_excludes_none_optional_fields(self):
        """Test optional fields not included when None."""
        exc = Exception("Error")
        ctx = ErrorContext(user_id="user_123")

        details = StreamingErrorLogger.build_error_details(exc, ctx)

        assert "chat_id" not in details
        assert "session_id" not in details
        assert "message_preview" not in details
        assert "request_id" not in details


class TestLogToStructlog:
    """Test StreamingErrorLogger.log_to_structlog method."""

    @patch("src.services.streaming.error_logger.logger")
    def test_logs_error(self, mock_logger):
        """Test logs error with details."""
        error_details = {
            "error_type": "ValueError",
            "error_message": "Test",
            "user_id": "user_123",
        }

        StreamingErrorLogger.log_to_structlog(error_details)

        mock_logger.error.assert_called_once()


class TestLogToStderr:
    """Test StreamingErrorLogger.log_to_stderr method."""

    def test_prints_error_info(self, capsys):
        """Test prints error information."""
        exc = ValueError("Test error")
        ctx = ErrorContext(user_id="user_123")

        StreamingErrorLogger.log_to_stderr(exc, ctx)

        captured = capsys.readouterr()
        assert "STREAMING ERROR" in captured.out
        assert "ValueError" in captured.out
        assert "Test error" in captured.out
        assert "user_123" in captured.out

    def test_prints_optional_fields(self, capsys):
        """Test prints optional fields when present."""
        exc = ValueError("Error")
        ctx = ErrorContext(
            user_id="user_123",
            chat_id="chat_456",
            model="saptiva-turbo",
            message_preview="Hello world",
        )

        StreamingErrorLogger.log_to_stderr(exc, ctx)

        captured = capsys.readouterr()
        assert "chat_456" in captured.out
        assert "saptiva-turbo" in captured.out
        assert "Hello world" in captured.out


class TestLogError:
    """Test StreamingErrorLogger.log_error method."""

    @patch.object(StreamingErrorLogger, "log_to_stderr")
    @patch.object(StreamingErrorLogger, "log_to_structlog")
    @patch.object(StreamingErrorLogger, "build_error_details")
    def test_calls_all_methods(
        self, mock_build, mock_structlog, mock_stderr
    ):
        """Test calls all logging methods."""
        mock_build.return_value = {"error": "details"}
        exc = ValueError("Test")
        ctx = ErrorContext(user_id="user_123")

        StreamingErrorLogger.log_error(exc, ctx)

        mock_build.assert_called_once_with(exc, ctx)
        mock_structlog.assert_called_once_with({"error": "details"})
        mock_stderr.assert_called_once_with(exc, ctx)


class TestLogFromRequest:
    """Test StreamingErrorLogger.log_from_request method."""

    @patch.object(StreamingErrorLogger, "log_error")
    def test_extracts_request_fields(self, mock_log):
        """Test extracts fields from request."""
        exc = ValueError("Error")
        request = MagicMock()
        request.model = "saptiva-turbo"
        request.stream = True

        StreamingErrorLogger.log_from_request(
            exc=exc, user_id="user_123", request=request
        )

        mock_log.assert_called_once()
        ctx = mock_log.call_args[0][1]
        assert ctx.user_id == "user_123"
        assert ctx.model == "saptiva-turbo"
        assert ctx.stream is True

    @patch.object(StreamingErrorLogger, "log_error")
    def test_extracts_context_fields(self, mock_log):
        """Test extracts fields from context."""
        exc = ValueError("Error")
        request = MagicMock()
        context = MagicMock()
        context.chat_id = "chat_456"
        context.session_id = "session_789"
        context.request_id = "req_abc"
        context.message = "This is a test message"

        StreamingErrorLogger.log_from_request(
            exc=exc, user_id="user_123", request=request, context=context
        )

        mock_log.assert_called_once()
        ctx = mock_log.call_args[0][1]
        assert ctx.chat_id == "chat_456"
        assert ctx.session_id == "session_789"
        assert ctx.request_id == "req_abc"
        assert "This is a test" in ctx.message_preview

    @patch.object(StreamingErrorLogger, "log_error")
    def test_handles_missing_context(self, mock_log):
        """Test handles None context."""
        exc = ValueError("Error")
        request = MagicMock()
        request.model = None
        request.stream = None

        StreamingErrorLogger.log_from_request(
            exc=exc, user_id="user_123", request=request, context=None
        )

        mock_log.assert_called_once()
        ctx = mock_log.call_args[0][1]
        assert ctx.chat_id is None
