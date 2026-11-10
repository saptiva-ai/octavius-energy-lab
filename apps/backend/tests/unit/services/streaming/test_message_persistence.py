"""
Unit tests for MessagePersistenceService.

Tests cover:
- Building assistant metadata
- Event building (done, error)
- Error content and metadata building
"""

import json
import pytest
from unittest.mock import MagicMock

from src.services.streaming.message_persistence import MessagePersistenceService


@pytest.mark.unit
class TestBuildAssistantMetadata:
    """Tests for build_assistant_metadata method."""

    def test_minimal_metadata(self):
        """Should build minimal metadata."""
        metadata = MessagePersistenceService.build_assistant_metadata()

        assert metadata["streaming"] is True
        assert metadata["has_documents"] is False
        assert metadata["document_warnings"] is None

    def test_with_document_ids(self):
        """Should mark has_documents when IDs provided."""
        metadata = MessagePersistenceService.build_assistant_metadata(
            document_ids=["doc-1", "doc-2"]
        )

        assert metadata["has_documents"] is True

    def test_with_doc_warnings(self):
        """Should include document warnings."""
        warnings = ["Password protected", "Large file"]
        metadata = MessagePersistenceService.build_assistant_metadata(
            doc_warnings=warnings
        )

        assert metadata["document_warnings"] == warnings

    def test_streaming_flag(self):
        """Should set streaming flag correctly."""
        metadata = MessagePersistenceService.build_assistant_metadata(streaming=False)

        assert metadata["streaming"] is False

    def test_with_artifact_id(self):
        """Should add tool_invocations for artifact (BUG-8 fix)."""
        metadata = MessagePersistenceService.build_assistant_metadata(
            artifact_id="art-123"
        )

        assert "tool_invocations" in metadata
        assert len(metadata["tool_invocations"]) == 1
        assert metadata["tool_invocations"][0]["tool_name"] == "create_artifact"
        assert metadata["tool_invocations"][0]["result"]["id"] == "art-123"

    def test_combined_metadata(self):
        """Should combine all metadata fields."""
        metadata = MessagePersistenceService.build_assistant_metadata(
            streaming=True,
            document_ids=["doc-1"],
            doc_warnings=["Large file"],
            artifact_id="art-456",
        )

        assert metadata["streaming"] is True
        assert metadata["has_documents"] is True
        assert metadata["document_warnings"] == ["Large file"]
        assert "tool_invocations" in metadata

    def test_without_retail_analytics_key_absent(self):
        """No debe agregar la key si no se pasa retail_analytics (default None)."""
        metadata = MessagePersistenceService.build_assistant_metadata()

        assert "retail_analytics" not in metadata

    def test_with_retail_analytics(self):
        """Debe adjuntar el AnalyticsResponse crudo del plugin cuando se pasa."""
        analytics = {
            "metric_name": "disponibilidad",
            "chart_type": "bar",
            "series": [{"name": "Mundo E", "points": []}],
        }
        metadata = MessagePersistenceService.build_assistant_metadata(
            retail_analytics=analytics
        )

        assert metadata["retail_analytics"] == analytics


@pytest.mark.unit
class TestBuildDoneEvent:
    """Tests for build_done_event method."""

    def test_event_structure(self):
        """Should build correct event structure."""
        event = MessagePersistenceService.build_done_event(
            message_id="msg-123",
            chat_id="chat-456",
            content="Full response here",
        )

        assert event["event"] == "done"
        assert "data" in event

    def test_event_data_content(self):
        """Should include all data fields."""
        event = MessagePersistenceService.build_done_event(
            message_id="msg-123",
            chat_id="chat-456",
            content="Full response here",
        )

        data = json.loads(event["data"])

        assert data["message_id"] == "msg-123"
        assert data["chat_id"] == "chat-456"
        assert data["content"] == "Full response here"

    def test_no_metadata_key_when_not_provided(self):
        """No debe incluir metadata en el payload si no se pasa (default None)."""
        event = MessagePersistenceService.build_done_event(
            message_id="msg-123",
            chat_id="chat-456",
            content="Full response here",
        )

        data = json.loads(event["data"])

        assert "metadata" not in data

    def test_includes_metadata_when_provided(self):
        """Debe incluir metadata (ej. retail_analytics) para que el frontend
        lo tenga en el mismo turno sin esperar un refresh."""
        event = MessagePersistenceService.build_done_event(
            message_id="msg-123",
            chat_id="chat-456",
            content="Full response here",
            metadata={"retail_analytics": {"metric_name": "disponibilidad"}},
        )

        data = json.loads(event["data"])

        assert data["metadata"]["retail_analytics"]["metric_name"] == "disponibilidad"


@pytest.mark.unit
class TestBuildErrorEvent:
    """Tests for build_error_event method."""

    def test_event_structure(self):
        """Should build correct error event structure."""
        event = MessagePersistenceService.build_error_event(
            error_message="Something went wrong",
            error_type="ValueError",
        )

        assert event["event"] == "error"
        assert "data" in event

    def test_error_data_content(self):
        """Should include error details."""
        event = MessagePersistenceService.build_error_event(
            error_message="Database error",
            error_type="ConnectionError",
            recoverable=True,
        )

        data = json.loads(event["data"])

        assert data["error"] == "Database error"
        assert data["type"] == "ConnectionError"
        assert data["recoverable"] is True

    def test_non_recoverable_error(self):
        """Should mark non-recoverable errors."""
        event = MessagePersistenceService.build_error_event(
            error_message="Fatal error",
            error_type="SystemError",
            recoverable=False,
        )

        data = json.loads(event["data"])
        assert data["recoverable"] is False


@pytest.mark.unit
class TestBuildErrorContent:
    """Tests for build_error_content method."""

    def test_includes_error_message(self):
        """Should include error message."""
        error = ValueError("Invalid input")
        content = MessagePersistenceService.build_error_content(error)

        assert "Invalid input" in content
        assert "❌" in content

    def test_truncates_long_errors(self):
        """Should truncate very long error messages."""
        error = Exception("x" * 500)
        content = MessagePersistenceService.build_error_content(error)

        # Should not include full 500 chars
        assert len(content) < 700

    def test_includes_retry_instruction(self):
        """Should include retry instruction."""
        error = Exception("Error")
        content = MessagePersistenceService.build_error_content(error)

        assert "intenta nuevamente" in content.lower() or "soporte" in content.lower()


@pytest.mark.unit
class TestBuildErrorMetadata:
    """Tests for build_error_metadata method."""

    def test_includes_error_flag(self):
        """Should set error flag to True."""
        error = ValueError("Test error")
        metadata = MessagePersistenceService.build_error_metadata(error)

        assert metadata["error"] is True

    def test_includes_error_type(self):
        """Should include exception type name."""
        error = TypeError("Wrong type")
        metadata = MessagePersistenceService.build_error_metadata(error)

        assert metadata["error_type"] == "TypeError"

    def test_includes_error_message(self):
        """Should include error message."""
        error = RuntimeError("Runtime issue")
        metadata = MessagePersistenceService.build_error_metadata(error)

        assert metadata["error_message"] == "Runtime issue"

    def test_truncates_long_message(self):
        """Should truncate very long error messages."""
        error = Exception("x" * 1000)
        metadata = MessagePersistenceService.build_error_metadata(error)

        assert len(metadata["error_message"]) <= 500


@pytest.mark.unit
class TestMetadataIntegration:
    """Integration tests for metadata building."""

    def test_full_metadata_scenario(self):
        """Should combine streaming, documents and artifact metadata."""
        metadata = MessagePersistenceService.build_assistant_metadata(
            streaming=True,
            document_ids=["doc-1"],
            artifact_id="art-789",
        )

        assert metadata["streaming"] is True
        assert metadata["has_documents"] is True
        assert "tool_invocations" in metadata
        assert metadata["tool_invocations"][0]["result"]["id"] == "art-789"
