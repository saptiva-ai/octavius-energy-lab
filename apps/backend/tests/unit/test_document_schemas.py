"""
Unit tests for document schemas.

Tests Pydantic models for document ingestion and responses.
"""
import pytest
from pydantic import ValidationError

from src.schemas.document import (
    IngestOptions,
    IngestRequest,
    PageContentResponse,
    IngestResponse,
    DocumentMetadata
)


@pytest.mark.unit
class TestDocumentSchemas:
    """Test document schema models"""

    def test_ingest_options_defaults(self):
        """Test IngestOptions with default values"""
        options = IngestOptions()

        assert options.ocr == "auto"
        assert options.dpi == 350
        assert options.language == "spa"

    def test_ingest_options_custom(self):
        """Test IngestOptions with custom values"""
        options = IngestOptions(
            ocr="always",
            dpi=600,
            language="eng"
        )

        assert options.ocr == "always"
        assert options.dpi == 600
        assert options.language == "eng"

    def test_ingest_request_minimal(self):
        """Test IngestRequest with minimal required fields"""
        request = IngestRequest(
            filename="document.pdf",
            content_type="application/pdf",
            size_bytes=1024000,
            minio_key="docs/uuid-123.pdf"
        )

        assert request.filename == "document.pdf"
        assert request.content_type == "application/pdf"
        assert request.size_bytes == 1024000
        assert request.minio_key == "docs/uuid-123.pdf"
        assert request.conversation_id is None
        assert isinstance(request.options, IngestOptions)

    def test_ingest_request_with_conversation(self):
        """Test IngestRequest with conversation_id"""
        request = IngestRequest(
            filename="report.pdf",
            content_type="application/pdf",
            size_bytes=500000,
            minio_key="docs/report.pdf",
            conversation_id="conv-123"
        )

        assert request.conversation_id == "conv-123"

    def test_ingest_request_with_custom_options(self):
        """Test IngestRequest with custom options"""
        options = IngestOptions(ocr="never", dpi=300, language="fra")
        request = IngestRequest(
            filename="doc.pdf",
            content_type="application/pdf",
            size_bytes=1000,
            minio_key="docs/doc.pdf",
            options=options
        )

        assert request.options.ocr == "never"
        assert request.options.dpi == 300
        assert request.options.language == "fra"

    def test_ingest_request_validation_missing_fields(self):
        """Test IngestRequest requires all mandatory fields"""
        with pytest.raises(ValidationError):
            IngestRequest(
                filename="doc.pdf",
                content_type="application/pdf"
                # Missing size_bytes and minio_key
            )

    def test_page_content_response_minimal(self):
        """Test PageContentResponse without table"""
        page = PageContentResponse(
            page=1,
            text_md="# Page 1\nContent here",
            has_table=False
        )

        assert page.page == 1
        assert "Page 1" in page.text_md
        assert page.has_table is False
        assert page.table_csv_key is None

    def test_page_content_response_with_table(self):
        """Test PageContentResponse with table"""
        page = PageContentResponse(
            page=2,
            text_md="# Data Table",
            has_table=True,
            table_csv_key="tables/page2.csv"
        )

        assert page.page == 2
        assert page.has_table is True
        assert page.table_csv_key == "tables/page2.csv"

    def test_ingest_response_creation(self):
        """Test IngestResponse model"""
        pages = [
            PageContentResponse(page=1, text_md="Page 1", has_table=False),
            PageContentResponse(page=2, text_md="Page 2", has_table=True, table_csv_key="t2.csv")
        ]

        response = IngestResponse(
            doc_id="doc-123",
            filename="report.pdf",
            size_bytes=2048000,
            total_pages=2,
            pages=pages,
            status="completed",
            ocr_applied=True
        )

        assert response.doc_id == "doc-123"
        assert response.filename == "report.pdf"
        assert response.size_bytes == 2048000
        assert response.total_pages == 2
        assert len(response.pages) == 2
        assert response.status == "completed"
        assert response.ocr_applied is True

    def test_ingest_response_no_ocr(self):
        """Test IngestResponse without OCR"""
        response = IngestResponse(
            doc_id="doc-456",
            filename="text.pdf",
            size_bytes=100000,
            total_pages=1,
            pages=[],
            status="completed",
            ocr_applied=False
        )

        assert response.ocr_applied is False
        assert len(response.pages) == 0

    def test_document_metadata_minimal(self):
        """Test DocumentMetadata without optional fields"""
        metadata = DocumentMetadata(
            doc_id="doc-789",
            filename="document.pdf",
            content_type="application/pdf",
            size_bytes=500000,
            total_pages=10,
            status="ready",
            created_at="2024-01-15T10:00:00Z"
        )

        assert metadata.doc_id == "doc-789"
        assert metadata.filename == "document.pdf"
        assert metadata.content_type == "application/pdf"
        assert metadata.size_bytes == 500000
        assert metadata.total_pages == 10
        assert metadata.status == "ready"
        assert metadata.created_at == "2024-01-15T10:00:00Z"
        assert metadata.minio_url is None

    def test_document_metadata_with_url(self):
        """Test DocumentMetadata with MinIO URL"""
        metadata = DocumentMetadata(
            doc_id="doc-101",
            filename="image.png",
            content_type="image/png",
            size_bytes=250000,
            total_pages=1,
            status="ready",
            created_at="2024-01-15T11:00:00Z",
            minio_url="https://minio.example.com/bucket/image.png"
        )

        assert metadata.minio_url == "https://minio.example.com/bucket/image.png"

    def test_ingest_response_json_serialization(self):
        """Test IngestResponse can be serialized"""
        response = IngestResponse(
            doc_id="doc-1",
            filename="test.pdf",
            size_bytes=1000,
            total_pages=1,
            pages=[],
            status="completed",
            ocr_applied=False
        )

        json_data = response.model_dump()
        assert json_data["doc_id"] == "doc-1"
        assert json_data["ocr_applied"] is False
        assert isinstance(json_data, dict)

    def test_ingest_options_json_schema(self):
        """Test IngestOptions generates valid JSON schema"""
        schema = IngestOptions.model_json_schema()
        assert "properties" in schema
        assert "ocr" in schema["properties"]
        assert "dpi" in schema["properties"]
        assert "language" in schema["properties"]
