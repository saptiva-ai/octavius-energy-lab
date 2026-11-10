"""
Unit tests for AuditDocumentResolver service.

Tests document resolution logic for audit operations.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.streaming.audit_document_resolver import (
    AuditDocumentResolver,
    ResolvedDocument,
    ResolutionError,
)


class TestResolvedDocumentDataclass:
    """Tests for ResolvedDocument dataclass."""

    def test_creation(self):
        """Test basic creation of ResolvedDocument."""
        mock_doc = MagicMock()
        mock_doc.id = "doc-123"
        mock_doc.filename = "test.pdf"

        resolved = ResolvedDocument(
            document=mock_doc,
            pdf_path=Path("/tmp/test.pdf"),
            is_temp=True,
        )

        assert resolved.document == mock_doc
        assert resolved.pdf_path == Path("/tmp/test.pdf")
        assert resolved.is_temp is True

    def test_creation_not_temp(self):
        """Test creation with is_temp=False."""
        mock_doc = MagicMock()
        resolved = ResolvedDocument(
            document=mock_doc,
            pdf_path=Path("/data/file.pdf"),
            is_temp=False,
        )

        assert resolved.is_temp is False

    def test_different_path_types(self):
        """Test with various path types."""
        mock_doc = MagicMock()

        resolved = ResolvedDocument(
            document=mock_doc,
            pdf_path=Path("/mnt/storage/docs/report.pdf"),
            is_temp=True,
        )

        assert str(resolved.pdf_path) == "/mnt/storage/docs/report.pdf"


class TestResolutionErrorDataclass:
    """Tests for ResolutionError dataclass."""

    def test_creation(self):
        """Test basic creation of ResolutionError."""
        error = ResolutionError(
            error_code="document_not_found",
            error_message="File not found",
        )

        assert error.error_code == "document_not_found"
        assert error.error_message == "File not found"

    def test_storage_unavailable_error(self):
        """Test storage unavailable error."""
        error = ResolutionError(
            error_code="storage_unavailable",
            error_message="Sistema de almacenamiento no disponible",
        )

        assert error.error_code == "storage_unavailable"
        assert "almacenamiento" in error.error_message

    def test_materialization_failed_error(self):
        """Test materialization failed error."""
        error = ResolutionError(
            error_code="pdf_materialization_failed",
            error_message="Error al cargar el archivo: Connection timeout",
        )

        assert error.error_code == "pdf_materialization_failed"
        assert "Connection timeout" in error.error_message


class TestExtractFilenameFromCommand:
    """Tests for extract_filename_from_command method."""

    def test_basic_extraction(self):
        """Test basic filename extraction."""
        message = "Auditar archivo: report.pdf"
        result = AuditDocumentResolver.extract_filename_from_command(message)
        assert result == "report.pdf"

    def test_with_extra_whitespace(self):
        """Test extraction with extra whitespace."""
        message = "  Auditar archivo:   financial_report.pdf  "
        result = AuditDocumentResolver.extract_filename_from_command(message)
        assert result == "financial_report.pdf"

    def test_filename_with_spaces(self):
        """Test extraction of filename containing spaces."""
        message = "Auditar archivo: my document with spaces.pdf"
        result = AuditDocumentResolver.extract_filename_from_command(message)
        assert result == "my document with spaces.pdf"

    def test_filename_with_special_chars(self):
        """Test extraction of filename with special characters."""
        message = "Auditar archivo: report_2024-01_v2.pdf"
        result = AuditDocumentResolver.extract_filename_from_command(message)
        assert result == "report_2024-01_v2.pdf"

    def test_empty_filename(self):
        """Test extraction when filename is empty."""
        message = "Auditar archivo:"
        result = AuditDocumentResolver.extract_filename_from_command(message)
        assert result == ""

    def test_no_prefix(self):
        """Test extraction when prefix is missing."""
        message = "some_file.pdf"
        result = AuditDocumentResolver.extract_filename_from_command(message)
        assert result == "some_file.pdf"

    def test_unicode_filename(self):
        """Test extraction with unicode characters."""
        message = "Auditar archivo: informe_año_2024.pdf"
        result = AuditDocumentResolver.extract_filename_from_command(message)
        assert result == "informe_año_2024.pdf"


class TestFindDocumentByFilename:
    """Tests for find_document_by_filename method."""

    @pytest.mark.asyncio
    async def test_find_existing_document(self):
        """Test finding an existing document."""
        mock_doc = MagicMock()
        mock_doc.filename = "report.pdf"

        with patch(
            "src.services.streaming.audit_document_resolver.Document"
        ) as mock_document_class:
            mock_document_class.get = AsyncMock(return_value=mock_doc)

            result = await AuditDocumentResolver.find_document_by_filename(
                "report.pdf", ["doc-123"]
            )

            assert result == mock_doc
            mock_document_class.get.assert_awaited_once_with("doc-123")

    @pytest.mark.asyncio
    async def test_find_document_no_match(self):
        """Test when no document matches the filename."""
        mock_doc = MagicMock()
        mock_doc.filename = "other.pdf"

        with patch(
            "src.services.streaming.audit_document_resolver.Document"
        ) as mock_document_class:
            mock_document_class.get = AsyncMock(return_value=mock_doc)

            result = await AuditDocumentResolver.find_document_by_filename(
                "report.pdf", ["doc-123"]
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_find_document_empty_ids(self):
        """Test with empty document IDs list."""
        result = await AuditDocumentResolver.find_document_by_filename("report.pdf", [])
        assert result is None

    @pytest.mark.asyncio
    async def test_find_document_none_ids(self):
        """Test with None document IDs."""
        result = await AuditDocumentResolver.find_document_by_filename(
            "report.pdf", None
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_find_document_multiple_ids(self):
        """Test searching through multiple document IDs."""
        mock_doc1 = MagicMock()
        mock_doc1.filename = "other1.pdf"
        mock_doc2 = MagicMock()
        mock_doc2.filename = "report.pdf"
        mock_doc3 = MagicMock()
        mock_doc3.filename = "other2.pdf"

        with patch(
            "src.services.streaming.audit_document_resolver.Document"
        ) as mock_document_class:
            mock_document_class.get = AsyncMock(
                side_effect=[mock_doc1, mock_doc2, mock_doc3]
            )

            result = await AuditDocumentResolver.find_document_by_filename(
                "report.pdf", ["doc-1", "doc-2", "doc-3"]
            )

            assert result == mock_doc2
            assert mock_document_class.get.await_count == 2

    @pytest.mark.asyncio
    async def test_find_document_handles_exception(self):
        """Test handling exceptions when loading documents."""
        with patch(
            "src.services.streaming.audit_document_resolver.Document"
        ) as mock_document_class:
            mock_document_class.get = AsyncMock(
                side_effect=Exception("Database error")
            )

            result = await AuditDocumentResolver.find_document_by_filename(
                "report.pdf", ["doc-123"]
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_find_document_continues_after_exception(self):
        """Test that search continues after an exception."""
        mock_doc = MagicMock()
        mock_doc.filename = "report.pdf"

        with patch(
            "src.services.streaming.audit_document_resolver.Document"
        ) as mock_document_class:
            mock_document_class.get = AsyncMock(
                side_effect=[Exception("Error"), mock_doc]
            )

            result = await AuditDocumentResolver.find_document_by_filename(
                "report.pdf", ["doc-1", "doc-2"]
            )

            assert result == mock_doc

    @pytest.mark.asyncio
    async def test_find_document_returns_none_for_none_doc(self):
        """Test when Document.get returns None."""
        with patch(
            "src.services.streaming.audit_document_resolver.Document"
        ) as mock_document_class:
            mock_document_class.get = AsyncMock(return_value=None)

            result = await AuditDocumentResolver.find_document_by_filename(
                "report.pdf", ["doc-123"]
            )

            assert result is None


class TestMaterializePdf:
    """Tests for materialize_pdf method."""

    def test_file_exists_locally(self):
        """Test when file already exists locally."""
        mock_doc = MagicMock()
        mock_doc.minio_key = "/tmp/existing.pdf"

        with patch.object(Path, "exists", return_value=True):
            pdf_path, is_temp, error = AuditDocumentResolver.materialize_pdf(mock_doc)

            assert pdf_path == Path("/tmp/existing.pdf")
            assert is_temp is False
            assert error is None

    def test_storage_unavailable(self):
        """Test when MinIO storage is unavailable."""
        mock_doc = MagicMock()
        mock_doc.minio_key = "/storage/file.pdf"

        with (
            patch.object(Path, "exists", return_value=False),
            patch(
                "src.services.streaming.audit_document_resolver.get_minio_storage",
                return_value=None,
            ),
        ):
            pdf_path, is_temp, error = AuditDocumentResolver.materialize_pdf(mock_doc)

            assert pdf_path is None
            assert is_temp is False
            assert error is not None
            assert error.error_code == "storage_unavailable"

    def test_successful_materialization(self):
        """Test successful PDF materialization from MinIO."""
        mock_doc = MagicMock()
        mock_doc.minio_key = "docs/report.pdf"
        mock_doc.filename = "report.pdf"
        mock_doc.minio_bucket = "documents"

        mock_storage = MagicMock()
        mock_storage.materialize_document.return_value = (
            Path("/tmp/materialized.pdf"),
            True,
        )

        with (
            patch.object(Path, "exists", return_value=False),
            patch(
                "src.services.streaming.audit_document_resolver.get_minio_storage",
                return_value=mock_storage,
            ),
        ):
            pdf_path, is_temp, error = AuditDocumentResolver.materialize_pdf(mock_doc)

            assert pdf_path == Path("/tmp/materialized.pdf")
            assert is_temp is True
            assert error is None
            mock_storage.materialize_document.assert_called_once_with(
                "docs/report.pdf",
                filename="report.pdf",
                bucket="documents",
            )

    def test_materialization_failure(self):
        """Test handling materialization failure."""
        mock_doc = MagicMock()
        mock_doc.id = "doc-123"
        mock_doc.minio_key = "docs/report.pdf"
        mock_doc.filename = "report.pdf"
        mock_doc.minio_bucket = "documents"

        mock_storage = MagicMock()
        mock_storage.materialize_document.side_effect = Exception("Connection timeout")

        with (
            patch.object(Path, "exists", return_value=False),
            patch(
                "src.services.streaming.audit_document_resolver.get_minio_storage",
                return_value=mock_storage,
            ),
        ):
            pdf_path, is_temp, error = AuditDocumentResolver.materialize_pdf(mock_doc)

            assert pdf_path is None
            assert is_temp is False
            assert error is not None
            assert error.error_code == "pdf_materialization_failed"
            assert "Connection timeout" in error.error_message


class TestResolve:
    """Tests for resolve method (integration of all steps)."""

    @pytest.mark.asyncio
    async def test_resolve_success(self):
        """Test successful document resolution."""
        mock_doc = MagicMock()
        mock_doc.filename = "report.pdf"
        mock_doc.minio_key = "docs/report.pdf"
        mock_doc.minio_bucket = "documents"
        mock_doc.id = "doc-123"

        mock_storage = MagicMock()
        mock_storage.materialize_document.return_value = (
            Path("/tmp/report.pdf"),
            True,
        )

        with (
            patch(
                "src.services.streaming.audit_document_resolver.Document"
            ) as mock_document_class,
            patch.object(Path, "exists", return_value=False),
            patch(
                "src.services.streaming.audit_document_resolver.get_minio_storage",
                return_value=mock_storage,
            ),
        ):
            mock_document_class.get = AsyncMock(return_value=mock_doc)

            resolved, error = await AuditDocumentResolver.resolve(
                "Auditar archivo: report.pdf",
                ["doc-123"],
            )

            assert error is None
            assert resolved is not None
            assert resolved.document == mock_doc
            assert resolved.pdf_path == Path("/tmp/report.pdf")
            assert resolved.is_temp is True

    @pytest.mark.asyncio
    async def test_resolve_document_not_found(self):
        """Test resolution when document is not found."""
        with patch(
            "src.services.streaming.audit_document_resolver.Document"
        ) as mock_document_class:
            mock_document_class.get = AsyncMock(return_value=None)

            resolved, error = await AuditDocumentResolver.resolve(
                "Auditar archivo: report.pdf",
                ["doc-123"],
            )

            assert resolved is None
            assert error is not None
            assert error.error_code == "document_not_found"
            assert "report.pdf" in error.error_message

    @pytest.mark.asyncio
    async def test_resolve_with_empty_document_ids(self):
        """Test resolution with empty document IDs."""
        resolved, error = await AuditDocumentResolver.resolve(
            "Auditar archivo: report.pdf",
            [],
        )

        assert resolved is None
        assert error is not None
        assert error.error_code == "document_not_found"

    @pytest.mark.asyncio
    async def test_resolve_materialization_error(self):
        """Test resolution when materialization fails."""
        mock_doc = MagicMock()
        mock_doc.filename = "report.pdf"
        mock_doc.minio_key = "docs/report.pdf"
        mock_doc.minio_bucket = "documents"
        mock_doc.id = "doc-123"

        with (
            patch(
                "src.services.streaming.audit_document_resolver.Document"
            ) as mock_document_class,
            patch.object(Path, "exists", return_value=False),
            patch(
                "src.services.streaming.audit_document_resolver.get_minio_storage",
                return_value=None,
            ),
        ):
            mock_document_class.get = AsyncMock(return_value=mock_doc)

            resolved, error = await AuditDocumentResolver.resolve(
                "Auditar archivo: report.pdf",
                ["doc-123"],
            )

            assert resolved is None
            assert error is not None
            assert error.error_code == "storage_unavailable"

    @pytest.mark.asyncio
    async def test_resolve_file_exists_locally(self):
        """Test resolution when file already exists locally."""
        mock_doc = MagicMock()
        mock_doc.filename = "report.pdf"
        mock_doc.minio_key = "/local/report.pdf"
        mock_doc.id = "doc-123"

        with (
            patch(
                "src.services.streaming.audit_document_resolver.Document"
            ) as mock_document_class,
            patch.object(Path, "exists", return_value=True),
        ):
            mock_document_class.get = AsyncMock(return_value=mock_doc)

            resolved, error = await AuditDocumentResolver.resolve(
                "Auditar archivo: report.pdf",
                ["doc-123"],
            )

            assert error is None
            assert resolved is not None
            assert resolved.is_temp is False

    @pytest.mark.asyncio
    async def test_resolve_extracts_filename_correctly(self):
        """Test that filename is extracted correctly from command."""
        mock_doc = MagicMock()
        mock_doc.filename = "my report 2024.pdf"
        mock_doc.minio_key = "/local/report.pdf"

        with (
            patch(
                "src.services.streaming.audit_document_resolver.Document"
            ) as mock_document_class,
            patch.object(Path, "exists", return_value=True),
        ):
            mock_document_class.get = AsyncMock(return_value=mock_doc)

            resolved, error = await AuditDocumentResolver.resolve(
                "Auditar archivo: my report 2024.pdf",
                ["doc-123"],
            )

            assert error is None
            assert resolved is not None
