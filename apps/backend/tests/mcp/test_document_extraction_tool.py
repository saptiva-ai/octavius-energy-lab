"""Tests for DocumentExtractionTool (MCP)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import os

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MCP_DOCUMENT_EXTRACTION", "false").lower() != "true",
    reason="MCP document extraction tests deshabilitados por defecto (requires full stack)",
)

from src.mcp_integration.tools.document_extraction_tool import DocumentExtractionTool
from src.mcp_integration.protocol import ToolCategory, ToolCapability
from src.models.document import Document


@pytest.fixture
def document_extraction_tool():
    """Create DocumentExtractionTool instance."""
    return DocumentExtractionTool()


@pytest.fixture
def mock_document():
    """Create mock document."""
    doc = MagicMock(spec=Document)
    doc.id = "doc_123"
    doc.filename = "test.pdf"
    doc.content_type = "application/pdf"
    doc.size_bytes = 100000
    doc.user_id = "user_123"
    doc.minio_key = "documents/test.pdf"
    return doc


class TestDocumentExtractionToolSpec:
    """Test tool specification."""

    def test_get_spec(self, document_extraction_tool):
        """Test tool specification structure."""
        spec = document_extraction_tool.get_spec()

        assert spec.name == "extract_document_text"
        assert spec.version == "1.0.0"
        assert spec.category == ToolCategory.DOCUMENT_ANALYSIS
        assert ToolCapability.ASYNC in spec.capabilities
        assert ToolCapability.IDEMPOTENT in spec.capabilities
        assert ToolCapability.CACHEABLE in spec.capabilities
        assert spec.requires_auth is True
        assert spec.timeout_ms == 60000  # 60 seconds

    def test_input_schema(self, document_extraction_tool):
        """Test input schema structure."""
        spec = document_extraction_tool.get_spec()
        schema = spec.input_schema

        assert schema["type"] == "object"
        assert "doc_id" in schema["required"]
        assert "doc_id" in schema["properties"]
        assert "method" in schema["properties"]
        assert schema["properties"]["method"]["enum"] == ["auto", "pypdf", "saptiva_sdk", "ocr"]

    def test_output_schema(self, document_extraction_tool):
        """Test output schema structure."""
        spec = document_extraction_tool.get_spec()
        schema = spec.output_schema

        assert schema["type"] == "object"
        assert "doc_id" in schema["properties"]
        assert "text" in schema["properties"]
        assert "method_used" in schema["properties"]
        assert "metadata" in schema["properties"]


class TestDocumentExtractionToolValidation:
    """Test input validation."""

    @pytest.mark.asyncio
    async def test_validate_input_success(self, document_extraction_tool):
        """Test successful input validation."""
        payload = {
            "doc_id": "doc_123",
            "method": "auto",
        }

        # Should not raise
        await document_extraction_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_validate_input_missing_doc_id(self, document_extraction_tool):
        """Test validation fails when doc_id is missing."""
        payload = {"method": "auto"}

        with pytest.raises(ValueError, match="Missing required field: doc_id"):
            await document_extraction_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_validate_input_invalid_method(self, document_extraction_tool):
        """Test validation fails with invalid method."""
        payload = {
            "doc_id": "doc_123",
            "method": "invalid_method",
        }

        with pytest.raises(ValueError, match="Invalid method"):
            await document_extraction_tool.validate_input(payload)

    @pytest.mark.asyncio
    async def test_validate_input_invalid_page_numbers(self, document_extraction_tool):
        """Test validation fails with invalid page_numbers."""
        payload = {
            "doc_id": "doc_123",
            "page_numbers": [1, 0, -1],  # 0 and -1 are invalid
        }

        with pytest.raises(ValueError, match="page_numbers must contain positive integers"):
            await document_extraction_tool.validate_input(payload)


class TestDocumentExtractionToolExecution:
    """Test tool execution."""

    @pytest.mark.asyncio
    async def test_execute_success_from_cache(self, document_extraction_tool, mock_document):
        """Test successful execution with cached text."""
        payload = {
            "doc_id": "doc_123",
            "method": "auto",
        }
        context = {"user_id": "user_123"}

        cached_text = "This is cached text content"

        with patch("src.mcp_integration.tools.document_extraction_tool.Document.get", return_value=mock_document):
            with patch(
                "src.mcp_integration.tools.document_extraction_tool.DocumentService.get_document_text_from_cache",
                new_callable=AsyncMock,
                return_value={"doc_123": {"text": cached_text}},
            ):
                result = await document_extraction_tool.execute(payload, context)

                assert result["doc_id"] == "doc_123"
                assert result["text"] == cached_text
                assert result["method_used"] == "cache"
                assert result["metadata"]["cached"] is True
                assert result["metadata"]["word_count"] == 4

    @pytest.mark.asyncio
    async def test_execute_success_extraction(self, document_extraction_tool, mock_document):
        """Test successful execution with text extraction."""
        payload = {
            "doc_id": "doc_123",
            "method": "auto",
        }
        context = {"user_id": "user_123"}

        extracted_text = "This is extracted text content"
        extraction_result = {
            "text": extracted_text,
            "method": "pypdf",
        }

        mock_storage = MagicMock()
        mock_storage.materialize_document.return_value = (Path("/tmp/test.pdf"), True)

        with patch("src.mcp_integration.tools.document_extraction_tool.Document.get", return_value=mock_document):
            with patch(
                "src.mcp_integration.tools.document_extraction_tool.DocumentService.get_document_text_from_cache",
                new_callable=AsyncMock,
                return_value={},
            ):
                with patch(
                    "src.mcp_integration.tools.document_extraction_tool.get_minio_storage",
                    return_value=mock_storage,
                ):
                    with patch(
                        "src.mcp_integration.tools.document_extraction_tool.extract_text_from_pdf",
                        new_callable=AsyncMock,
                        return_value=extraction_result,
                    ):
                        result = await document_extraction_tool.execute(payload, context)

                        assert result["doc_id"] == "doc_123"
                        assert result["text"] == extracted_text
                        assert result["method_used"] == "pypdf"
                        assert result["metadata"]["cached"] is False

    @pytest.mark.asyncio
    async def test_execute_document_not_found(self, document_extraction_tool):
        """Test execution fails when document not found."""
        payload = {"doc_id": "nonexistent"}
        context = {}

        with patch("src.mcp_integration.tools.document_extraction_tool.Document.get", return_value=None):
            with pytest.raises(ValueError, match="Document not found"):
                await document_extraction_tool.execute(payload, context)

    @pytest.mark.asyncio
    async def test_execute_permission_denied(self, document_extraction_tool, mock_document):
        """Test execution fails with permission denied."""
        payload = {"doc_id": "doc_123"}
        context = {"user_id": "different_user"}

        with patch("src.mcp_integration.tools.document_extraction_tool.Document.get", return_value=mock_document):
            with pytest.raises(PermissionError, match="not authorized"):
                await document_extraction_tool.execute(payload, context)

    @pytest.mark.asyncio
    async def test_execute_unsupported_file_type(self, document_extraction_tool, mock_document):
        """Test execution fails with unsupported file type."""
        mock_document.content_type = "text/plain"
        payload = {"doc_id": "doc_123"}
        context = {"user_id": "user_123"}

        with patch("src.mcp_integration.tools.document_extraction_tool.Document.get", return_value=mock_document):
            with pytest.raises(ValueError, match="Unsupported document type"):
                await document_extraction_tool.execute(payload, context)

    @pytest.mark.asyncio
    async def test_execute_with_metadata(self, document_extraction_tool, mock_document):
        """Test execution includes metadata."""
        payload = {
            "doc_id": "doc_123",
            "include_metadata": True,
        }
        context = {"user_id": "user_123"}

        cached_text = "Test content"

        with patch("src.mcp_integration.tools.document_extraction_tool.Document.get", return_value=mock_document):
            with patch(
                "src.mcp_integration.tools.document_extraction_tool.DocumentService.get_document_text_from_cache",
                new_callable=AsyncMock,
                return_value={"doc_123": {"text": cached_text}},
            ):
                result = await document_extraction_tool.execute(payload, context)

                assert "metadata" in result
                assert result["metadata"]["filename"] == "test.pdf"
                assert result["metadata"]["content_type"] == "application/pdf"
                assert result["metadata"]["size_bytes"] == 100000
                assert result["metadata"]["char_count"] == len(cached_text)
                assert result["metadata"]["word_count"] == 2
                assert "extraction_duration_ms" in result["metadata"]

    @pytest.mark.asyncio
    async def test_execute_without_metadata(self, document_extraction_tool, mock_document):
        """Test execution without metadata."""
        payload = {
            "doc_id": "doc_123",
            "include_metadata": False,
        }
        context = {"user_id": "user_123"}

        cached_text = "Test content"

        with patch("src.mcp_integration.tools.document_extraction_tool.Document.get", return_value=mock_document):
            with patch(
                "src.mcp_integration.tools.document_extraction_tool.DocumentService.get_document_text_from_cache",
                new_callable=AsyncMock,
                return_value={"doc_123": {"text": cached_text}},
            ):
                result = await document_extraction_tool.execute(payload, context)

                assert "metadata" not in result
                assert result["text"] == cached_text


class TestDocumentExtractionToolInvoke:
    """Test full invocation lifecycle."""

    @pytest.mark.asyncio
    async def test_invoke_success(self, document_extraction_tool, mock_document):
        """Test successful tool invocation."""
        payload = {"doc_id": "doc_123"}

        cached_text = "Cached content"

        with patch("src.mcp_integration.tools.document_extraction_tool.Document.get", return_value=mock_document):
            with patch(
                "src.mcp_integration.tools.document_extraction_tool.DocumentService.get_document_text_from_cache",
                new_callable=AsyncMock,
                return_value={"doc_123": {"text": cached_text}},
            ):
                response = await document_extraction_tool.invoke(payload, context={"user_id": "user_123"})

                assert response.success is True
                assert response.tool == "extract_document_text"
                assert response.version == "1.0.0"
                assert response.result is not None
                assert response.result["text"] == cached_text
                assert response.error is None
                assert response.duration_ms > 0

    @pytest.mark.asyncio
    async def test_invoke_validation_error(self, document_extraction_tool):
        """Test invocation with validation error."""
        payload = {}  # Missing doc_id

        response = await document_extraction_tool.invoke(payload)

        assert response.success is False
        assert response.error is not None
        assert response.error.code == "INVALID_INPUT"
        assert "doc_id" in response.error.message

    @pytest.mark.asyncio
    async def test_invoke_execution_error(self, document_extraction_tool):
        """Test invocation with execution error."""
        payload = {"doc_id": "doc_123"}

        with patch(
            "src.mcp_integration.tools.document_extraction_tool.Document.get",
            side_effect=Exception("Database error"),
        ):
            response = await document_extraction_tool.invoke(payload)

            assert response.success is False
            assert response.error is not None
            assert response.error.code == "EXECUTION_ERROR"
            assert "Database error" in response.error.message

    @pytest.mark.asyncio
    async def test_invoke_with_context(self, document_extraction_tool, mock_document):
        """Test invocation preserves context."""
        payload = {"doc_id": "doc_123"}
        context = {
            "user_id": "user_123",
            "trace_id": "trace_456",
        }

        cached_text = "Test"

        with patch("src.mcp_integration.tools.document_extraction_tool.Document.get", return_value=mock_document):
            with patch(
                "src.mcp_integration.tools.document_extraction_tool.DocumentService.get_document_text_from_cache",
                new_callable=AsyncMock,
                return_value={"doc_123": {"text": cached_text}},
            ):
                response = await document_extraction_tool.invoke(payload, context=context)

                assert response.success is True
                assert "context" in response.metadata
                assert response.metadata["context"]["user_id"] == "user_123"
                assert response.metadata["context"]["trace_id"] == "trace_456"
