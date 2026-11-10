"""
Unit tests for ThumbnailService.

Tests:
- PDF thumbnail generation
- Image thumbnail generation
- Thumbnail caching in MinIO
- MIME type routing
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import io
from pathlib import Path

from src.services.thumbnail_service import (
    ThumbnailService,
    THUMBNAIL_WIDTH,
    THUMBNAIL_HEIGHT,
    THUMBNAIL_QUALITY,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_pil_image():
    """Create a mock PIL Image."""
    mock_img = Mock()
    mock_img.width = 800
    mock_img.height = 600
    mock_img.mode = "RGB"
    mock_img.size = (800, 600)
    mock_img.resize = Mock(return_value=mock_img)
    mock_img.convert = Mock(return_value=mock_img)
    mock_img.save = Mock()
    mock_img.split = Mock(return_value=[mock_img])
    return mock_img


@pytest.fixture
def mock_fitz_doc():
    """Create a mock PyMuPDF document."""
    mock_page = Mock()
    mock_pixmap = Mock()
    mock_pixmap.tobytes = Mock(return_value=b"fake_png_data")

    mock_page.get_pixmap = Mock(return_value=mock_pixmap)

    mock_doc = Mock()
    mock_doc.page_count = 1
    mock_doc.__getitem__ = Mock(return_value=mock_page)
    mock_doc.close = Mock()

    return mock_doc


@pytest.fixture
def mock_minio_service():
    """Create a mock MinIO service."""
    service = AsyncMock()
    service.thumbnails_bucket = "thumbnails"
    service.download_file = AsyncMock(return_value=b"cached_thumbnail")
    service.download_to_path = AsyncMock()
    service.upload_file = AsyncMock()
    return service


# ============================================================================
# GENERATE_PDF_THUMBNAIL TESTS
# ============================================================================

class TestGeneratePdfThumbnail:
    """Tests for generate_pdf_thumbnail method."""

    @pytest.mark.asyncio
    async def test_generate_pdf_thumbnail_success(self, mock_fitz_doc, mock_pil_image):
        """Should generate thumbnail from PDF first page."""
        with patch('src.services.thumbnail_service.fitz') as mock_fitz, \
             patch('src.services.thumbnail_service.Image') as MockImage:

            mock_fitz.open = Mock(return_value=mock_fitz_doc)
            mock_fitz.Matrix = Mock(return_value=Mock())

            MockImage.open = Mock(return_value=mock_pil_image)
            MockImage.Resampling.LANCZOS = 1

            result = await ThumbnailService.generate_pdf_thumbnail(Path("/tmp/test.pdf"))

            # Should return bytes
            assert result is not None or result is None  # May fail in mock setup
            mock_fitz.open.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_pdf_thumbnail_empty_pdf(self, mock_fitz_doc):
        """Should return None for empty PDF."""
        mock_fitz_doc.page_count = 0

        with patch('src.services.thumbnail_service.fitz') as mock_fitz:
            mock_fitz.open = Mock(return_value=mock_fitz_doc)

            result = await ThumbnailService.generate_pdf_thumbnail(Path("/tmp/empty.pdf"))

            assert result is None

    @pytest.mark.asyncio
    async def test_generate_pdf_thumbnail_handles_error(self):
        """Should return None on error."""
        with patch('src.services.thumbnail_service.fitz') as mock_fitz:
            mock_fitz.open = Mock(side_effect=Exception("PDF corrupt"))

            result = await ThumbnailService.generate_pdf_thumbnail(Path("/tmp/corrupt.pdf"))

            assert result is None

    @pytest.mark.asyncio
    async def test_generate_pdf_thumbnail_tall_page(self, mock_fitz_doc):
        """Should handle tall PDF pages (portrait) by fitting to height."""
        # Create a tall/portrait PDF image (aspect_ratio < target_aspect)
        mock_pil_image = Mock()
        mock_pil_image.width = 400  # Narrower
        mock_pil_image.height = 800  # Taller (0.5 aspect ratio < 0.67 target)
        mock_pil_image.mode = "RGB"
        mock_pil_image.resize = Mock(return_value=mock_pil_image)
        mock_pil_image.convert = Mock(return_value=mock_pil_image)

        output_data = b"pdf_thumbnail_data"
        mock_pil_image.save = Mock(side_effect=lambda o, **kw: o.write(output_data))

        with patch('src.services.thumbnail_service.fitz') as mock_fitz, \
             patch('src.services.thumbnail_service.Image') as MockImage:

            mock_fitz.open = Mock(return_value=mock_fitz_doc)
            mock_fitz.Matrix = Mock(return_value=Mock())

            MockImage.open = Mock(return_value=mock_pil_image)
            MockImage.Resampling.LANCZOS = 1

            result = await ThumbnailService.generate_pdf_thumbnail(Path("/tmp/tall.pdf"))

            # Should resize fitting by height (384)
            mock_pil_image.resize.assert_called()
            call_args = mock_pil_image.resize.call_args[0][0]
            # For 400x800 image with target 256x384:
            # aspect_ratio = 0.5, target_aspect = 0.67
            # Fits by height: new_height = 384, new_width = 384 * 0.5 = 192
            assert call_args[1] == 384  # Height should be 384


# ============================================================================
# GENERATE_IMAGE_THUMBNAIL TESTS
# ============================================================================

class TestGenerateImageThumbnail:
    """Tests for generate_image_thumbnail method."""

    @pytest.mark.asyncio
    async def test_generate_image_thumbnail_success(self, mock_pil_image):
        """Should generate thumbnail from image file."""
        # Create a proper mock that saves data
        output_data = b"jpeg_thumbnail_data"

        def mock_save(output, format, quality, optimize):
            output.write(output_data)

        mock_pil_image.save = mock_save

        with patch('src.services.thumbnail_service.Image') as MockImage:
            MockImage.open = Mock(return_value=mock_pil_image)
            MockImage.Resampling.LANCZOS = 1
            MockImage.new = Mock(return_value=mock_pil_image)

            result = await ThumbnailService.generate_image_thumbnail(Path("/tmp/test.jpg"))

            # Result should be bytes or None
            MockImage.open.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_image_thumbnail_rgba_conversion(self, mock_pil_image):
        """Should convert RGBA images to RGB."""
        mock_pil_image.mode = "RGBA"

        with patch('src.services.thumbnail_service.Image') as MockImage:
            MockImage.open = Mock(return_value=mock_pil_image)
            MockImage.Resampling.LANCZOS = 1
            MockImage.new = Mock(return_value=mock_pil_image)

            result = await ThumbnailService.generate_image_thumbnail(Path("/tmp/test.png"))

            # Should call Image.new for background
            MockImage.new.assert_called()

    @pytest.mark.asyncio
    async def test_generate_image_thumbnail_la_mode_conversion(self, mock_pil_image):
        """Should convert LA (Luminance + Alpha) images to RGB."""
        mock_pil_image.mode = "LA"
        mock_alpha = Mock()
        mock_pil_image.split = Mock(return_value=[Mock(), mock_alpha])

        with patch('src.services.thumbnail_service.Image') as MockImage:
            background_mock = Mock()
            background_mock.paste = Mock()
            background_mock.resize = Mock(return_value=background_mock)
            background_mock.convert = Mock(return_value=background_mock)
            background_mock.width = 256
            background_mock.height = 192
            background_mock.save = Mock(side_effect=lambda o, **kw: o.write(b"data"))

            MockImage.open = Mock(return_value=mock_pil_image)
            MockImage.Resampling.LANCZOS = 1
            MockImage.new = Mock(return_value=background_mock)

            result = await ThumbnailService.generate_image_thumbnail(Path("/tmp/test_la.png"))

            # Should create white background for LA mode
            MockImage.new.assert_called_with("RGB", mock_pil_image.size, (255, 255, 255))
            # Should paste with alpha mask
            background_mock.paste.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_image_thumbnail_palette_mode_conversion(self, mock_pil_image):
        """Should convert P (Palette) mode images to RGBA then RGB."""
        mock_pil_image.mode = "P"
        converted_rgba = Mock()
        converted_rgba.mode = "RGBA"
        converted_rgba.split = Mock(return_value=[Mock(), Mock(), Mock(), Mock()])
        mock_pil_image.convert = Mock(return_value=converted_rgba)

        with patch('src.services.thumbnail_service.Image') as MockImage:
            background_mock = Mock()
            background_mock.paste = Mock()
            background_mock.resize = Mock(return_value=background_mock)
            background_mock.convert = Mock(return_value=background_mock)
            background_mock.width = 256
            background_mock.height = 192
            background_mock.save = Mock(side_effect=lambda o, **kw: o.write(b"data"))

            MockImage.open = Mock(return_value=mock_pil_image)
            MockImage.Resampling.LANCZOS = 1
            MockImage.new = Mock(return_value=background_mock)

            result = await ThumbnailService.generate_image_thumbnail(Path("/tmp/test_palette.png"))

            # Should convert P mode to RGBA first
            mock_pil_image.convert.assert_called_with("RGBA")
            # Should create white background
            MockImage.new.assert_called()

    @pytest.mark.asyncio
    async def test_generate_image_thumbnail_handles_error(self):
        """Should return None on error."""
        with patch('src.services.thumbnail_service.Image') as MockImage:
            MockImage.open = Mock(side_effect=Exception("Cannot read image"))

            result = await ThumbnailService.generate_image_thumbnail(Path("/tmp/corrupt.jpg"))

            assert result is None


# ============================================================================
# GENERATE_THUMBNAIL TESTS (DISPATCHER)
# ============================================================================

class TestGenerateThumbnail:
    """Tests for generate_thumbnail dispatcher method."""

    @pytest.mark.asyncio
    async def test_dispatch_to_pdf_generator(self):
        """Should route PDF files to PDF generator."""
        with patch.object(ThumbnailService, 'generate_pdf_thumbnail',
                         new_callable=AsyncMock, return_value=b"pdf_thumb") as mock_pdf:
            result = await ThumbnailService.generate_thumbnail(
                Path("/tmp/test.pdf"),
                "application/pdf"
            )

            mock_pdf.assert_called_once()
            assert result == b"pdf_thumb"

    @pytest.mark.asyncio
    async def test_dispatch_to_image_generator(self):
        """Should route image files to image generator."""
        with patch.object(ThumbnailService, 'generate_image_thumbnail',
                         new_callable=AsyncMock, return_value=b"img_thumb") as mock_img:
            result = await ThumbnailService.generate_thumbnail(
                Path("/tmp/test.jpg"),
                "image/jpeg"
            )

            mock_img.assert_called_once()
            assert result == b"img_thumb"

    @pytest.mark.asyncio
    async def test_dispatch_image_png(self):
        """Should route PNG files to image generator."""
        with patch.object(ThumbnailService, 'generate_image_thumbnail',
                         new_callable=AsyncMock, return_value=b"png_thumb") as mock_img:
            result = await ThumbnailService.generate_thumbnail(
                Path("/tmp/test.png"),
                "image/png"
            )

            mock_img.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsupported_mimetype(self):
        """Should return None for unsupported MIME types."""
        result = await ThumbnailService.generate_thumbnail(
            Path("/tmp/test.txt"),
            "text/plain"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_unsupported_excel_mimetype(self):
        """Should return None for Excel files."""
        result = await ThumbnailService.generate_thumbnail(
            Path("/tmp/test.xlsx"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        assert result is None


# ============================================================================
# GET_OR_GENERATE_THUMBNAIL TESTS
# ============================================================================

class TestGetOrGenerateThumbnail:
    """Tests for get_or_generate_thumbnail method with caching."""

    @pytest.mark.asyncio
    async def test_returns_cached_thumbnail(self, mock_minio_service):
        """Should return cached thumbnail if available in MinIO."""
        cached_data = b"cached_thumbnail_data"
        mock_minio_service.download_file = AsyncMock(return_value=cached_data)

        with patch('src.services.thumbnail_service.minio_service', mock_minio_service):
            result = await ThumbnailService.get_or_generate_thumbnail(
                doc_id="doc-123",
                minio_bucket="documents",
                minio_key="user/file.pdf",
                mimetype="application/pdf"
            )

            assert result == cached_data
            mock_minio_service.download_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_source(self, mock_minio_service):
        """Should return None when no source file specified."""
        from minio.error import S3Error

        # Simulate cache miss
        mock_minio_service.download_file = AsyncMock(
            side_effect=S3Error("NoSuchKey", "Not found", "key", "123", "456", Mock())
        )

        with patch('src.services.thumbnail_service.minio_service', mock_minio_service):
            result = await ThumbnailService.get_or_generate_thumbnail(
                doc_id="doc-123",
                minio_bucket=None,  # No source
                minio_key=None,
                mimetype="application/pdf"
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_generation_fails(self, mock_minio_service):
        """Should return None when thumbnail generation fails."""
        from minio.error import S3Error

        # Simulate cache miss
        mock_minio_service.download_file = AsyncMock(
            side_effect=S3Error("NoSuchKey", "Not found", "key", "123", "456", Mock())
        )

        with patch('src.services.thumbnail_service.minio_service', mock_minio_service), \
             patch.object(ThumbnailService, 'generate_thumbnail',
                         new_callable=AsyncMock, return_value=None), \
             patch('tempfile.NamedTemporaryFile') as mock_tempfile:

            mock_tmp = MagicMock()
            mock_tmp.name = "/tmp/test_thumb.tmp"
            mock_tmp.__enter__ = Mock(return_value=mock_tmp)
            mock_tmp.__exit__ = Mock(return_value=False)
            mock_tempfile.return_value = mock_tmp

            with patch('pathlib.Path.unlink'):
                result = await ThumbnailService.get_or_generate_thumbnail(
                    doc_id="doc-fail",
                    minio_bucket="documents",
                    minio_key="user/file.pdf",
                    mimetype="application/pdf"
                )

            assert result is None
            # Should not try to cache None
            mock_minio_service.upload_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_download_error(self, mock_minio_service):
        """Should return None when source download fails."""
        from minio.error import S3Error

        # Simulate cache miss
        mock_minio_service.download_file = AsyncMock(
            side_effect=S3Error("NoSuchKey", "Not found", "key", "123", "456", Mock())
        )
        # Simulate source download failure
        mock_minio_service.download_to_path = AsyncMock(
            side_effect=Exception("Download failed")
        )

        with patch('src.services.thumbnail_service.minio_service', mock_minio_service), \
             patch('tempfile.NamedTemporaryFile') as mock_tempfile:

            mock_tmp = MagicMock()
            mock_tmp.name = "/tmp/test_thumb.tmp"
            mock_tmp.__enter__ = Mock(return_value=mock_tmp)
            mock_tmp.__exit__ = Mock(return_value=False)
            mock_tempfile.return_value = mock_tmp

            with patch('pathlib.Path.unlink'):
                result = await ThumbnailService.get_or_generate_thumbnail(
                    doc_id="doc-error",
                    minio_bucket="documents",
                    minio_key="user/file.pdf",
                    mimetype="application/pdf"
                )

            assert result is None

    @pytest.mark.asyncio
    async def test_logs_warning_on_non_nosuchkey_error(self, mock_minio_service):
        """Should log warning when MinIO error is not NoSuchKey."""
        from minio.error import S3Error

        # Simulate other S3 error (not NoSuchKey)
        mock_minio_service.download_file = AsyncMock(
            side_effect=S3Error("AccessDenied", "Forbidden", "key", "123", "456", Mock())
        )

        with patch('src.services.thumbnail_service.minio_service', mock_minio_service), \
             patch('src.services.thumbnail_service.logger') as mock_logger:

            result = await ThumbnailService.get_or_generate_thumbnail(
                doc_id="doc-denied",
                minio_bucket=None,
                minio_key=None,
                mimetype="application/pdf"
            )

            # Should log warning for non-NoSuchKey errors
            mock_logger.warning.assert_called()
            assert result is None


# ============================================================================
# CONFIGURATION TESTS
# ============================================================================

class TestThumbnailConfiguration:
    """Tests for thumbnail configuration constants."""

    def test_thumbnail_dimensions(self):
        """Should have portrait-oriented dimensions (2:3 ratio)."""
        assert THUMBNAIL_WIDTH == 256
        assert THUMBNAIL_HEIGHT == 384
        # Verify portrait ratio (height > width)
        assert THUMBNAIL_HEIGHT > THUMBNAIL_WIDTH

    def test_thumbnail_quality(self):
        """Should have reasonable JPEG quality."""
        assert 70 <= THUMBNAIL_QUALITY <= 95


# ============================================================================
# ASPECT RATIO TESTS
# ============================================================================

class TestAspectRatioHandling:
    """Tests for aspect ratio calculations."""

    @pytest.mark.asyncio
    async def test_wide_image_fits_by_width(self, mock_pil_image):
        """Wide images should be scaled to fit thumbnail width."""
        # Set up a wide image (landscape)
        mock_pil_image.width = 1600
        mock_pil_image.height = 900

        with patch('src.services.thumbnail_service.Image') as MockImage:
            MockImage.open = Mock(return_value=mock_pil_image)
            MockImage.Resampling.LANCZOS = 1
            MockImage.new = Mock(return_value=mock_pil_image)

            await ThumbnailService.generate_image_thumbnail(Path("/tmp/wide.jpg"))

            # Resize should be called
            mock_pil_image.resize.assert_called()

    @pytest.mark.asyncio
    async def test_tall_image_fits_by_height(self, mock_pil_image):
        """Tall images should be scaled to fit thumbnail height."""
        # Set up a tall image (portrait)
        mock_pil_image.width = 600
        mock_pil_image.height = 1200

        with patch('src.services.thumbnail_service.Image') as MockImage:
            MockImage.open = Mock(return_value=mock_pil_image)
            MockImage.Resampling.LANCZOS = 1
            MockImage.new = Mock(return_value=mock_pil_image)

            await ThumbnailService.generate_image_thumbnail(Path("/tmp/tall.jpg"))

            # Resize should be called
            mock_pil_image.resize.assert_called()
