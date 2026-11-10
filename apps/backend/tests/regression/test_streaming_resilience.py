"""
Regression Tests for Streaming Resilience - Phase 3

Tests que verifican el manejo correcto de errores y edge cases en streaming:
- BUG-006: Producer error propagation to frontend
- BUG-007: Empty response fallback handling
- BUG-008: Redis blacklist failure resilience

These tests focus on the error handling and resilience patterns
in the streaming pipeline.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.streaming.message_persistence import MessagePersistenceService


class TestMessagePersistenceErrorHandling:
    """Tests for MessagePersistenceService error handling methods."""

    def test_bug_006_build_error_event_format(self):
        """
        BUG-006: Producer error propagation to frontend.

        Verifies that error events are properly formatted for SSE
        streaming to the frontend.
        """
        # Arrange
        error_message = "Connection to Saptiva API failed"
        error_type = "ConnectionError"

        # Act
        event = MessagePersistenceService.build_error_event(
            error_message=error_message,
            error_type=error_type,
            recoverable=True,
        )

        # Assert - Event has correct structure
        assert event["event"] == "error"
        assert "data" in event

        # Assert - Data is valid JSON
        data = json.loads(event["data"])
        assert data["error"] == error_message
        assert data["type"] == error_type
        assert data["recoverable"] is True

    def test_bug_006_build_error_event_non_recoverable(self):
        """Verify non-recoverable errors are marked correctly."""
        event = MessagePersistenceService.build_error_event(
            error_message="Fatal system error",
            error_type="SystemError",
            recoverable=False,
        )

        data = json.loads(event["data"])
        assert data["recoverable"] is False

    def test_bug_006_build_error_content_truncation(self):
        """Verify long error messages are truncated for user display."""
        # Arrange - Very long error message
        long_error = "x" * 500
        error = Exception(long_error)

        # Act
        content = MessagePersistenceService.build_error_content(error)

        # Assert - Content is truncated (200 chars max for error text)
        assert len(content) < 400  # Header + truncated error + footer
        assert "❌" in content
        assert "intenta nuevamente" in content

    def test_bug_006_build_error_metadata_structure(self):
        """Verify error metadata has correct structure for persistence."""
        # Arrange
        error = ValueError("Invalid parameter: bank_id must be positive")

        # Act
        metadata = MessagePersistenceService.build_error_metadata(error)

        # Assert
        assert metadata["error"] is True
        assert metadata["error_type"] == "ValueError"
        assert "Invalid parameter" in metadata["error_message"]
        assert len(metadata["error_message"]) <= 500  # Truncation limit


class TestMessagePersistenceMetadata:
    """Tests for assistant message metadata building."""

    def test_bug_007_empty_response_metadata(self):
        """
        BUG-007: Empty response fallback handling.

        Verifies metadata is built correctly even with minimal data.
        """
        # Act - Build metadata with minimal inputs
        metadata = MessagePersistenceService.build_assistant_metadata(
            streaming=True,
            document_ids=None,
            doc_warnings=None,
            bank_chart_data=None,
        )

        # Assert - Basic structure present
        assert metadata["streaming"] is True
        assert metadata["has_documents"] is False
        assert metadata["document_warnings"] is None

    def test_metadata_with_document_warnings(self):
        """Verify document warnings are included in metadata."""
        warnings = ["Document PDF-123 exceeded context limit", "Skipping page 5"]

        metadata = MessagePersistenceService.build_assistant_metadata(
            streaming=True,
            document_ids=["doc1", "doc2"],
            doc_warnings=warnings,
        )

        assert metadata["has_documents"] is True
        assert metadata["document_warnings"] == warnings

    def test_metadata_with_latency_tracking(self):
        """Verify latency is included for dashboard metrics."""
        metadata = MessagePersistenceService.build_assistant_metadata(
            streaming=True,
            latency_ms=1234.56,
        )

        assert metadata["latency_ms"] == 1234.56

    def test_bug_008_artifact_id_persistence(self):
        """
        BUG-008: Chart artifact restoration.

        Verifies artifact_id is properly stored in tool_invocations
        for chart restoration from history.
        """
        artifact_id = "artifact-abc123"

        metadata = MessagePersistenceService.build_assistant_metadata(
            streaming=True,
            artifact_id=artifact_id,
        )

        # Assert - tool_invocations structure for chart restoration
        assert "tool_invocations" in metadata
        assert len(metadata["tool_invocations"]) == 1
        invocation = metadata["tool_invocations"][0]
        assert invocation["tool_name"] == "create_artifact"
        assert invocation["result"]["id"] == artifact_id
        assert invocation["result"]["type"] == "bank_chart"


class TestRedisBlacklistResilience:
    """Tests for Redis token blacklist resilience."""

    @pytest.mark.asyncio
    async def test_bug_009_blacklist_check_with_redis_unavailable(self):
        """
        BUG-009: Token blacklist Redis failure.

        Verifies that when Redis is unavailable, the blacklist check
        either fails gracefully or raises an appropriate error.

        NOTE: Current implementation does NOT have fallback.
        This test documents the expected behavior.
        """
        from src.services.cache_service import is_token_blacklisted

        # Mock Redis client to raise connection error
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

        with patch("src.services.cache_service.get_redis_client", return_value=mock_redis):
            # Patch at module level to affect lazy loading
            import src.services.cache_service as cache_module
            original_get_client = cache_module.get_redis_client

            async def mock_get_redis_client():
                return mock_redis

            cache_module.get_redis_client = mock_get_redis_client

            try:
                # Act & Assert - Should raise connection error (no fallback)
                with pytest.raises(ConnectionError):
                    await is_token_blacklisted("test-token-123")
            finally:
                cache_module.get_redis_client = original_get_client

    @pytest.mark.asyncio
    async def test_bug_009_add_to_blacklist_with_redis_unavailable(self):
        """
        Verify add_token_to_blacklist behavior when Redis is unavailable.

        NOTE: Current implementation raises exception (no fallback).
        """
        from src.services.cache_service import add_token_to_blacklist

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

        import src.services.cache_service as cache_module
        original_get_client = cache_module.get_redis_client

        async def mock_get_redis_client():
            return mock_redis

        cache_module.get_redis_client = mock_get_redis_client

        try:
            with pytest.raises(ConnectionError):
                await add_token_to_blacklist("logout-token", 1234567890)
        finally:
            cache_module.get_redis_client = original_get_client


class TestStreamingEdgeCases:
    """Edge cases for streaming response handling."""

    def test_error_event_with_special_characters(self):
        """Verify error messages with special characters are properly escaped."""
        # Arrange - Error with JSON special characters
        error_message = 'Invalid query: "SELECT * FROM users" contains forbidden chars'

        # Act
        event = MessagePersistenceService.build_error_event(
            error_message=error_message,
            error_type="SQLInjectionError",
            recoverable=False,
        )

        # Assert - JSON is valid (special chars escaped)
        data = json.loads(event["data"])
        assert '"SELECT * FROM users"' in data["error"]

    def test_error_event_with_unicode(self):
        """Verify error messages with unicode characters work correctly."""
        error_message = "Error: Parámetro inválido 'año_fiscal' debe ser > 2020 🚫"

        event = MessagePersistenceService.build_error_event(
            error_message=error_message,
            error_type="ValidationError",
            recoverable=True,
        )

        data = json.loads(event["data"])
        assert "año_fiscal" in data["error"]
        assert "🚫" in data["error"]

    def test_error_metadata_with_nested_exception(self):
        """Verify nested exceptions are handled correctly."""
        # Arrange - Nested exception
        inner_error = ValueError("Inner error")
        outer_error = RuntimeError(f"Outer error caused by: {inner_error}")

        # Act
        metadata = MessagePersistenceService.build_error_metadata(outer_error)

        # Assert
        assert metadata["error_type"] == "RuntimeError"
        assert "Inner error" in metadata["error_message"]

    def test_metadata_empty_list_handling(self):
        """Verify empty lists are handled correctly."""
        metadata = MessagePersistenceService.build_assistant_metadata(
            streaming=True,
            document_ids=[],  # Empty list
            doc_warnings=[],  # Empty list
        )

        # Empty list should be falsy for has_documents
        assert metadata["has_documents"] is False
        # Empty list should become None for warnings (or empty)
        assert metadata["document_warnings"] is None or metadata["document_warnings"] == []
