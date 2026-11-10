"""
Unit tests for text extraction abstraction layer.

Tests cover:
- Factory pattern (get_text_extractor)
- ThirdPartyExtractor (pypdf + pytesseract)
- SaptivaExtractor (stub)
- Error handling and exceptions
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Import from specific modules due to lazy loading optimization
from src.services.extractors import (
    get_text_extractor,
    clear_extractor_cache,
    health_check_extractor,
    TextExtractor,
    ExtractionError,
    UnsupportedFormatError,
)
from src.services.extractors.third_party import ThirdPartyExtractor
from src.services.extractors.saptiva import SaptivaExtractor

# HuggingFaceExtractor requires PyMuPDF - import conditionally
try:
    from src.services.extractors.huggingface import HuggingFaceExtractor
    HAS_PYMUPDF = True
except ImportError:
    HuggingFaceExtractor = None  # type: ignore
    HAS_PYMUPDF = False


class TestFactory:
    """Tests for extractor factory (get_text_extractor)."""

    def setup_method(self):
        """Reset factory cache before each test."""
        clear_extractor_cache()

    def teardown_method(self):
        """Clean up after each test."""
        clear_extractor_cache()

    def test_factory_returns_third_party_by_default(self):
        """Factory should return ThirdPartyExtractor when EXTRACTOR_PROVIDER not set."""
        with patch.dict(os.environ, {}, clear=True):
            extractor = get_text_extractor()
            assert isinstance(extractor, ThirdPartyExtractor)

    def test_factory_returns_third_party_explicitly(self):
        """Factory should return ThirdPartyExtractor when EXTRACTOR_PROVIDER=third_party."""
        with patch.dict(os.environ, {"EXTRACTOR_PROVIDER": "third_party"}):
            clear_extractor_cache()
            extractor = get_text_extractor()
            assert isinstance(extractor, ThirdPartyExtractor)

    def test_factory_returns_saptiva(self):
        """Factory should return SaptivaExtractor when EXTRACTOR_PROVIDER=saptiva."""
        with patch.dict(os.environ, {"EXTRACTOR_PROVIDER": "saptiva"}):
            clear_extractor_cache()
            extractor = get_text_extractor()
            assert isinstance(extractor, SaptivaExtractor)

    @pytest.mark.skipif(not HAS_PYMUPDF, reason="PyMuPDF (fitz) not installed")
    def test_factory_returns_huggingface(self):
        """Factory should return HuggingFaceExtractor when EXTRACTOR_PROVIDER=huggingface."""
        with patch.dict(os.environ, {"EXTRACTOR_PROVIDER": "huggingface"}):
            clear_extractor_cache()
            extractor = get_text_extractor()
            assert isinstance(extractor, HuggingFaceExtractor)

    def test_factory_caches_instance(self):
        """Factory should return same instance on subsequent calls (singleton)."""
        extractor1 = get_text_extractor()
        extractor2 = get_text_extractor()
        assert extractor1 is extractor2

    def test_factory_force_new_creates_fresh_instance(self):
        """Factory should create new instance when force_new=True."""
        extractor1 = get_text_extractor()
        extractor2 = get_text_extractor(force_new=True)
        assert extractor1 is not extractor2

    def test_factory_handles_invalid_provider(self):
        """Factory should fallback to third_party for invalid EXTRACTOR_PROVIDER."""
        with patch.dict(os.environ, {"EXTRACTOR_PROVIDER": "invalid"}):
            clear_extractor_cache()
            extractor = get_text_extractor()
            assert isinstance(extractor, ThirdPartyExtractor)

    def test_factory_handles_case_insensitive_provider(self):
        """Factory should handle case-insensitive EXTRACTOR_PROVIDER."""
        with patch.dict(os.environ, {"EXTRACTOR_PROVIDER": "SAPTIVA"}):
            clear_extractor_cache()
            extractor = get_text_extractor()
            assert isinstance(extractor, SaptivaExtractor)

    def test_clear_cache_resets_singleton(self):
        """clear_extractor_cache() should allow creating new instance."""
        extractor1 = get_text_extractor()
        clear_extractor_cache()
        extractor2 = get_text_extractor()
        assert extractor1 is not extractor2

    @pytest.mark.asyncio
    async def test_health_check_extractor_convenience(self):
        """health_check_extractor() should check current extractor."""
        with patch.object(ThirdPartyExtractor, "health_check", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = True
            clear_extractor_cache()

            result = await health_check_extractor()

            assert result is True
            mock_health.assert_called_once()


class TestThirdPartyExtractor:
    """Tests for ThirdPartyExtractor (pypdf + pytesseract)."""

    @pytest.mark.asyncio
    async def test_extract_pdf_text_success(self):
        """Should extract text from valid PDF bytes."""
        # Create minimal PDF content (simplified test)
        pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"

        extractor = ThirdPartyExtractor()

        # Mock pypdf to avoid needing real PDF
        with patch("src.services.extractors.third_party.PdfReader") as mock_reader:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Test PDF content"
            mock_reader.return_value.pages = [mock_page]

            text = await extractor.extract_text(
                media_type="pdf",
                data=pdf_bytes,
                mime="application/pdf",
                filename="test.pdf",
            )

            assert text == "Test PDF content"
            mock_reader.assert_called_once()
            mock_page.extract_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_pdf_handles_empty_pages(self):
        """Should handle PDFs with empty pages."""
        pdf_bytes = b"%PDF-1.4 test"

        extractor = ThirdPartyExtractor()

        with patch("src.services.extractors.third_party.PdfReader") as mock_reader:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = ""  # Empty page
            mock_reader.return_value.pages = [mock_page]

            text = await extractor.extract_text(
                media_type="pdf",
                data=pdf_bytes,
                mime="application/pdf",
            )

            assert "[Página 1 sin texto extraíble]" in text

    @pytest.mark.asyncio
    async def test_extract_image_text_success(self):
        """Should extract text from image using OCR."""
        # Create simple 1x1 PNG bytes
        image_bytes = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'
            b'\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )

        extractor = ThirdPartyExtractor()

        # Mock PIL and pytesseract
        with patch("src.services.extractors.third_party.Image") as mock_image, \
             patch("src.services.extractors.third_party.pytesseract") as mock_tesseract:

            mock_img = MagicMock()
            mock_img.mode = "RGB"
            mock_img.size = (100, 100)
            mock_image.open.return_value = mock_img
            mock_tesseract.image_to_string.return_value = "OCR extracted text"

            text = await extractor.extract_text(
                media_type="image",
                data=image_bytes,
                mime="image/png",
                filename="test.png",
            )

            assert text == "OCR extracted text"
            mock_image.open.assert_called_once()
            mock_tesseract.image_to_string.assert_called()

    @pytest.mark.asyncio
    async def test_extract_image_handles_empty_ocr(self):
        """Should return message when OCR finds no text."""
        image_bytes = b"fake_image_bytes"

        extractor = ThirdPartyExtractor()

        with patch("src.services.extractors.third_party.Image") as mock_image, \
             patch("src.services.extractors.third_party.pytesseract") as mock_tesseract:

            mock_img = MagicMock()
            mock_img.mode = "RGB"
            mock_img.size = (100, 100)
            mock_image.open.return_value = mock_img
            mock_tesseract.image_to_string.return_value = ""  # Empty OCR result

            text = await extractor.extract_text(
                media_type="image",
                data=image_bytes,
                mime="image/png",
            )

            assert "sin texto detectable" in text.lower()

    @pytest.mark.asyncio
    async def test_extract_rejects_wrong_mime_for_pdf(self):
        """Should raise UnsupportedFormatError for wrong MIME type."""
        extractor = ThirdPartyExtractor()

        with pytest.raises(UnsupportedFormatError) as exc_info:
            await extractor.extract_text(
                media_type="pdf",
                data=b"test",
                mime="image/png",  # Wrong MIME for PDF
            )

        assert "not supported for PDF" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_rejects_unsupported_image_mime(self):
        """Should raise UnsupportedFormatError for unsupported image MIME."""
        extractor = ThirdPartyExtractor()

        with pytest.raises(UnsupportedFormatError) as exc_info:
            await extractor.extract_text(
                media_type="image",
                data=b"test",
                mime="image/tiff",  # Unsupported
            )

        assert "not supported for image" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_available(self):
        """Should return True when pypdf and tesseract are available."""
        extractor = ThirdPartyExtractor()

        with patch("src.services.extractors.third_party.PdfReader"), \
             patch("src.services.extractors.third_party.pytesseract") as mock_tesseract:
            mock_tesseract.get_tesseract_version.return_value = "4.1.1"

            result = await extractor.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_when_missing(self):
        """Should return False when dependencies are missing."""
        extractor = ThirdPartyExtractor()

        # Patch to None to simulate missing dependency (health_check checks if PdfReader is None)
        with patch("src.services.extractors.third_party.PdfReader", None):
            result = await extractor.health_check()

            assert result is False

    @pytest.mark.asyncio
    async def test_temp_file_cleanup_on_success(self, tmp_path):
        """Should clean up temporary file after successful extraction."""
        extractor = ThirdPartyExtractor()

        with patch("src.services.extractors.third_party.PdfReader") as mock_reader:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "test"
            mock_reader.return_value.pages = [mock_page]

            await extractor.extract_text(
                media_type="pdf",
                data=b"%PDF test",
                mime="application/pdf",
            )

            # Temp file should be deleted (can't easily verify, but no exception means cleanup worked)

    @pytest.mark.asyncio
    async def test_temp_file_cleanup_on_error(self):
        """Should clean up temporary file even when extraction fails."""
        extractor = ThirdPartyExtractor()

        with patch("src.services.extractors.third_party.PdfReader", side_effect=Exception("Read error")):
            with pytest.raises(ExtractionError):
                await extractor.extract_text(
                    media_type="pdf",
                    data=b"%PDF test",
                    mime="application/pdf",
                )

            # Temp file should be deleted even on error


class TestSaptivaExtractor:
    """Tests for SaptivaExtractor (stub)."""

    def test_saptiva_extractor_initializes_with_env_vars(self):
        """Should read configuration from environment variables."""
        with patch.dict(os.environ, {
            "SAPTIVA_BASE_URL": "https://test.saptiva.ai",
            "SAPTIVA_API_KEY": "test-key-123",
        }):
            extractor = SaptivaExtractor()

            assert extractor.base_url == "https://test.saptiva.ai"
            assert extractor.api_key == "test-key-123"

    def test_saptiva_extractor_strips_trailing_slash(self):
        """Should strip trailing slash from base URL."""
        extractor = SaptivaExtractor(base_url="https://test.saptiva.ai/")
        assert extractor.base_url == "https://test.saptiva.ai"

    @pytest.mark.asyncio
    async def test_saptiva_extract_image_success(self):
        """Should extract text from image using OCR endpoint."""
        import httpx
        from unittest.mock import AsyncMock

        extractor = SaptivaExtractor(
            base_url="https://test.saptiva.ai",
            api_key="test-key-123",
        )

        # Mock httpx client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "Saptiva OCR",
            "choices": [
                {
                    "message": {"content": "OCR extracted text"},
                    "finish_reason": "stop",
                }
            ],
        }
        mock_response.raise_for_status = MagicMock()

        class _DummyCache:
            async def get(self, *_args, **_kwargs):
                return None

            async def set(self, *_args, **_kwargs):
                return True

        with patch(
            "src.services.extractors.saptiva.get_extraction_cache",
            return_value=_DummyCache(),
        ), patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            text = await extractor.extract_text(
                media_type="image",
                data=b"fake_image_bytes",
                mime="image/png",
                filename="test.png",
            )

            assert text == "OCR extracted text"

            # Verify OCR endpoint was called
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            assert call_args[0][0] == "https://test.saptiva.ai/v1/chat/completions"

            # Verify request payload structure
            payload = call_args[1]["json"]
            assert payload["model"] == "Saptiva OCR"
            content = payload["messages"][0]["content"]
            assert content[0]["type"] == "text"
            assert content[1]["type"] == "image_url"
            assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")

    @pytest.mark.asyncio
    async def test_saptiva_health_check_returns_true_when_configured(self):
        """Should return True when API is properly configured."""
        extractor = SaptivaExtractor(
            base_url="https://test.saptiva.ai",
            api_key="test-key"
        )

        result = await extractor.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_saptiva_circuit_breaker_opens_after_failures(self):
        """Should open circuit breaker after repeated failures."""
        import httpx
        from unittest.mock import AsyncMock

        extractor = SaptivaExtractor(
            base_url="https://test.saptiva.ai",
            api_key="test-key-123",
        )

        # Mock httpx to always fail
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.HTTPStatusError("Server error", request=MagicMock(), response=MagicMock(status_code=500, text="Internal error"))
            )

            # Fail 5 times to open circuit
            for _ in range(5):
                with pytest.raises(ExtractionError):
                    await extractor.extract_text(
                        media_type="pdf",
                        data=b"%PDF-1.4 test",
                        mime="application/pdf",
                    )

            # Circuit should now be OPEN
            assert extractor.circuit_breaker.state.value == "open"

            # Next request should fail immediately without hitting API
            with pytest.raises(ExtractionError) as exc_info:
                await extractor.extract_text(
                    media_type="pdf",
                    data=b"%PDF-1.4 test",
                    mime="application/pdf",
                )

            assert "circuit breaker" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_saptiva_validates_file_size(self):
        """Should reject files exceeding size limits."""
        extractor = SaptivaExtractor(
            base_url="https://test.saptiva.ai",
            api_key="test-key-123",
        )

        # Create 51MB PDF (exceeds 50MB limit)
        large_pdf = b"%PDF-1.4\n" + b"x" * (51 * 1024 * 1024)

        with pytest.raises(ExtractionError) as exc_info:
            await extractor.extract_text(
                media_type="pdf",
                data=large_pdf,
                mime="application/pdf",
            )

        assert "exceeds" in str(exc_info.value).lower()
        assert "50" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_saptiva_validates_mime_type(self):
        """Should reject unsupported MIME types."""
        extractor = SaptivaExtractor(
            base_url="https://test.saptiva.ai",
            api_key="test-key-123",
        )

        with pytest.raises(UnsupportedFormatError) as exc_info:
            await extractor.extract_text(
                media_type="pdf",
                data=b"test",
                mime="application/msword",  # Unsupported
            )

        assert "not supported" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_saptiva_retries_on_server_error(self):
        """Should retry on 5xx errors with exponential backoff."""
        import httpx
        from unittest.mock import AsyncMock

        extractor = SaptivaExtractor(
            base_url="https://test.saptiva.ai",
            api_key="test-key-123",
        )

        class _DummyCache:
            async def get(self, *_args, **_kwargs):
                return None

            async def set(self, *_args, **_kwargs):
                return True

        call_count = 0

        async def mock_post(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1

            if call_count <= 2:
                mock_resp = MagicMock()
                mock_resp.status_code = 503
                mock_resp.text = "Service Unavailable"
                raise httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_resp)

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "model": "Saptiva OCR",
                "choices": [{"message": {"content": "Success after retries"}, "finish_reason": "stop"}],
            }
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        with patch(
            "src.services.extractors.saptiva.get_extraction_cache",
            return_value=_DummyCache(),
        ), patch("httpx.AsyncClient") as mock_client, patch.object(
            SaptivaExtractor, "_calculate_retry_delay", return_value=0
        ):
            mock_client.return_value.__aenter__.return_value.post = mock_post

            text = await extractor.extract_text(
                media_type="image",
                data=b"fake_image",
                mime="image/png",
            )

            assert text == "Success after retries"
            assert call_count == 3

    @pytest.mark.asyncio
    async def test_saptiva_no_retry_on_client_error(self):
        """Should not retry on 4xx client errors (except 429)."""
        import httpx
        from unittest.mock import AsyncMock

        extractor = SaptivaExtractor(
            base_url="https://test.saptiva.ai",
            api_key="test-key-123",
        )

        class _DummyCache:
            async def get(self, *_args, **_kwargs):
                return None

            async def set(self, *_args, **_kwargs):
                return True

        call_count = 0

        async def mock_post(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1

            mock_resp = MagicMock()
            mock_resp.status_code = 400
            mock_resp.text = "Bad Request"
            raise httpx.HTTPStatusError("Client error", request=MagicMock(), response=mock_resp)

        with patch(
            "src.services.extractors.saptiva.get_extraction_cache",
            return_value=_DummyCache(),
        ), patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = mock_post

            with pytest.raises(ExtractionError) as exc_info:
                await extractor.extract_text(
                    media_type="image",
                    data=b"fake_image",
                    mime="image/png",
                )

            assert "400" in str(exc_info.value)
            assert call_count == 1

    @pytest.mark.asyncio
    async def test_saptiva_generates_idempotency_key(self):
        """Should generate consistent idempotency keys from content hash."""
        import httpx
        from unittest.mock import AsyncMock

        extractor = SaptivaExtractor(
            base_url="https://test.saptiva.ai",
            api_key="test-key-123",
        )

        pdf_data = b"%PDF-1.4 test content"

        key1 = extractor._generate_idempotency_key(pdf_data, "pdf")
        key2 = extractor._generate_idempotency_key(pdf_data, "pdf")

        assert key1 == key2
        assert key1.startswith("saptiva-extract-pdf-")


class TestAbstractInterface:
    """Tests for TextExtractor ABC compliance."""

    def test_cannot_instantiate_abstract_class(self):
        """Should not allow direct instantiation of TextExtractor."""
        with pytest.raises(TypeError):
            TextExtractor()

    def test_third_party_implements_interface(self):
        """ThirdPartyExtractor should implement TextExtractor interface."""
        extractor = ThirdPartyExtractor()
        assert isinstance(extractor, TextExtractor)

    def test_saptiva_implements_interface(self):
        """SaptivaExtractor should implement TextExtractor interface."""
        extractor = SaptivaExtractor()
        assert isinstance(extractor, TextExtractor)


class TestExceptions:
    """Tests for custom exception classes."""

    def test_extraction_error_stores_media_type(self):
        """ExtractionError should store media_type attribute."""
        error = ExtractionError("test error", media_type="pdf")
        assert error.media_type == "pdf"

    def test_extraction_error_stores_original_error(self):
        """ExtractionError should store original exception."""
        original = ValueError("original error")
        error = ExtractionError("wrapper", original_error=original)
        assert error.original_error is original

    def test_unsupported_format_error_is_extraction_error(self):
        """UnsupportedFormatError should inherit from ExtractionError."""
        error = UnsupportedFormatError("test", media_type="image")
        assert isinstance(error, ExtractionError)
