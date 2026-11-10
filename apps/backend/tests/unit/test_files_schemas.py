"""
Unit tests for files schemas.

Tests Pydantic models for unified file ingestion.
"""
import pytest
from pydantic import ValidationError

from src.schemas.files import (
    FileStatus,
    FileError,
    FileIngestResponse,
    FileIngestBulkResponse,
    FileEventPhase,
    FileEventPayload
)


@pytest.mark.unit
class TestFilesSchemas:
    """Test files schema models"""

    def test_file_status_enum_values(self):
        """Test FileStatus enum has expected values"""
        assert FileStatus.RECEIVED == "RECEIVED"
        assert FileStatus.PROCESSING == "PROCESSING"
        assert FileStatus.READY == "READY"
        assert FileStatus.FAILED == "FAILED"

    def test_file_error_creation(self):
        """Test FileError model"""
        error = FileError(
            code="EXTRACTION_FAILED",
            detail="Could not extract text from PDF"
        )

        assert error.code == "EXTRACTION_FAILED"
        assert error.detail == "Could not extract text from PDF"

    def test_file_error_without_detail(self):
        """Test FileError without optional detail"""
        error = FileError(code="UNKNOWN_ERROR")

        assert error.code == "UNKNOWN_ERROR"
        assert error.detail is None

    def test_file_ingest_response_success(self):
        """Test FileIngestResponse for successful upload"""
        response = FileIngestResponse(
            file_id="file-123",
            status=FileStatus.READY,
            bytes=1024000,
            mimetype="application/pdf",
            pages=10,
            name="document.pdf",
            filename="document.pdf"
        )

        assert response.file_id == "file-123"
        assert response.status == FileStatus.READY
        assert response.bytes == 1024000
        assert response.mimetype == "application/pdf"
        assert response.pages == 10
        assert response.name == "document.pdf"
        assert response.filename == "document.pdf"
        assert response.doc_id is None
        assert response.error is None

    def test_file_ingest_response_with_doc_id(self):
        """Test FileIngestResponse with backward compatible doc_id"""
        response = FileIngestResponse(
            file_id="file-456",
            doc_id="doc-456",
            status=FileStatus.READY,
            bytes=500000
        )

        assert response.file_id == "file-456"
        assert response.doc_id == "doc-456"

    def test_file_ingest_response_failed(self):
        """Test FileIngestResponse for failed upload"""
        error = FileError(
            code="INVALID_FORMAT",
            detail="Unsupported file format"
        )

        response = FileIngestResponse(
            file_id="file-789",
            status=FileStatus.FAILED,
            bytes=0,
            error=error
        )

        assert response.status == FileStatus.FAILED
        assert response.error is not None
        assert response.error.code == "INVALID_FORMAT"

    def test_file_ingest_response_processing(self):
        """Test FileIngestResponse during processing"""
        response = FileIngestResponse(
            file_id="file-101",
            status=FileStatus.PROCESSING,
            bytes=2048000,
            mimetype="image/jpeg"
        )

        assert response.status == FileStatus.PROCESSING
        assert response.pages is None

    def test_file_ingest_bulk_response_empty(self):
        """Test FileIngestBulkResponse with no files"""
        bulk = FileIngestBulkResponse()

        assert bulk.files == []
        assert len(bulk.files) == 0

    def test_file_ingest_bulk_response_multiple(self):
        """Test FileIngestBulkResponse with multiple files"""
        files = [
            FileIngestResponse(
                file_id="file-1",
                status=FileStatus.READY,
                bytes=1000
            ),
            FileIngestResponse(
                file_id="file-2",
                status=FileStatus.PROCESSING,
                bytes=2000
            )
        ]

        bulk = FileIngestBulkResponse(files=files)

        assert len(bulk.files) == 2
        assert bulk.files[0].file_id == "file-1"
        assert bulk.files[1].file_id == "file-2"

    def test_file_event_phase_enum_values(self):
        """Test FileEventPhase enum has expected values"""
        assert FileEventPhase.UPLOAD == "upload"
        assert FileEventPhase.EXTRACT == "extract"
        assert FileEventPhase.CACHE == "cache"
        assert FileEventPhase.COMPLETE == "complete"

    def test_file_event_payload_upload(self):
        """Test FileEventPayload for upload phase"""
        event = FileEventPayload(
            file_id="file-123",
            phase=FileEventPhase.UPLOAD,
            pct=50.0
        )

        assert event.file_id == "file-123"
        assert event.phase == FileEventPhase.UPLOAD
        assert event.pct == 50.0
        assert event.trace_id is None
        assert event.status is None
        assert event.error is None

    def test_file_event_payload_complete(self):
        """Test FileEventPayload for complete phase"""
        event = FileEventPayload(
            file_id="file-456",
            phase=FileEventPhase.COMPLETE,
            pct=100.0,
            trace_id="trace-abc",
            status=FileStatus.READY
        )

        assert event.phase == FileEventPhase.COMPLETE
        assert event.pct == 100.0
        assert event.trace_id == "trace-abc"
        assert event.status == FileStatus.READY

    def test_file_event_payload_failed(self):
        """Test FileEventPayload with error"""
        error = FileError(code="TIMEOUT", detail="Processing timeout")

        event = FileEventPayload(
            file_id="file-789",
            phase=FileEventPhase.EXTRACT,
            pct=75.0,
            status=FileStatus.FAILED,
            error=error
        )

        assert event.status == FileStatus.FAILED
        assert event.error is not None
        assert event.error.code == "TIMEOUT"

    def test_file_event_payload_percentage_validation(self):
        """Test FileEventPayload validates percentage range"""
        # Valid percentage
        event = FileEventPayload(
            file_id="file-1",
            phase=FileEventPhase.EXTRACT,
            pct=0.0
        )
        assert event.pct == 0.0

        event = FileEventPayload(
            file_id="file-2",
            phase=FileEventPhase.EXTRACT,
            pct=100.0
        )
        assert event.pct == 100.0

        # Invalid percentage (should fail)
        with pytest.raises(ValidationError):
            FileEventPayload(
                file_id="file-3",
                phase=FileEventPhase.EXTRACT,
                pct=150.0  # > 100
            )

    def test_file_ingest_response_json_serialization(self):
        """Test FileIngestResponse can be serialized"""
        response = FileIngestResponse(
            file_id="file-1",
            status=FileStatus.READY,
            bytes=1000,
            pages=5
        )

        json_data = response.model_dump()
        assert json_data["file_id"] == "file-1"
        assert json_data["status"] == "READY"
        assert isinstance(json_data, dict)

    def test_file_event_payload_json_serialization(self):
        """Test FileEventPayload can be serialized"""
        event = FileEventPayload(
            file_id="file-1",
            phase=FileEventPhase.UPLOAD,
            pct=25.5
        )

        json_data = event.model_dump()
        assert json_data["file_id"] == "file-1"
        assert json_data["phase"] == "upload"
        assert json_data["pct"] == 25.5
