"""
Streaming Error Logger Service - Centralized error logging for streaming handlers.

REFACTOR-001 Phase 10: Extracted from streaming_handler.py handle_stream error block.
"""

import traceback
from dataclasses import dataclass
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ErrorContext:
    """Context information for error logging."""

    user_id: str
    model: Optional[str] = None
    stream: Optional[bool] = None
    chat_id: Optional[str] = None
    session_id: Optional[str] = None
    message_preview: Optional[str] = None
    request_id: Optional[str] = None


class StreamingErrorLogger:
    """
    Centralized error logging for streaming handlers.

    Provides consistent error logging with:
    - Structured logging via structlog
    - Stderr output for immediate visibility
    - Full traceback capture
    """

    @classmethod
    def build_error_details(
        cls,
        exc: Exception,
        ctx: ErrorContext,
    ) -> Dict[str, Any]:
        """
        Build error details dictionary for logging.

        Args:
            exc: The exception that occurred
            ctx: Error context with request/session info

        Returns:
            Dictionary with all error details
        """
        details = {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
            "user_id": ctx.user_id,
            "model": ctx.model or "default",
            "stream": ctx.stream,
        }

        # Add optional context fields
        if ctx.chat_id:
            details["chat_id"] = ctx.chat_id
        if ctx.session_id:
            details["session_id"] = ctx.session_id
        if ctx.message_preview:
            details["message_preview"] = ctx.message_preview
        if ctx.request_id:
            details["request_id"] = ctx.request_id

        return details

    @classmethod
    def log_to_structlog(
        cls,
        error_details: Dict[str, Any],
    ) -> None:
        """Log error using structlog."""
        logger.error(
            "🚨 STREAMING CHAT FAILED - CRITICAL ERROR",
            **error_details,
            exc_info=True,
        )

    @classmethod
    def log_to_stderr(
        cls,
        exc: Exception,
        ctx: ErrorContext,
    ) -> None:
        """Print error to stderr for immediate visibility."""
        print(f"\n{'=' * 80}")
        print(f"🚨 STREAMING ERROR: {type(exc).__name__}")
        print(f"Message: {str(exc)}")
        print(f"User: {ctx.user_id}")

        if ctx.chat_id:
            print(f"Chat ID: {ctx.chat_id}")
        if ctx.model:
            print(f"Model: {ctx.model}")
        if ctx.message_preview:
            print(f"Message Preview: {ctx.message_preview}")

        print(f"Traceback:\n{traceback.format_exc()}")
        print(f"{'=' * 80}\n")

    @classmethod
    def log_error(
        cls,
        exc: Exception,
        ctx: ErrorContext,
    ) -> None:
        """
        Log error to both structlog and stderr.

        This is the main entry point for error logging.

        Args:
            exc: The exception that occurred
            ctx: Error context with request/session info
        """
        error_details = cls.build_error_details(exc, ctx)
        cls.log_to_structlog(error_details)
        cls.log_to_stderr(exc, ctx)

    @classmethod
    def log_from_request(
        cls,
        exc: Exception,
        user_id: str,
        request: Any,
        context: Optional[Any] = None,
    ) -> None:
        """
        Convenience method to log error from request and optional context.

        Args:
            exc: The exception that occurred
            user_id: User ID from request
            request: ChatRequest object
            context: Optional ChatContext (may not exist if error during creation)
        """
        ctx = ErrorContext(
            user_id=user_id,
            model=getattr(request, "model", None),
            stream=getattr(request, "stream", None),
        )

        # Add context fields if available
        if context:
            ctx.chat_id = getattr(context, "chat_id", None)
            ctx.session_id = getattr(context, "session_id", None)
            ctx.request_id = getattr(context, "request_id", None)
            if hasattr(context, "message") and context.message:
                ctx.message_preview = context.message[:100]

        cls.log_error(exc, ctx)
