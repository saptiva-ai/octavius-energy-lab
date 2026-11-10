"""
Unit tests for extraction_delegator service.

Tests:
- DELEGATE_EXTRACTION flag
- get_extraction_delegator singleton
- ExtractionDelegator class
- extract_text_delegated convenience function
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Skip all tests if import fails due to proto version mismatch
try:
    from src.services.extraction_delegator import (
        DELEGATE_EXTRACTION,
        ExtractionDelegator,
        extract_text_delegated,
        extract_text_from_minio_delegated,
        get_extraction_delegator,
    )
    SERVICE_IMPORT_AVAILABLE = True
except Exception:
    SERVICE_IMPORT_AVAILABLE = False
    # Dummy imports
    DELEGATE_EXTRACTION = False
    ExtractionDelegator = None
    extract_text_delegated = None
    extract_text_from_minio_delegated = None
    get_extraction_delegator = None

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        not SERVICE_IMPORT_AVAILABLE,
        reason="Protobuf version mismatch - regenerate protos"
    ),
]


class TestDelegateExtractionFlag:
    """Test DELEGATE_EXTRACTION feature flag."""

    def test_flag_is_boolean(self):
        """Test DELEGATE_EXTRACTION is a boolean."""
        assert isinstance(DELEGATE_EXTRACTION, bool)


class TestGetExtractionDelegator:
    """Test get_extraction_delegator singleton."""

    def test_returns_extraction_delegator(self):
        """Test returns ExtractionDelegator instance."""
        # Reset singleton for test
        import src.services.extraction_delegator as module

        module._delegator = None

        delegator = get_extraction_delegator()
        assert isinstance(delegator, ExtractionDelegator)

    def test_returns_same_instance(self):
        """Test returns same singleton instance."""
        delegator1 = get_extraction_delegator()
        delegator2 = get_extraction_delegator()
        assert delegator1 is delegator2


class TestExtractionDelegator:
    """Test ExtractionDelegator class."""

    def test_init(self):
        """Test initialization."""
        delegator = ExtractionDelegator()
        assert delegator._client is None
        assert delegator._file_manager_available is None

    @pytest.mark.asyncio
    async def test_check_file_manager_health_caches_result(self):
        """Test health check result is cached."""
        delegator = ExtractionDelegator()

        with patch.object(delegator, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.health_check = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            # First call
            result1 = await delegator._check_file_manager_health()
            # Second call
            result2 = await delegator._check_file_manager_health()

            assert result1 is True
            assert result2 is True
            # Should only call health_check once (cached)
            mock_client.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_file_manager_health_returns_false_on_error(self):
        """Test health check returns False on error."""
        delegator = ExtractionDelegator()

        with patch.object(delegator, "_get_client") as mock_get_client:
            mock_get_client.side_effect = Exception("Connection failed")

            result = await delegator._check_file_manager_health()

            assert result is False
            assert delegator._file_manager_available is False

    @pytest.mark.asyncio
    async def test_extract_from_file_pdf(self):
        """Test extract_from_file with PDF content type."""
        delegator = ExtractionDelegator()

        # Mock the PDF extraction
        with patch.object(
            delegator, "_extract_pdf_local"
        ) as mock_extract:
            mock_extract.return_value = [
                MagicMock(page=1, text_md="Test content", has_table=False)
            ]

            pages = await delegator.extract_from_file(
                Path("/tmp/test.pdf"), "application/pdf"
            )

            assert len(pages) == 1
            mock_extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_from_file_unsupported_type(self):
        """Test extract_from_file with unsupported content type."""
        delegator = ExtractionDelegator()

        pages = await delegator.extract_from_file(
            Path("/tmp/test.xyz"), "application/xyz"
        )

        assert len(pages) == 1
        assert "Formato no soportado" in pages[0].text_md

    @pytest.mark.asyncio
    async def test_extract_from_file_image_without_file_manager(self):
        """Test extract_from_file with image when file-manager unavailable."""
        delegator = ExtractionDelegator()
        delegator._file_manager_available = False

        with patch(
            "src.services.extraction_delegator.DELEGATE_EXTRACTION", False
        ):
            pages = await delegator.extract_from_file(
                Path("/tmp/test.png"), "image/png"
            )

        assert len(pages) == 1
        assert "OCR" in pages[0].text_md

    @pytest.mark.asyncio
    async def test_extract_pdf_local_success(self):
        """Test PDF extraction with pypdf."""
        delegator = ExtractionDelegator()

        # PdfReader is imported inside the method, so patch at pypdf module level
        with patch("pypdf.PdfReader") as mock_reader_class:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Page 1 content"

            mock_reader = MagicMock()
            mock_reader.pages = [mock_page]
            mock_reader_class.return_value = mock_reader

            pages = await delegator._extract_pdf_local(Path("/tmp/test.pdf"))

            assert len(pages) == 1
            assert "Page 1 content" in pages[0].text_md

    @pytest.mark.asyncio
    async def test_extract_pdf_local_handles_empty_page(self):
        """Test PDF extraction handles pages with no text."""
        delegator = ExtractionDelegator()

        with patch("pypdf.PdfReader") as mock_reader_class:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = ""

            mock_reader = MagicMock()
            mock_reader.pages = [mock_page]
            mock_reader_class.return_value = mock_reader

            pages = await delegator._extract_pdf_local(Path("/tmp/test.pdf"))

            assert len(pages) == 1
            assert "sin texto extraible" in pages[0].text_md

    @pytest.mark.asyncio
    async def test_extract_pdf_local_handles_page_error(self):
        """Test PDF extraction handles per-page errors."""
        delegator = ExtractionDelegator()

        with patch("pypdf.PdfReader") as mock_reader_class:
            mock_page = MagicMock()
            mock_page.extract_text.side_effect = Exception("Page error")

            mock_reader = MagicMock()
            mock_reader.pages = [mock_page]
            mock_reader_class.return_value = mock_reader

            pages = await delegator._extract_pdf_local(Path("/tmp/test.pdf"))

            assert len(pages) == 1
            assert "Error en pagina" in pages[0].text_md

    @pytest.mark.asyncio
    async def test_extract_via_file_manager_success(self):
        """Test extraction via file-manager API."""
        delegator = ExtractionDelegator()

        mock_client = AsyncMock()
        mock_client.extract_text = AsyncMock(
            return_value={"text": "Extracted text", "pages": 5, "source": "ocr"}
        )
        delegator._client = mock_client

        text, pages = await delegator._extract_via_file_manager("test/path.pdf")

        assert text == "Extracted text"
        assert pages == 5

    @pytest.mark.asyncio
    async def test_extract_via_file_manager_error(self):
        """Test extraction via file-manager handles errors."""
        delegator = ExtractionDelegator()

        mock_client = AsyncMock()
        mock_client.extract_text = AsyncMock(
            side_effect=Exception("API error")
        )
        delegator._client = mock_client

        with pytest.raises(Exception, match="API error"):
            await delegator._extract_via_file_manager("test/path.pdf")


class TestExtractTextDelegated:
    """Test extract_text_delegated convenience function."""

    @pytest.mark.asyncio
    async def test_uses_singleton(self):
        """Test uses singleton delegator."""
        # Reset singleton
        import src.services.extraction_delegator as module

        module._delegator = None

        with patch.object(
            ExtractionDelegator, "extract_from_file"
        ) as mock_extract:
            mock_extract.return_value = []

            await extract_text_delegated(Path("/tmp/test.pdf"), "application/pdf")

            mock_extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_correct_args(self):
        """Test passes correct arguments to delegator."""
        import src.services.extraction_delegator as module

        mock_delegator = MagicMock()
        mock_delegator.extract_from_file = AsyncMock(return_value=[])
        module._delegator = mock_delegator

        path = Path("/tmp/test.pdf")
        content_type = "application/pdf"

        await extract_text_delegated(path, content_type)

        mock_delegator.extract_from_file.assert_called_once_with(path, content_type)


class TestExtractTextFromMinioDelegated:
    """Test extract_text_from_minio_delegated convenience function."""

    @pytest.mark.asyncio
    async def test_calls_delegator(self):
        """Test calls delegator extract_from_minio."""
        import src.services.extraction_delegator as module

        mock_delegator = MagicMock()
        mock_delegator.extract_from_minio = AsyncMock(
            return_value=("extracted text", 5)
        )
        module._delegator = mock_delegator

        text, pages = await extract_text_from_minio_delegated(
            "bucket", "key", "application/pdf", force=True
        )

        assert text == "extracted text"
        assert pages == 5
        mock_delegator.extract_from_minio.assert_called_once_with(
            "bucket", "key", "application/pdf", True
        )

    @pytest.mark.asyncio
    async def test_default_force_false(self):
        """Test default force is False."""
        import src.services.extraction_delegator as module

        mock_delegator = MagicMock()
        mock_delegator.extract_from_minio = AsyncMock(
            return_value=("text", None)
        )
        module._delegator = mock_delegator

        await extract_text_from_minio_delegated("bucket", "key", "application/pdf")

        mock_delegator.extract_from_minio.assert_called_once_with(
            "bucket", "key", "application/pdf", False
        )


class TestGetClient:
    """Test _get_client method."""

    @pytest.mark.asyncio
    async def test_lazy_initializes_client(self):
        """Test client is lazily initialized."""
        delegator = ExtractionDelegator()
        mock_client = AsyncMock()

        with patch(
            "src.services.extraction_delegator.get_file_manager_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            client = await delegator._get_client()

            assert client is mock_client
            assert delegator._client is mock_client

    @pytest.mark.asyncio
    async def test_returns_cached_client(self):
        """Test returns cached client on subsequent calls."""
        delegator = ExtractionDelegator()
        mock_client = AsyncMock()
        delegator._client = mock_client

        with patch(
            "src.services.extraction_delegator.get_file_manager_client",
        ) as mock_get:
            client = await delegator._get_client()

            assert client is mock_client
            mock_get.assert_not_called()


class TestExtractFromMinio:
    """Test extract_from_minio method."""

    @pytest.mark.asyncio
    async def test_delegates_when_flag_enabled_and_healthy(self):
        """Test delegates to file-manager when enabled and healthy."""
        delegator = ExtractionDelegator()

        with patch(
            "src.services.extraction_delegator.DELEGATE_EXTRACTION", True
        ), patch.object(
            delegator, "_check_file_manager_health", return_value=True
        ), patch.object(
            delegator, "_extract_via_file_manager", return_value=("text", 3)
        ) as mock_delegate:
            text, pages = await delegator.extract_from_minio(
                "bucket", "key.pdf", "application/pdf", force=True
            )

            assert text == "text"
            assert pages == 3
            mock_delegate.assert_called_once_with("key.pdf", True)

    @pytest.mark.asyncio
    async def test_falls_back_when_flag_disabled(self):
        """Test falls back to local when flag disabled."""
        delegator = ExtractionDelegator()

        with patch(
            "src.services.extraction_delegator.DELEGATE_EXTRACTION", False
        ), patch.object(
            delegator, "_extract_locally_from_minio", return_value=("local text", 2)
        ) as mock_local:
            text, pages = await delegator.extract_from_minio(
                "bucket", "key.pdf", "application/pdf"
            )

            assert text == "local text"
            assert pages == 2
            mock_local.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_when_unhealthy(self):
        """Test falls back to local when file-manager unhealthy."""
        delegator = ExtractionDelegator()

        with patch(
            "src.services.extraction_delegator.DELEGATE_EXTRACTION", True
        ), patch.object(
            delegator, "_check_file_manager_health", return_value=False
        ), patch.object(
            delegator, "_extract_locally_from_minio", return_value=("fallback", 1)
        ) as mock_local:
            text, pages = await delegator.extract_from_minio(
                "bucket", "key.pdf", "application/pdf"
            )

            assert text == "fallback"
            mock_local.assert_called_once()


class TestExtractLocallyFromMinio:
    """Test _extract_locally_from_minio method."""

    @pytest.mark.asyncio
    async def test_downloads_and_extracts(self):
        """Test downloads file and extracts locally."""
        delegator = ExtractionDelegator()

        mock_page = MagicMock()
        mock_page.text_md = "Page content"

        # minio_service is imported inside the method from src.services.minio_service
        with patch(
            "src.services.minio_service.minio_service"
        ) as mock_minio, patch.object(
            delegator, "extract_from_file", return_value=[mock_page]
        ) as mock_extract, patch(
            "tempfile.NamedTemporaryFile"
        ) as mock_temp:
            mock_file = MagicMock()
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_file.name = "/tmp/test.pdf"
            mock_temp.return_value = mock_file

            mock_minio.download_to_path = AsyncMock()

            # Patch unlink to avoid file system errors
            with patch("pathlib.Path.unlink"):
                text, pages = await delegator._extract_locally_from_minio(
                    "bucket", "key.pdf", "application/pdf"
                )

            assert text == "Page content"
            assert pages == 1
            mock_minio.download_to_path.assert_called_once()
            mock_extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_correct_suffix(self):
        """Test uses file suffix from minio key."""
        delegator = ExtractionDelegator()

        with patch(
            "src.services.minio_service.minio_service"
        ) as mock_minio, patch.object(
            delegator, "extract_from_file", return_value=[]
        ), patch(
            "tempfile.NamedTemporaryFile"
        ) as mock_temp:
            mock_file = MagicMock()
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_file.name = "/tmp/test.docx"
            mock_temp.return_value = mock_file

            mock_minio.download_to_path = AsyncMock()

            with patch("pathlib.Path.unlink"):
                await delegator._extract_locally_from_minio(
                    "bucket", "path/to/file.docx", "application/docx"
                )

            # Should use .docx suffix
            mock_temp.assert_called_once()
            call_kwargs = mock_temp.call_args[1]
            assert call_kwargs["suffix"] == ".docx"


class TestExtractPdfLocalEdgeCases:
    """Test edge cases for _extract_pdf_local."""

    @pytest.mark.asyncio
    async def test_handles_import_error(self):
        """Test handles pypdf ImportError."""
        delegator = ExtractionDelegator()

        with patch.dict("sys.modules", {"pypdf": None}):
            # Force import to fail
            import builtins
            original_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "pypdf":
                    raise ImportError("No module named 'pypdf'")
                return original_import(name, *args, **kwargs)

            with patch.object(builtins, "__import__", side_effect=mock_import):
                pages = await delegator._extract_pdf_local(Path("/tmp/test.pdf"))

            assert len(pages) == 1
            assert "pypdf no instalado" in pages[0].text_md

    @pytest.mark.asyncio
    async def test_handles_general_exception(self):
        """Test handles general exception during extraction."""
        delegator = ExtractionDelegator()

        with patch("pypdf.PdfReader") as mock_reader_class:
            mock_reader_class.side_effect = Exception("Corrupt PDF")

            pages = await delegator._extract_pdf_local(Path("/tmp/corrupt.pdf"))

            assert len(pages) == 1
            assert "Error de extraccion" in pages[0].text_md
            assert "Corrupt PDF" in pages[0].text_md


class TestExtractFromFileImageWithManager:
    """Test image extraction when file-manager is available."""

    @pytest.mark.asyncio
    async def test_image_with_file_manager_available(self):
        """Test returns placeholder when file-manager is available."""
        delegator = ExtractionDelegator()

        with patch(
            "src.services.extraction_delegator.DELEGATE_EXTRACTION", True
        ), patch.object(
            delegator, "_check_file_manager_health", return_value=True
        ):
            pages = await delegator.extract_from_file(
                Path("/tmp/image.png"), "image/png"
            )

            assert len(pages) == 1
            assert "OCR" in pages[0].text_md
            assert "file-manager" in pages[0].text_md

    @pytest.mark.asyncio
    async def test_multiple_pages_extraction(self):
        """Test extraction of PDF with multiple pages."""
        delegator = ExtractionDelegator()

        with patch("pypdf.PdfReader") as mock_reader_class:
            mock_page1 = MagicMock()
            mock_page1.extract_text.return_value = "Page 1"
            mock_page2 = MagicMock()
            mock_page2.extract_text.return_value = "Page 2"
            mock_page3 = MagicMock()
            mock_page3.extract_text.return_value = "Page 3"

            mock_reader = MagicMock()
            mock_reader.pages = [mock_page1, mock_page2, mock_page3]
            mock_reader_class.return_value = mock_reader

            pages = await delegator._extract_pdf_local(Path("/tmp/multi.pdf"))

            assert len(pages) == 3
            assert pages[0].page == 1
            assert pages[1].page == 2
            assert pages[2].page == 3
            assert "Page 1" in pages[0].text_md
            assert "Page 2" in pages[1].text_md
            assert "Page 3" in pages[2].text_md
