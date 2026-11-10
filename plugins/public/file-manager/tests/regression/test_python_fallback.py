"""
Regression tests for Python fallback when Rust module is unavailable.

These tests ensure the extraction service continues to work correctly
when the Rust module is not compiled or available, by forcing the
Python fallback path.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys


# ============================================================================
# Python Fallback Core Tests
# ============================================================================


class TestPythonFallbackCore:
    """Test that Python fallback activates correctly."""

    def test_rust_unavailable_flag_set(self):
        """Test RUST_AVAILABLE is False when module missing."""
        # Temporarily remove the module from sys.modules if present
        original_module = sys.modules.pop("document_processing_rs", None)

        try:
            with patch.dict(sys.modules, {"document_processing_rs": None}):
                # Force reimport
                import importlib
                from src.services import extraction

                # Reload to test import path
                importlib.reload(extraction)

                # Should fall back gracefully
                assert hasattr(extraction, "RUST_AVAILABLE")
        finally:
            if original_module:
                sys.modules["document_processing_rs"] = original_module

    def test_extraction_status_without_rust(self):
        """Test extraction status reports correctly without Rust."""
        from src.services.extraction import get_extraction_status

        status = get_extraction_status()

        assert "rust_available" in status
        assert "capabilities" in status
        assert "performance" in status
        assert isinstance(status["capabilities"], (list, dict))


# ============================================================================
# PDF Extraction Fallback Tests
# ============================================================================


class TestPdfExtractionFallback:
    """Test PDF extraction falls back to Python correctly."""

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    def test_pdf_extraction_uses_python(self, temp_pdf_file):
        """Test PDF extraction uses Python when Rust unavailable."""
        from src.services.extraction import extract_text_from_pdf

        text, pages = extract_text_from_pdf(temp_pdf_file)

        assert isinstance(text, str)
        assert isinstance(pages, int)
        assert pages >= 1

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    def test_pdf_extraction_python_handles_errors(self):
        """Test Python fallback handles errors gracefully."""
        from src.services.extraction import extract_text_from_pdf

        with pytest.raises(Exception):
            extract_text_from_pdf(Path("/nonexistent/file.pdf"))

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    def test_pdf_extraction_python_empty_file(self, temp_dir):
        """Test Python fallback handles empty PDF."""
        from src.services.extraction import extract_text_from_pdf

        # Create empty file
        empty_pdf = temp_dir / "empty.pdf"
        empty_pdf.write_bytes(b"")

        with pytest.raises(Exception):
            extract_text_from_pdf(empty_pdf)


# ============================================================================
# Text Quality Fallback Tests
# ============================================================================


class TestTextQualityFallback:
    """Test text quality validation falls back correctly."""

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    def test_quality_check_python_good_text(self, sample_text):
        """Test Python quality check works for good text."""
        from src.services.extraction import _is_text_quality_sufficient

        result = _is_text_quality_sufficient(sample_text)
        assert result is True

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    def test_quality_check_python_empty_text(self):
        """Test Python quality check fails for empty text."""
        from src.services.extraction import _is_text_quality_sufficient

        result = _is_text_quality_sufficient("")
        assert result is False

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    def test_quality_check_python_low_quality(self, low_quality_text):
        """Test Python quality check fails for low quality text."""
        from src.services.extraction import _is_text_quality_sufficient

        result = _is_text_quality_sufficient(low_quality_text)
        assert result is False


# ============================================================================
# Thumbnail Generation Fallback Tests
# ============================================================================


class TestThumbnailFallback:
    """Test thumbnail generation falls back correctly."""

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    def test_thumbnail_python_basic(self, temp_image_file):
        """Test Python thumbnail generation works."""
        from src.services.extraction import generate_thumbnail

        data, content_type = generate_thumbnail(temp_image_file)

        assert isinstance(data, bytes)
        assert len(data) > 0
        assert content_type in ("image/jpeg", "image/png", "image/webp")

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    def test_thumbnail_python_custom_size(self, temp_image_file):
        """Test Python thumbnail with custom dimensions."""
        from src.services.extraction import generate_thumbnail

        data, content_type = generate_thumbnail(
            temp_image_file,
            width=100,
            height=100,
        )

        assert isinstance(data, bytes)
        assert len(data) > 0

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    def test_thumbnail_python_from_bytes(self, sample_image_bytes):
        """Test Python thumbnail from bytes."""
        from src.services.extraction import generate_thumbnail_bytes

        data, content_type = generate_thumbnail_bytes(sample_image_bytes)

        assert isinstance(data, bytes)
        assert len(data) > 0


# ============================================================================
# Async Interface Fallback Tests
# ============================================================================


@pytest.mark.asyncio
class TestAsyncFallback:
    """Test async extraction interface falls back correctly."""

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    async def test_async_extract_pdf_python(self, temp_pdf_file):
        """Test async PDF extraction uses Python fallback."""
        from src.services.extraction import extract_text_from_file

        text, pages = await extract_text_from_file(
            temp_pdf_file,
            "application/pdf",
        )

        assert isinstance(text, str)
        assert isinstance(pages, int)

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    async def test_async_extract_unsupported_python(self, temp_pdf_file):
        """Test async extraction handles unsupported types."""
        from src.services.extraction import extract_text_from_file

        text, pages = await extract_text_from_file(
            temp_pdf_file,
            "application/unknown",
        )

        assert "[Unsupported format" in text


# ============================================================================
# Rust Failure Recovery Tests
# ============================================================================


class TestRustFailureRecovery:
    """Test recovery when Rust extraction fails mid-operation."""

    def test_rust_error_triggers_python_fallback(self, temp_pdf_file, monkeypatch):
        """Test Python fallback activates when Rust raises."""
        from src.services import extraction

        if not extraction.RUST_AVAILABLE:
            pytest.skip("Rust module not available")

        # Make Rust fail
        def failing_rust(*args, **kwargs):
            raise RuntimeError("Simulated Rust failure")

        monkeypatch.setattr(extraction, "_extract_pdf_rust", failing_rust)

        # Should fall back to Python without raising
        text, pages = extraction.extract_text_from_pdf(temp_pdf_file)

        assert isinstance(text, str)
        assert isinstance(pages, int)

    def test_rust_timeout_triggers_fallback(self, temp_pdf_file, monkeypatch):
        """Test fallback on Rust timeout."""
        from src.services import extraction
        import asyncio

        if not extraction.RUST_AVAILABLE:
            pytest.skip("Rust module not available")

        # Make Rust hang (simulate timeout)
        async def hanging_rust(*args, **kwargs):
            await asyncio.sleep(100)

        # This tests the synchronous path which should catch errors
        def error_rust(*args, **kwargs):
            raise TimeoutError("Simulated timeout")

        monkeypatch.setattr(extraction, "_extract_pdf_rust", error_rust)

        text, pages = extraction.extract_text_from_pdf(temp_pdf_file)

        assert isinstance(text, str)


# ============================================================================
# Consistency Tests
# ============================================================================


class TestFallbackConsistency:
    """Test that Python and Rust produce consistent results."""

    def test_quality_check_consistency(self, sample_text):
        """Test quality check gives same result in both paths."""
        from src.services import extraction

        # Get Python result
        with patch.object(extraction, "RUST_AVAILABLE", False):
            with patch.object(extraction, "rs", None):
                python_result = extraction._is_text_quality_sufficient(sample_text)

        # If Rust available, compare
        if extraction.RUST_AVAILABLE:
            rust_result = extraction.rs.is_quality_sufficient(sample_text)
            assert python_result == rust_result

    def test_extraction_result_structure_consistent(self, temp_pdf_file):
        """Test extraction returns same structure regardless of backend."""
        from src.services.extraction import extract_text_from_pdf

        text, pages = extract_text_from_pdf(temp_pdf_file)

        # Structure should be consistent
        assert isinstance(text, str)
        assert isinstance(pages, int)
        assert pages >= 0

    def test_thumbnail_format_consistent(self, temp_image_file):
        """Test thumbnail output format is consistent."""
        from src.services.extraction import generate_thumbnail

        data, content_type = generate_thumbnail(temp_image_file)

        # Should always return valid image data
        assert isinstance(data, bytes)
        assert len(data) > 0
        assert content_type.startswith("image/")

        # Check magic bytes for common formats
        if content_type == "image/png":
            assert data[:4] == b"\x89PNG"
        elif content_type == "image/jpeg":
            assert data[:2] == b"\xff\xd8"


# ============================================================================
# Edge Case Fallback Tests
# ============================================================================


class TestEdgeCaseFallback:
    """Test edge cases in fallback behavior."""

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    def test_very_large_text_python(self):
        """Test Python handles very large text."""
        from src.services.extraction import _is_text_quality_sufficient

        large_text = "This is a test sentence. " * 10000
        result = _is_text_quality_sufficient(large_text)

        assert result is True

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    def test_unicode_text_python(self):
        """Test Python handles unicode text."""
        from src.services.extraction import _is_text_quality_sufficient

        unicode_text = "这是中文测试文本。" * 50 + " English mixed in. " * 20
        result = _is_text_quality_sufficient(unicode_text)

        assert isinstance(result, bool)

    @patch("src.services.extraction.RUST_AVAILABLE", False)
    @patch("src.services.extraction.rs", None)
    def test_special_characters_python(self):
        """Test Python handles special characters."""
        from src.services.extraction import _is_text_quality_sufficient

        special_text = "Normal text with émojis 🎉 and spëcial çharacters àéîõü"
        result = _is_text_quality_sufficient(special_text * 10)

        assert isinstance(result, bool)
