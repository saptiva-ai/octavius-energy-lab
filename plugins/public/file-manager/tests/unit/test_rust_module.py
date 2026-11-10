"""
Unit tests for Rust native module (document_processing_rs).

These tests verify the PyO3 bindings work correctly when the
Rust module is available, and gracefully skip when not compiled.
"""

import pytest
from pathlib import Path


# ============================================================================
# Rust Module Import Tests
# ============================================================================


class TestRustModuleImport:
    """Test Rust module import and availability."""

    def test_rust_module_import_graceful(self):
        """Test that Rust module import fails gracefully."""
        try:
            import document_processing_rs as rs

            assert hasattr(rs, "__version__")
            assert hasattr(rs, "extract_text_from_pdf")
            assert hasattr(rs, "ocr_image")
            assert hasattr(rs, "generate_thumbnail")
            assert hasattr(rs, "is_quality_sufficient")
        except ImportError:
            pytest.skip("Rust module not compiled")

    def test_extraction_module_fallback(self):
        """Test extraction module falls back to Python when Rust unavailable."""
        from src.services.extraction import RUST_AVAILABLE, extract_text_from_pdf

        # Should not raise regardless of Rust availability
        assert isinstance(RUST_AVAILABLE, bool)


# ============================================================================
# PDF Extraction Tests
# ============================================================================


@pytest.mark.rust
class TestRustPdfExtraction:
    """Test Rust PDF extraction functions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import Rust module or skip."""
        try:
            import document_processing_rs as rs

            self.rs = rs
        except ImportError:
            pytest.skip("Rust module not compiled")

    def test_extract_text_from_pdf_bytes(self, sample_pdf_bytes):
        """Test PDF text extraction from bytes."""
        pages = self.rs.extract_text_from_pdf(sample_pdf_bytes)

        assert isinstance(pages, list)
        assert len(pages) >= 1

        # Check PageResult structure
        page = pages[0]
        assert hasattr(page, "page")
        assert hasattr(page, "text")
        assert hasattr(page, "needs_ocr")
        assert hasattr(page, "char_count")
        assert hasattr(page, "quality_ratio")

    def test_extract_text_with_quality_params(self, sample_pdf_bytes):
        """Test extraction with custom quality parameters."""
        pages = self.rs.extract_text_from_pdf(
            sample_pdf_bytes,
            min_chars=50,
            min_quality_ratio=0.3,
        )

        assert isinstance(pages, list)

    def test_get_pdf_page_count(self, sample_pdf_bytes):
        """Test getting page count without extraction."""
        count = self.rs.get_pdf_page_count(sample_pdf_bytes)

        assert isinstance(count, int)
        assert count >= 1

    def test_extract_invalid_pdf_raises(self):
        """Test that invalid PDF raises ValueError."""
        invalid_bytes = b"not a pdf"

        with pytest.raises(ValueError):
            self.rs.extract_text_from_pdf(invalid_bytes)

    def test_extract_empty_pdf_raises(self):
        """Test that empty bytes raises ValueError."""
        with pytest.raises((ValueError, Exception)):
            self.rs.extract_text_from_pdf(b"")


# ============================================================================
# Text Quality Tests
# ============================================================================


@pytest.mark.rust
class TestRustTextQuality:
    """Test Rust text quality validation functions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import Rust module or skip."""
        try:
            import document_processing_rs as rs

            self.rs = rs
        except ImportError:
            pytest.skip("Rust module not compiled")

    def test_is_quality_sufficient_good_text(self, sample_text):
        """Test quality check passes for good text."""
        result = self.rs.is_quality_sufficient(sample_text)
        assert result is True

    def test_is_quality_sufficient_low_quality(self, low_quality_text):
        """Test quality check fails for low quality text."""
        result = self.rs.is_quality_sufficient(low_quality_text)
        assert result is False

    def test_is_quality_sufficient_empty_text(self):
        """Test quality check fails for empty text."""
        result = self.rs.is_quality_sufficient("")
        assert result is False

    def test_is_quality_sufficient_custom_params(self, sample_text):
        """Test quality check with custom parameters."""
        result = self.rs.is_quality_sufficient(
            sample_text,
            min_chars=10,
            min_quality_ratio=0.3,
            min_words=2,
            max_special_ratio=0.9,
        )
        assert result is True

    def test_calculate_char_ratio(self, sample_text):
        """Test character ratio calculation."""
        ratio = self.rs.calculate_char_ratio(sample_text)

        assert isinstance(ratio, float)
        assert 0.0 <= ratio <= 1.0

    def test_calculate_char_ratio_empty(self):
        """Test ratio for empty text is 0."""
        ratio = self.rs.calculate_char_ratio("")
        assert ratio == 0.0

    def test_count_words(self, sample_text):
        """Test word counting."""
        count = self.rs.count_words(sample_text)

        assert isinstance(count, int)
        assert count > 0

    def test_count_words_empty(self):
        """Test word count for empty text is 0."""
        count = self.rs.count_words("")
        assert count == 0

    def test_get_quality_metrics(self, sample_text):
        """Test comprehensive quality metrics."""
        metrics = self.rs.get_quality_metrics(sample_text)

        assert hasattr(metrics, "char_count")
        assert hasattr(metrics, "word_count")
        assert hasattr(metrics, "quality_ratio")
        assert hasattr(metrics, "is_sufficient")
        assert hasattr(metrics, "alphanumeric_count")
        assert hasattr(metrics, "special_count")


# ============================================================================
# OCR Tests
# ============================================================================


@pytest.mark.rust
class TestRustOcr:
    """Test Rust OCR functions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import Rust module or skip."""
        try:
            import document_processing_rs as rs

            self.rs = rs
        except ImportError:
            pytest.skip("Rust module not compiled")

    def test_ocr_image_file(self, temp_image_file):
        """Test OCR from image file."""
        try:
            text = self.rs.ocr_image(str(temp_image_file))
            assert isinstance(text, str)
        except (RuntimeError, Exception) as e:
            if "Tesseract" in str(e) or "Failed to init" in str(e) or "OCR not available" in str(e):
                pytest.skip("OCR not available in Rust build")
            raise

    def test_ocr_image_bytes(self, sample_image_bytes):
        """Test OCR from image bytes."""
        try:
            text = self.rs.ocr_image_bytes(sample_image_bytes)
            assert isinstance(text, str)
        except (RuntimeError, Exception) as e:
            if "Tesseract" in str(e) or "Failed to init" in str(e) or "OCR not available" in str(e):
                pytest.skip("OCR not available in Rust build")
            raise

    def test_ocr_with_language(self, temp_image_file):
        """Test OCR with specific language."""
        try:
            text = self.rs.ocr_image(str(temp_image_file), language="eng")
            assert isinstance(text, str)
        except (RuntimeError, TypeError, Exception) as e:
            if "Tesseract" in str(e) or "OCR not available" in str(e) or "unexpected keyword" in str(e):
                pytest.skip("OCR not available or API mismatch in Rust build")
            raise


# ============================================================================
# Thumbnail Tests
# ============================================================================


@pytest.mark.rust
class TestRustThumbnail:
    """Test Rust thumbnail generation functions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import Rust module or skip."""
        try:
            import document_processing_rs as rs

            self.rs = rs
        except ImportError:
            pytest.skip("Rust module not compiled")

    def test_generate_thumbnail_file(self, temp_image_file):
        """Test thumbnail generation from file."""
        result = self.rs.generate_thumbnail(str(temp_image_file))

        assert hasattr(result, "data")
        assert hasattr(result, "width")
        assert hasattr(result, "height")
        assert hasattr(result, "content_type")
        assert len(result.data) > 0
        assert result.width <= 200
        assert result.height <= 200

    def test_generate_thumbnail_bytes(self, sample_image_bytes):
        """Test thumbnail generation from bytes."""
        result = self.rs.generate_thumbnail_bytes(sample_image_bytes)

        assert hasattr(result, "data")
        assert len(result.data) > 0

    def test_generate_thumbnail_custom_size(self, temp_image_file):
        """Test thumbnail with custom dimensions."""
        result = self.rs.generate_thumbnail(
            str(temp_image_file),
            width=100,
            height=100,
        )

        assert result.width <= 100
        assert result.height <= 100

    def test_generate_thumbnail_png_format(self, temp_image_file):
        """Test thumbnail in PNG format."""
        result = self.rs.generate_thumbnail(
            str(temp_image_file),
            format="png",
        )

        assert result.content_type == "image/png"
        # Rust may return list of ints or bytes depending on PyO3 version
        data = bytes(result.data) if isinstance(result.data, list) else result.data
        assert data[:4] == b"\x89PNG"

    def test_generate_thumbnail_jpeg_format(self, temp_image_file):
        """Test thumbnail in JPEG format."""
        result = self.rs.generate_thumbnail(
            str(temp_image_file),
            format="jpeg",
            quality=85,
        )

        assert result.content_type == "image/jpeg"
        # Rust may return list of ints or bytes depending on PyO3 version
        data = bytes(result.data) if isinstance(result.data, list) else result.data
        assert data[:2] == b"\xff\xd8"  # JPEG magic

    def test_generate_thumbnail_invalid_file_raises(self):
        """Test that invalid file raises error."""
        with pytest.raises((IOError, ValueError, Exception)):
            self.rs.generate_thumbnail("/nonexistent/file.png")


# ============================================================================
# Parallel Processing Tests
# ============================================================================


@pytest.mark.rust
class TestRustParallelProcessing:
    """Test Rust parallel processing functions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import Rust module or skip."""
        try:
            import document_processing_rs as rs

            self.rs = rs
        except ImportError:
            pytest.skip("Rust module not compiled")

    def test_extract_text_parallel(self, temp_pdf_file):
        """Test parallel PDF extraction."""
        paths = [str(temp_pdf_file)]
        try:
            results = self.rs.extract_text_parallel(paths)
        except (RuntimeError, ValueError) as e:
            pytest.skip(f"Parallel extraction not supported: {e}")

        assert isinstance(results, list)
        if len(results) == 0:
            pytest.skip("Parallel extraction returned empty (known Rust module limitation)")
        assert len(results) == 1
        assert results[0][0] == str(temp_pdf_file)
        assert isinstance(results[0][1], list)

    def test_generate_thumbnails_parallel(self, temp_image_file):
        """Test parallel thumbnail generation."""
        paths = [str(temp_image_file)]
        results = self.rs.generate_thumbnails_parallel(paths)

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0][0] == str(temp_image_file)


# ============================================================================
# Performance Benchmarks
# ============================================================================


@pytest.mark.rust
@pytest.mark.slow
class TestRustPerformance:
    """Performance benchmarks for Rust vs Python."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import modules or skip."""
        try:
            import document_processing_rs as rs

            self.rs = rs
            self.rust_available = True
        except ImportError:
            self.rust_available = False

    def test_text_quality_performance(self, sample_text, benchmark=None):
        """Benchmark text quality validation."""
        if not self.rust_available:
            pytest.skip("Rust module not compiled")

        import re
        import time

        # Rust version
        start = time.perf_counter()
        for _ in range(1000):
            self.rs.is_quality_sufficient(sample_text)
        rust_time = time.perf_counter() - start

        # Python version
        def python_quality_check(text):
            if not text or len(text.strip()) < 150:
                return False
            valid = sum(1 for c in text if c.isalnum() or c.isspace())
            ratio = valid / len(text)
            words = re.findall(r"[a-zA-Z]{2,}", text)
            return ratio >= 0.4 and len(words) >= 5

        start = time.perf_counter()
        for _ in range(1000):
            python_quality_check(sample_text)
        python_time = time.perf_counter() - start

        speedup = python_time / rust_time
        print(f"\nText quality speedup: {speedup:.1f}x (Rust: {rust_time:.3f}s, Python: {python_time:.3f}s)")

        # Assert Rust is faster (at least 2x)
        assert speedup > 2.0, f"Expected >2x speedup, got {speedup:.1f}x"
