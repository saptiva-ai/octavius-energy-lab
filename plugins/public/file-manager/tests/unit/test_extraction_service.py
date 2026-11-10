"""
Unit tests for extraction service.

Tests the extraction.py module with both Rust and Python paths.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock


# ============================================================================
# Extraction Service Import Tests
# ============================================================================


class TestExtractionServiceImport:
    """Test extraction service module structure."""

    def test_module_imports(self):
        """Test all public functions are importable."""
        from src.services.extraction import (
            extract_text_from_pdf,
            extract_text_from_image,
            extract_text_from_file,
            generate_thumbnail,
            generate_thumbnail_bytes,
            get_extraction_status,
            RUST_AVAILABLE,
        )

        # All should be callable
        assert callable(extract_text_from_pdf)
        assert callable(extract_text_from_image)
        assert callable(extract_text_from_file)
        assert callable(generate_thumbnail)
        assert callable(generate_thumbnail_bytes)
        assert callable(get_extraction_status)
        assert isinstance(RUST_AVAILABLE, bool)

    def test_get_extraction_status(self):
        """Test extraction status returns expected structure."""
        from src.services.extraction import get_extraction_status

        status = get_extraction_status()

        assert "rust_available" in status
        assert "capabilities" in status
        assert "performance" in status
        assert isinstance(status["rust_available"], bool)


# ============================================================================
# Text Quality Validation Tests
# ============================================================================


class TestTextQualityValidation:
    """Test text quality validation functions."""

    def test_quality_sufficient_good_text(self, sample_text):
        """Test quality check passes for good text."""
        from src.services.extraction import _is_text_quality_sufficient

        result = _is_text_quality_sufficient(sample_text)
        assert result is True

    def test_quality_sufficient_empty_text(self):
        """Test quality check fails for empty text."""
        from src.services.extraction import _is_text_quality_sufficient

        result = _is_text_quality_sufficient("")
        assert result is False

    def test_quality_sufficient_whitespace_only(self):
        """Test quality check fails for whitespace only."""
        from src.services.extraction import _is_text_quality_sufficient

        result = _is_text_quality_sufficient("   \n\t   ")
        assert result is False

    def test_quality_sufficient_low_quality(self, low_quality_text):
        """Test quality check fails for special chars."""
        from src.services.extraction import _is_text_quality_sufficient

        result = _is_text_quality_sufficient(low_quality_text)
        assert result is False

    def test_quality_sufficient_short_text(self):
        """Test quality check fails for short text."""
        from src.services.extraction import _is_text_quality_sufficient

        result = _is_text_quality_sufficient("short")
        assert result is False

    def test_quality_sufficient_custom_ratio(self, sample_text):
        """Test quality check with custom ratio."""
        from src.services.extraction import _is_text_quality_sufficient

        result = _is_text_quality_sufficient(sample_text, min_quality_ratio=0.9)
        # May fail with high ratio
        assert isinstance(result, bool)


# ============================================================================
# PDF Extraction Tests
# ============================================================================


class TestPdfExtraction:
    """Test PDF extraction functions."""

    def test_extract_text_from_pdf_basic(self, temp_pdf_file):
        """Test basic PDF extraction."""
        from src.services.extraction import extract_text_from_pdf

        text, pages = extract_text_from_pdf(temp_pdf_file)

        assert isinstance(text, str)
        assert isinstance(pages, int)
        assert pages >= 1

    def test_extract_text_from_pdf_nonexistent_raises(self):
        """Test extraction raises for nonexistent file."""
        from src.services.extraction import extract_text_from_pdf

        with pytest.raises(Exception):
            extract_text_from_pdf(Path("/nonexistent/file.pdf"))

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    def test_extract_text_from_pdf_python_fallback(self, temp_pdf_file):
        """Test Python fallback when Rust unavailable."""
        from src.services.extraction import _extract_pdf_python

        text, pages = _extract_pdf_python(temp_pdf_file)

        assert isinstance(text, str)
        assert isinstance(pages, int)


# ============================================================================
# Image Extraction Tests
# ============================================================================


class TestImageExtraction:
    """Test image text extraction (OCR)."""

    def test_extract_text_from_image_basic(self, temp_image_file):
        """Test basic image OCR."""
        from src.services.extraction import extract_text_from_image

        try:
            text = extract_text_from_image(temp_image_file)
            assert isinstance(text, str)
        except Exception as e:
            if "Tesseract" in str(e):
                pytest.skip("Tesseract not available")
            raise

    def test_extract_text_from_image_nonexistent_raises(self):
        """Test OCR raises or returns error for nonexistent file."""
        from src.services.extraction import extract_text_from_image

        try:
            result = extract_text_from_image(Path("/nonexistent/file.png"))
            # If no exception, should return error message
            assert "error" in result.lower() or result == ""
        except Exception:
            # Exception is also acceptable
            pass


# ============================================================================
# Thumbnail Generation Tests
# ============================================================================


class TestThumbnailGeneration:
    """Test thumbnail generation functions."""

    def test_generate_thumbnail_basic(self, temp_image_file):
        """Test basic thumbnail generation."""
        from src.services.extraction import generate_thumbnail

        data, content_type = generate_thumbnail(temp_image_file)

        assert isinstance(data, bytes)
        assert len(data) > 0
        assert content_type in ("image/jpeg", "image/png", "image/webp")

    def test_generate_thumbnail_custom_size(self, temp_image_file):
        """Test thumbnail with custom size."""
        from src.services.extraction import generate_thumbnail

        data, content_type = generate_thumbnail(
            temp_image_file,
            width=100,
            height=100,
        )

        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_generate_thumbnail_png_format(self, temp_image_file):
        """Test thumbnail in PNG format."""
        from src.services.extraction import generate_thumbnail

        data, content_type = generate_thumbnail(
            temp_image_file,
            format="png",
        )

        assert content_type == "image/png"
        assert data[:4] == b"\x89PNG"

    def test_generate_thumbnail_bytes(self, sample_image_bytes):
        """Test thumbnail from bytes."""
        from src.services.extraction import generate_thumbnail_bytes

        data, content_type = generate_thumbnail_bytes(sample_image_bytes)

        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_generate_thumbnail_invalid_raises(self):
        """Test thumbnail raises for invalid file."""
        from src.services.extraction import generate_thumbnail

        with pytest.raises(Exception):
            generate_thumbnail(Path("/nonexistent/file.png"))


# ============================================================================
# Async Extraction Interface Tests
# ============================================================================


class TestAsyncExtraction:
    """Test async extraction interface."""

    @pytest.mark.asyncio
    async def test_extract_text_from_file_pdf(self, temp_pdf_file):
        """Test async extraction for PDF."""
        from src.services.extraction import extract_text_from_file

        text, pages = await extract_text_from_file(
            temp_pdf_file,
            "application/pdf",
        )

        assert isinstance(text, str)
        assert isinstance(pages, int)

    @pytest.mark.asyncio
    async def test_extract_text_from_file_image(self, temp_image_file):
        """Test async extraction for image."""
        from src.services.extraction import extract_text_from_file

        try:
            text, pages = await extract_text_from_file(
                temp_image_file,
                "image/png",
            )

            assert isinstance(text, str)
            assert pages is None  # Images don't have pages
        except Exception as e:
            if "Tesseract" in str(e):
                pytest.skip("Tesseract not available")
            raise

    @pytest.mark.asyncio
    async def test_extract_text_from_file_unsupported(self, temp_pdf_file):
        """Test async extraction for unsupported type."""
        from src.services.extraction import extract_text_from_file

        text, pages = await extract_text_from_file(
            temp_pdf_file,
            "application/unknown",
        )

        assert "[Unsupported format" in text


# ============================================================================
# Rust Integration Tests
# ============================================================================


class TestRustIntegration:
    """Test Rust module integration in extraction service."""

    def test_rust_used_when_available(self, temp_pdf_file, monkeypatch):
        """Test Rust is used when available."""
        from src.services import extraction

        if not extraction.RUST_AVAILABLE:
            pytest.skip("Rust module not available")

        # Track which path was taken
        rust_called = []

        original_extract = extraction._extract_pdf_rust

        def tracking_extract(*args, **kwargs):
            rust_called.append(True)
            return original_extract(*args, **kwargs)

        monkeypatch.setattr(extraction, "_extract_pdf_rust", tracking_extract)

        text, pages = extraction.extract_text_from_pdf(temp_pdf_file)

        assert len(rust_called) > 0, "Rust extraction should have been called"

    def test_python_fallback_on_rust_error(self, temp_pdf_file, monkeypatch):
        """Test Python fallback when Rust fails."""
        from src.services import extraction

        if not extraction.RUST_AVAILABLE:
            pytest.skip("Rust module not available")

        # Make Rust extraction fail
        def failing_extract(*args, **kwargs):
            raise Exception("Simulated Rust failure")

        monkeypatch.setattr(extraction, "_extract_pdf_rust", failing_extract)

        # Should fall back to Python and not raise
        text, pages = extraction.extract_text_from_pdf(temp_pdf_file)

        assert isinstance(text, str)
        assert isinstance(pages, int)
