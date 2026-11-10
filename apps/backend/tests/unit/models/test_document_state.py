"""
Unit tests for DocumentState model.
"""

import pytest
from datetime import datetime
from src.models.document_state import DocumentState, ProcessingStatus


class TestDocumentStateCreation:
    """Test DocumentState instantiation"""

    def test_minimal_creation(self):
        """Test creation with minimal required fields"""
        doc = DocumentState(
            doc_id="test-123",
            name="report.pdf"
        )

        assert doc.doc_id == "test-123"
        assert doc.name == "report.pdf"
        assert doc.status == ProcessingStatus.UPLOADING
        assert doc.segments_count == 0
        assert doc.error is None
        assert doc.is_ready() is False
        assert doc.is_processing() is True

    def test_creation_with_metadata(self):
        """Test creation with full metadata"""
        doc = DocumentState(
            doc_id="test-123",
            name="report.pdf",
            pages=32,
            size_bytes=1024000,
            mimetype="application/pdf"
        )

        assert doc.pages == 32
        assert doc.size_bytes == 1024000
        assert doc.mimetype == "application/pdf"

    def test_timestamps_auto_populated(self):
        """Test that timestamps are automatically set"""
        before = datetime.utcnow()
        doc = DocumentState(doc_id="test-123", name="test.pdf")
        after = datetime.utcnow()

        assert before <= doc.created_at <= after
        assert before <= doc.updated_at <= after


class TestDocumentLifecycle:
    """Test document state transitions"""

    def test_lifecycle_uploading_to_ready(self):
        """Test normal lifecycle: UPLOADING → PROCESSING → READY"""
        doc = DocumentState(doc_id="test-123", name="test.pdf")

        # Initial state
        assert doc.status == ProcessingStatus.UPLOADING
        assert doc.is_processing() is True

        # Transition to PROCESSING
        doc.mark_processing()
        assert doc.status == ProcessingStatus.PROCESSING
        assert doc.is_processing() is True
        assert doc.is_ready() is False

        # Transition to READY
        doc.mark_ready(segments_count=15)
        assert doc.status == ProcessingStatus.READY
        assert doc.segments_count == 15
        assert doc.indexed_at is not None
        assert doc.is_ready() is True
        assert doc.is_processing() is False

    def test_lifecycle_with_segmenting(self):
        """Test lifecycle with explicit segmenting step"""
        doc = DocumentState(doc_id="test-123", name="test.pdf")

        doc.mark_processing()
        assert doc.status == ProcessingStatus.PROCESSING

        doc.mark_segmenting()
        assert doc.status == ProcessingStatus.SEGMENTING
        assert doc.is_processing() is True

        doc.mark_ready(segments_count=20)
        assert doc.status == ProcessingStatus.READY
        assert doc.segments_count == 20

    def test_lifecycle_failure(self):
        """Test failure during processing"""
        doc = DocumentState(doc_id="test-123", name="corrupted.pdf")

        doc.mark_processing()
        doc.mark_failed("OCR extraction failed: invalid PDF structure")

        assert doc.status == ProcessingStatus.FAILED
        assert doc.error == "OCR extraction failed: invalid PDF structure"
        assert doc.is_failed() is True
        assert doc.is_ready() is False
        assert doc.is_processing() is False

    def test_updated_at_changes_on_transitions(self):
        """Test that updated_at changes on each transition"""
        doc = DocumentState(doc_id="test-123", name="test.pdf")
        initial_updated = doc.updated_at

        # Small delay to ensure timestamp difference
        import time
        time.sleep(0.01)

        doc.mark_processing()
        processing_updated = doc.updated_at
        assert processing_updated > initial_updated

        time.sleep(0.01)
        doc.mark_ready(segments_count=10)
        ready_updated = doc.updated_at
        assert ready_updated > processing_updated


class TestErrorHandling:
    """Test error message handling"""

    def test_error_truncation(self):
        """Test that long error messages are truncated"""
        doc = DocumentState(doc_id="test-123", name="test.pdf")

        long_error = "x" * 1000
        doc.mark_failed(long_error)

        assert len(doc.error) == 500  # Truncated
        assert doc.error == "x" * 500

    def test_error_normal_length(self):
        """Test that short errors are not truncated"""
        doc = DocumentState(doc_id="test-123", name="test.pdf")

        error_msg = "File not found"
        doc.mark_failed(error_msg)

        assert doc.error == error_msg


class TestStateMethods:
    """Test state checking methods"""

    def test_is_ready_only_for_ready_status(self):
        """Test is_ready() returns True only for READY status"""
        doc = DocumentState(doc_id="test-123", name="test.pdf")

        assert doc.is_ready() is False  # UPLOADING

        doc.mark_processing()
        assert doc.is_ready() is False  # PROCESSING

        doc.mark_ready(segments_count=5)
        assert doc.is_ready() is True  # READY

        # Create new doc and mark as failed
        doc2 = DocumentState(doc_id="test-456", name="failed.pdf")
        doc2.mark_failed("error")
        assert doc2.is_ready() is False  # FAILED

    def test_is_processing_for_intermediate_states(self):
        """Test is_processing() returns True for all intermediate states"""
        doc = DocumentState(doc_id="test-123", name="test.pdf")

        # UPLOADING
        assert doc.is_processing() is True

        # PROCESSING
        doc.mark_processing()
        assert doc.is_processing() is True

        # SEGMENTING
        doc.mark_segmenting()
        assert doc.is_processing() is True

        # READY - no longer processing
        doc.mark_ready(segments_count=5)
        assert doc.is_processing() is False

    def test_is_failed_only_for_failed_status(self):
        """Test is_failed() returns True only for FAILED status"""
        doc = DocumentState(doc_id="test-123", name="test.pdf")

        assert doc.is_failed() is False

        doc.mark_processing()
        assert doc.is_failed() is False

        doc.mark_failed("error")
        assert doc.is_failed() is True


class TestSerialization:
    """Test JSON serialization"""

    def test_model_dump(self):
        """Test that model can be serialized to dict"""
        doc = DocumentState(
            doc_id="test-123",
            name="report.pdf",
            pages=32
        )

        data = doc.model_dump()

        assert isinstance(data, dict)
        assert data["doc_id"] == "test-123"
        assert data["name"] == "report.pdf"
        assert data["pages"] == 32
        assert data["status"] == ProcessingStatus.UPLOADING.value

    def test_model_dump_json(self):
        """Test JSON serialization with timestamps"""
        doc = DocumentState(doc_id="test-123", name="test.pdf")
        doc.mark_ready(segments_count=10)

        json_data = doc.model_dump(mode='json')

        assert isinstance(json_data, dict)
        assert json_data["indexed_at"] is not None
        # In JSON mode, datetimes are serialized as ISO strings
        assert isinstance(json_data["created_at"], str)
        assert "T" in json_data["created_at"]  # ISO format


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_zero_segments(self):
        """Test marking ready with zero segments"""
        doc = DocumentState(doc_id="test-123", name="empty.pdf")

        doc.mark_ready(segments_count=0)

        assert doc.is_ready() is True
        assert doc.segments_count == 0

    def test_large_segment_count(self):
        """Test large segment counts"""
        doc = DocumentState(doc_id="test-123", name="huge.pdf")

        doc.mark_ready(segments_count=10000)

        assert doc.segments_count == 10000

    def test_empty_error_message(self):
        """Test failing with empty error message"""
        doc = DocumentState(doc_id="test-123", name="test.pdf")

        doc.mark_failed("")

        assert doc.is_failed() is True
        assert doc.error == ""

    def test_special_characters_in_name(self):
        """Test document names with special characters"""
        doc = DocumentState(
            doc_id="test-123",
            name="Reporte 2024 - Demo Capital (Final).pdf"
        )

        assert doc.name == "Reporte 2024 - Demo Capital (Final).pdf"
