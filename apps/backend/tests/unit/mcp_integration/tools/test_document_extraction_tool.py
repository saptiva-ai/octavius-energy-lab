"""
Unit tests for DocumentExtractionTool - Multi-tier text extraction.

Tests PDF and image text extraction with caching.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.mcp_integration.tools.document_extraction_tool import DocumentExtractionTool
from src.mcp_integration.protocol import ToolCategory, ToolCapability


@pytest.fixture
def extraction_tool():
    """Create DocumentExtractionTool instance."""
    return DocumentExtractionTool()


class TestDocumentExtractionToolSpec:
    """Tests for DocumentExtractionTool specification."""

    def test_get_spec_returns_tool_spec(self, extraction_tool):
        """Test get_spec returns valid ToolSpec."""
        spec = extraction_tool.get_spec()

        assert spec.name == "extract_document_text"
        assert spec.version == "1.0.0"
        assert spec.display_name == "Document Text Extractor"
        assert spec.category == ToolCategory.DOCUMENT_ANALYSIS

    def test_spec_capabilities(self, extraction_tool):
        """Test tool capabilities are correct."""
        spec = extraction_tool.get_spec()

        assert ToolCapability.ASYNC in spec.capabilities
        assert ToolCapability.IDEMPOTENT in spec.capabilities
        assert ToolCapability.CACHEABLE in spec.capabilities

    def test_spec_input_schema(self, extraction_tool):
        """Test input schema structure."""
        spec = extraction_tool.get_spec()
        schema = spec.input_schema

        assert schema["type"] == "object"
        assert "doc_id" in schema["properties"]
        assert "method" in schema["properties"]
        assert "page_numbers" in schema["properties"]
        assert "doc_id" in schema["required"]

    def test_spec_extraction_methods(self, extraction_tool):
        """Test supported extraction methods."""
        spec = extraction_tool.get_spec()
        methods = spec.input_schema["properties"]["method"]["enum"]

        assert "auto" in methods
        assert "pypdf" in methods
        assert "saptiva_sdk" in methods
        assert "ocr" in methods

    def test_spec_rate_limit(self, extraction_tool):
        """Test rate limit is configured."""
        spec = extraction_tool.get_spec()

        assert spec.rate_limit["calls_per_minute"] == 30

    def test_spec_timeout(self, extraction_tool):
        """Test timeout is 60 seconds for OCR."""
        spec = extraction_tool.get_spec()

        assert spec.timeout_ms == 60000


class TestDocumentExtractionToolValidateInput:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_valid_input_minimal(self, extraction_tool):
        """Test valid input with only required field."""
        payload = {"doc_id": "doc-123"}

        # Should not raise
        await extraction_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_valid_input_full(self, extraction_tool):
        """Test valid input with all fields."""
        payload = {
            "doc_id": "doc-123",
            "method": "pypdf",
            "page_numbers": [1, 2, 3],
            "include_metadata": True,
            "cache_ttl_seconds": 7200,
        }

        # Should not raise
        await extraction_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_missing_doc_id(self, extraction_tool):
        """Test validation fails without doc_id."""
        payload = {"method": "auto"}

        with pytest.raises(ValueError, match="Missing required field: doc_id"):
            await extraction_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_doc_id_not_string(self, extraction_tool):
        """Test validation fails if doc_id is not a string."""
        payload = {"doc_id": 123}

        with pytest.raises(ValueError, match="doc_id must be a string"):
            await extraction_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_invalid_method(self, extraction_tool):
        """Test validation fails for invalid method."""
        payload = {"doc_id": "doc-123", "method": "invalid"}

        with pytest.raises(ValueError, match="Invalid method"):
            await extraction_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_page_numbers_not_array(self, extraction_tool):
        """Test validation fails if page_numbers is not an array."""
        payload = {"doc_id": "doc-123", "page_numbers": "1,2,3"}

        with pytest.raises(ValueError, match="page_numbers must be an array"):
            await extraction_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_page_numbers_invalid_values(self, extraction_tool):
        """Test validation fails for invalid page numbers."""
        payload = {"doc_id": "doc-123", "page_numbers": [1, 0, 3]}

        with pytest.raises(ValueError, match="page_numbers must contain positive integers"):
            await extraction_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_page_numbers_non_integer(self, extraction_tool):
        """Test validation fails for non-integer page numbers."""
        payload = {"doc_id": "doc-123", "page_numbers": [1, "two", 3]}

        with pytest.raises(ValueError, match="page_numbers must contain positive integers"):
            await extraction_tool.validate_input(payload)


class TestDocumentExtractionToolNormalizePages:
    """Tests for _normalize_pages static method."""

    def test_normalize_empty_pages(self, extraction_tool):
        """Test normalizing empty pages."""
        result = extraction_tool._normalize_pages(None)
        assert result == []

        result = extraction_tool._normalize_pages([])
        assert result == []

    def test_normalize_pages_with_text(self, extraction_tool):
        """Test normalizing pages with text field."""
        pages = [
            {"page_number": 1, "text": "Page one content", "word_count": 3},
            {"page_number": 2, "text": "Page two content here", "word_count": 4},
        ]

        result = extraction_tool._normalize_pages(pages)

        assert len(result) == 2
        assert result[0]["page_number"] == 1
        assert result[0]["text"] == "Page one content"
        assert result[0]["word_count"] == 3
        assert result[1]["page_number"] == 2

    def test_normalize_pages_with_text_md(self, extraction_tool):
        """Test normalizing pages with text_md field (fallback)."""
        pages = [
            {"page": 1, "text_md": "# Markdown content"},
        ]

        result = extraction_tool._normalize_pages(pages)

        assert len(result) == 1
        assert result[0]["page_number"] == 1
        assert result[0]["text"] == "# Markdown content"

    def test_normalize_pages_calculates_word_count(self, extraction_tool):
        """Test word count is calculated if not provided."""
        pages = [
            {"page_number": 1, "text": "one two three four five"},
        ]

        result = extraction_tool._normalize_pages(pages)

        assert result[0]["word_count"] == 5


class TestDocumentExtractionToolExecute:
    """Tests for tool execution."""

    @pytest.mark.asyncio
    async def test_execute_document_not_found(self, extraction_tool):
        """Test execution fails when document not found."""
        payload = {"doc_id": "doc-999"}

        with patch("src.mcp_integration.tools.document_extraction_tool.Document") as mock_doc:
            mock_doc.get = AsyncMock(return_value=None)

            with pytest.raises(ValueError, match="Document not found: doc-999"):
                await extraction_tool.execute(payload, context={"user_id": "user-123"})

    @pytest.mark.asyncio
    async def test_execute_permission_denied(self, extraction_tool):
        """Test execution fails when user doesn't own document."""
        payload = {"doc_id": "doc-123"}

        mock_doc = MagicMock()
        mock_doc.user_id = "other-user"

        with patch("src.mcp_integration.tools.document_extraction_tool.Document") as mock_doc_class:
            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            with pytest.raises(PermissionError, match="not authorized"):
                await extraction_tool.execute(payload, context={"user_id": "user-123"})

    @pytest.mark.asyncio
    async def test_execute_unsupported_content_type(self, extraction_tool):
        """Test execution fails for unsupported document types."""
        payload = {"doc_id": "doc-123"}

        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "text/plain"

        with patch("src.mcp_integration.tools.document_extraction_tool.Document") as mock_doc_class:
            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            with pytest.raises(ValueError, match="Unsupported document type"):
                await extraction_tool.execute(payload, context={"user_id": "user-123"})

    @pytest.mark.asyncio
    async def test_execute_pdf_success(self, extraction_tool):
        """Test successful PDF extraction."""
        payload = {"doc_id": "doc-123", "include_metadata": True}

        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/pdf"
        mock_doc.minio_key = "test/file.pdf"
        mock_doc.filename = "file.pdf"
        mock_doc.size_bytes = 12345

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        extraction_result = {
            "text": "Extracted PDF content",
            "method": "pypdf",
            "pages": [{"page_number": 1, "text": "Page 1 content", "word_count": 3}],
        }

        with patch("src.mcp_integration.tools.document_extraction_tool.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.document_extraction_tool.get_minio_storage") as mock_storage_func, \
             patch("src.mcp_integration.tools.document_extraction_tool.extract_text_from_pdf", new_callable=AsyncMock) as mock_extract:

            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            mock_storage = MagicMock()
            mock_storage.materialize_document.return_value = (mock_path, True)
            mock_storage_func.return_value = mock_storage

            mock_extract.return_value = extraction_result

            result = await extraction_tool.execute(payload, context={"user_id": "user-123"})

            assert result["doc_id"] == "doc-123"
            assert result["text"] == "Extracted PDF content"
            assert result["method_used"] == "pypdf"
            assert "metadata" in result
            assert result["metadata"]["filename"] == "file.pdf"
            assert result["metadata"]["cached"] is False
            mock_path.unlink.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_cache_hit(self, extraction_tool):
        """Test extraction with cache hit."""
        payload = {"doc_id": "doc-123", "method": "auto"}

        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/pdf"
        mock_doc.filename = "cached.pdf"
        mock_doc.size_bytes = 5000

        cache_response = {"doc-123": {"text": "Cached text content"}}

        with patch("src.mcp_integration.tools.document_extraction_tool.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.document_extraction_tool.DocumentService") as mock_doc_service:

            mock_doc_class.get = AsyncMock(return_value=mock_doc)
            mock_doc_service.get_document_text_from_cache = AsyncMock(return_value=cache_response)

            result = await extraction_tool.execute(payload, context={"user_id": "user-123"})

            assert result["text"] == "Cached text content"
            assert result["method_used"] == "cache"
            assert result["metadata"]["cached"] is True

    @pytest.mark.asyncio
    async def test_execute_cache_miss_fallback(self, extraction_tool):
        """Test extraction falls back when cache misses."""
        payload = {"doc_id": "doc-123", "method": "auto"}

        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/pdf"
        mock_doc.minio_key = "test/file.pdf"
        mock_doc.filename = "file.pdf"
        mock_doc.size_bytes = 10000

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        extraction_result = {
            "text": "Freshly extracted text",
            "method": "saptiva_sdk",
        }

        with patch("src.mcp_integration.tools.document_extraction_tool.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.document_extraction_tool.DocumentService") as mock_doc_service, \
             patch("src.mcp_integration.tools.document_extraction_tool.get_minio_storage") as mock_storage_func, \
             patch("src.mcp_integration.tools.document_extraction_tool.extract_text_from_pdf", new_callable=AsyncMock) as mock_extract:

            mock_doc_class.get = AsyncMock(return_value=mock_doc)
            # Cache returns empty
            mock_doc_service.get_document_text_from_cache = AsyncMock(return_value={})

            mock_storage = MagicMock()
            mock_storage.materialize_document.return_value = (mock_path, True)
            mock_storage_func.return_value = mock_storage

            mock_extract.return_value = extraction_result

            result = await extraction_tool.execute(payload, context={"user_id": "user-123"})

            assert result["text"] == "Freshly extracted text"
            assert result["method_used"] == "saptiva_sdk"
            assert result["metadata"]["cached"] is False

    @pytest.mark.asyncio
    async def test_execute_image_support(self, extraction_tool):
        """Test extraction supports image files."""
        for content_type in ["image/png", "image/jpeg", "image/tiff"]:
            payload = {"doc_id": "doc-123"}

            mock_doc = MagicMock()
            mock_doc.user_id = "user-123"
            mock_doc.content_type = content_type
            mock_doc.minio_key = "test/image.png"
            mock_doc.filename = "image.png"
            mock_doc.size_bytes = 5000

            mock_path = MagicMock(spec=Path)
            mock_path.exists.return_value = True

            with patch("src.mcp_integration.tools.document_extraction_tool.Document") as mock_doc_class, \
                 patch("src.mcp_integration.tools.document_extraction_tool.get_minio_storage") as mock_storage_func, \
                 patch("src.mcp_integration.tools.document_extraction_tool.extract_text_from_pdf", new_callable=AsyncMock) as mock_extract:

                mock_doc_class.get = AsyncMock(return_value=mock_doc)

                mock_storage = MagicMock()
                mock_storage.materialize_document.return_value = (mock_path, True)
                mock_storage_func.return_value = mock_storage

                mock_extract.return_value = {"text": "OCR text", "method": "ocr"}

                result = await extraction_tool.execute(payload, context={"user_id": "user-123"})

                assert result["text"] == "OCR text"

    @pytest.mark.asyncio
    async def test_execute_no_user_id_skips_cache(self, extraction_tool):
        """Test extraction without user_id skips cache lookup."""
        payload = {"doc_id": "doc-123", "method": "auto"}

        mock_doc = MagicMock()
        mock_doc.user_id = "any-user"  # Not checked without user_id
        mock_doc.content_type = "application/pdf"
        mock_doc.minio_key = "test/file.pdf"
        mock_doc.filename = "file.pdf"
        mock_doc.size_bytes = 5000

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch("src.mcp_integration.tools.document_extraction_tool.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.document_extraction_tool.DocumentService") as mock_doc_service, \
             patch("src.mcp_integration.tools.document_extraction_tool.get_minio_storage") as mock_storage_func, \
             patch("src.mcp_integration.tools.document_extraction_tool.extract_text_from_pdf", new_callable=AsyncMock) as mock_extract:

            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            mock_storage = MagicMock()
            mock_storage.materialize_document.return_value = (mock_path, True)
            mock_storage_func.return_value = mock_storage

            mock_extract.return_value = {"text": "No cache check", "method": "pypdf"}

            result = await extraction_tool.execute(payload, context=None)

            # Cache should not be called without user_id
            mock_doc_service.get_document_text_from_cache.assert_not_called()
            assert result["text"] == "No cache check"

    @pytest.mark.asyncio
    async def test_execute_with_page_numbers_filter(self, extraction_tool):
        """Test extraction filters pages when page_numbers specified."""
        payload = {"doc_id": "doc-123", "page_numbers": [1, 3]}

        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/pdf"
        mock_doc.minio_key = "test/file.pdf"
        mock_doc.filename = "file.pdf"
        mock_doc.size_bytes = 10000

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        extraction_result = {
            "text": "All pages",
            "method": "pypdf",
            "pages": [
                {"page_number": 1, "text": "Page 1"},
                {"page_number": 2, "text": "Page 2"},
                {"page_number": 3, "text": "Page 3"},
            ],
        }

        with patch("src.mcp_integration.tools.document_extraction_tool.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.document_extraction_tool.get_minio_storage") as mock_storage_func, \
             patch("src.mcp_integration.tools.document_extraction_tool.extract_text_from_pdf", new_callable=AsyncMock) as mock_extract:

            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            mock_storage = MagicMock()
            mock_storage.materialize_document.return_value = (mock_path, True)
            mock_storage_func.return_value = mock_storage

            mock_extract.return_value = extraction_result

            result = await extraction_tool.execute(payload, context={"user_id": "user-123"})

            # Only pages 1 and 3 should be in result
            assert len(result["pages"]) == 2
            page_numbers = [p["page_number"] for p in result["pages"]]
            assert 1 in page_numbers
            assert 3 in page_numbers
            assert 2 not in page_numbers

    @pytest.mark.asyncio
    async def test_execute_without_metadata(self, extraction_tool):
        """Test extraction without metadata."""
        payload = {"doc_id": "doc-123", "include_metadata": False}

        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/pdf"
        mock_doc.minio_key = "test/file.pdf"
        mock_doc.filename = "file.pdf"
        mock_doc.size_bytes = 5000

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch("src.mcp_integration.tools.document_extraction_tool.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.document_extraction_tool.get_minio_storage") as mock_storage_func, \
             patch("src.mcp_integration.tools.document_extraction_tool.extract_text_from_pdf", new_callable=AsyncMock) as mock_extract:

            mock_doc_class.get = AsyncMock(return_value=mock_doc)

            mock_storage = MagicMock()
            mock_storage.materialize_document.return_value = (mock_path, True)
            mock_storage_func.return_value = mock_storage

            mock_extract.return_value = {"text": "Content", "method": "pypdf"}

            result = await extraction_tool.execute(payload, context={"user_id": "user-123"})

            assert "metadata" not in result

    @pytest.mark.asyncio
    async def test_execute_cache_error_fallback(self, extraction_tool):
        """Test extraction falls back when cache lookup fails."""
        payload = {"doc_id": "doc-123", "method": "auto"}

        mock_doc = MagicMock()
        mock_doc.user_id = "user-123"
        mock_doc.content_type = "application/pdf"
        mock_doc.minio_key = "test/file.pdf"
        mock_doc.filename = "file.pdf"
        mock_doc.size_bytes = 5000

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        with patch("src.mcp_integration.tools.document_extraction_tool.Document") as mock_doc_class, \
             patch("src.mcp_integration.tools.document_extraction_tool.DocumentService") as mock_doc_service, \
             patch("src.mcp_integration.tools.document_extraction_tool.get_minio_storage") as mock_storage_func, \
             patch("src.mcp_integration.tools.document_extraction_tool.extract_text_from_pdf", new_callable=AsyncMock) as mock_extract:

            mock_doc_class.get = AsyncMock(return_value=mock_doc)
            # Cache raises exception
            mock_doc_service.get_document_text_from_cache = AsyncMock(
                side_effect=Exception("Redis connection failed")
            )

            mock_storage = MagicMock()
            mock_storage.materialize_document.return_value = (mock_path, True)
            mock_storage_func.return_value = mock_storage

            mock_extract.return_value = {"text": "Fallback text", "method": "pypdf"}

            # Should not raise, should fall back to extraction
            result = await extraction_tool.execute(payload, context={"user_id": "user-123"})

            assert result["text"] == "Fallback text"
            assert result["metadata"]["cached"] is False
