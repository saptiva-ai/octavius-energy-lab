"""
Thumbnail Service - Generate preview images for files

V2: Caches thumbnails in MinIO for persistence and lazy generation.
V3: Delegates PDF thumbnails to file-manager via gRPC when PyMuPDF unavailable.

Generates portrait thumbnails for:
- PDFs: Rasterizes first page to 256x384px JPEG (vertical/portrait)
- Images: Resizes to max 256x384px JPEG with quality=85

Architecture:
1. Check MinIO thumbnails bucket for cached thumbnail
2. If not found, generate from source file:
   - Images: Use Pillow locally
   - PDFs: Use file-manager gRPC (has PyMuPDF)
3. Cache in MinIO and return

Used by /api/documents/{doc_id}/thumbnail endpoint
"""

import io
import tempfile
from pathlib import Path
from typing import Optional

import structlog
from minio.error import S3Error
from PIL import Image

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from .minio_service import minio_service

# gRPC client availability
try:
    from ..clients.file_manager_grpc import (
        get_file_manager_grpc_client,
        is_grpc_available,
    )

    GRPC_AVAILABLE = is_grpc_available()
except ImportError:
    GRPC_AVAILABLE = False

logger = structlog.get_logger(__name__)

# Thumbnail configuration - Portrait/Vertical format (2:3 aspect ratio)
THUMBNAIL_WIDTH = 256  # Fixed width
THUMBNAIL_HEIGHT = 384  # Fixed height (1.5x width for vertical)
THUMBNAIL_QUALITY = 85  # JPEG quality (0-100) - Higher quality for PDFs
PDF_DPI_SCALE = 2.0  # Render PDFs at 2x resolution for better quality
THUMBNAIL_FORMAT = "JPEG"


class ThumbnailService:
    """Service for generating file thumbnails"""

    @staticmethod
    async def generate_pdf_thumbnail(file_path: Path) -> Optional[bytes]:
        """
        Generate high-quality vertical thumbnail from PDF first page

        Uses PyMuPDF locally if available, otherwise delegates to file-manager via gRPC.

        Args:
            file_path: Path to PDF file

        Returns:
            JPEG thumbnail bytes (256x384px portrait) or None if failed
        """
        # Strategy 1: Use local PyMuPDF if available
        if fitz:
            return await ThumbnailService._generate_pdf_thumbnail_local(file_path)

        # Strategy 2: Use file-manager via gRPC (has PyMuPDF)
        if GRPC_AVAILABLE:
            return await ThumbnailService._generate_pdf_thumbnail_grpc(file_path)

        # No available method
        logger.warning(
            "Cannot generate PDF thumbnail - PyMuPDF not available and gRPC unavailable",
            path=str(file_path),
        )
        return None

    @staticmethod
    async def _generate_pdf_thumbnail_local(file_path: Path) -> Optional[bytes]:
        """Generate PDF thumbnail using local PyMuPDF."""
        try:
            doc = fitz.open(str(file_path))

            if doc.page_count == 0:
                logger.warning("PDF has no pages", path=str(file_path))
                return None

            page = doc[0]
            zoom_matrix = fitz.Matrix(PDF_DPI_SCALE, PDF_DPI_SCALE)
            pix = page.get_pixmap(matrix=zoom_matrix)

            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))

            aspect_ratio = img.width / img.height
            target_aspect = THUMBNAIL_WIDTH / THUMBNAIL_HEIGHT

            if aspect_ratio > target_aspect:
                new_width = THUMBNAIL_WIDTH
                new_height = int(THUMBNAIL_WIDTH / aspect_ratio)
            else:
                new_height = THUMBNAIL_HEIGHT
                new_width = int(THUMBNAIL_HEIGHT * aspect_ratio)

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            output = io.BytesIO()
            img.convert("RGB").save(
                output,
                format=THUMBNAIL_FORMAT,
                quality=THUMBNAIL_QUALITY,
                optimize=True,
            )
            output.seek(0)
            doc.close()

            logger.info(
                "Generated PDF thumbnail (local)",
                path=str(file_path),
                size=f"{img.width}x{img.height}",
                bytes=output.getbuffer().nbytes,
            )

            return output.getvalue()

        except Exception as e:
            logger.error(
                "Failed to generate PDF thumbnail (local)",
                error=str(e),
                path=str(file_path),
            )
            return None

    @staticmethod
    async def _generate_pdf_thumbnail_grpc_by_key(
        minio_key: str, minio_bucket: str = ""
    ) -> Optional[bytes]:
        """
        Generate PDF thumbnail via file-manager gRPC service using MinIO key.

        Args:
            minio_key: The MinIO object key (path) for the PDF
            minio_bucket: The MinIO bucket where the file lives

        Returns:
            JPEG thumbnail bytes or None if failed
        """
        try:
            grpc_client = await get_file_manager_grpc_client()

            result = await grpc_client.generate_thumbnail(
                file_path=minio_key,
                width=THUMBNAIL_WIDTH,
                height=THUMBNAIL_HEIGHT,
                bucket=minio_bucket,
            )

            logger.info(
                "Generated PDF thumbnail via gRPC",
                minio_key=minio_key,
                size=len(result.data),
                processing_time_ms=result.processing_time_ms,
            )

            return result.data

        except Exception as e:
            logger.error(
                "Failed to generate PDF thumbnail via gRPC",
                error=str(e),
                minio_key=minio_key,
            )
            return None

    @staticmethod
    async def generate_image_thumbnail(file_path: Path) -> Optional[bytes]:
        """
        Generate high-quality vertical thumbnail from image file

        Args:
            file_path: Path to image file (PNG, JPEG, HEIC, etc.)

        Returns:
            JPEG thumbnail bytes (256x384px portrait) or None if failed
        """
        try:
            # Open image
            img = Image.open(file_path)

            # Convert RGBA to RGB (for PNG with transparency)
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(
                    img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None
                )
                img = background

            # Calculate dimensions to fit in portrait thumbnail (256x384)
            aspect_ratio = img.width / img.height
            target_aspect = THUMBNAIL_WIDTH / THUMBNAIL_HEIGHT

            if aspect_ratio > target_aspect:
                # Image is wider than target - fit by width
                new_width = THUMBNAIL_WIDTH
                new_height = int(THUMBNAIL_WIDTH / aspect_ratio)
            else:
                # Image is taller than target - fit by height
                new_height = THUMBNAIL_HEIGHT
                new_width = int(THUMBNAIL_HEIGHT * aspect_ratio)

            # Resize with high-quality Lanczos resampling
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Convert to JPEG with high quality
            output = io.BytesIO()
            img.convert("RGB").save(
                output,
                format=THUMBNAIL_FORMAT,
                quality=THUMBNAIL_QUALITY,
                optimize=True,
            )
            output.seek(0)

            logger.info(
                "Generated image thumbnail",
                path=str(file_path),
                size=f"{img.width}x{img.height}",
                bytes=output.getbuffer().nbytes,
            )

            return output.getvalue()

        except Exception as e:
            logger.error(
                "Failed to generate image thumbnail", error=str(e), path=str(file_path)
            )
            return None

    @staticmethod
    async def get_or_generate_thumbnail(
        doc_id: str,
        minio_bucket: Optional[str],
        minio_key: Optional[str],
        mimetype: str,
    ) -> Optional[bytes]:
        """
        Get cached thumbnail from MinIO or generate new one (V3)

        For PDFs: Uses gRPC to file-manager when PyMuPDF not available locally.
        For images: Uses Pillow locally.

        Args:
            doc_id: Document ID (used as thumbnail key)
            minio_bucket: Source file bucket (None for legacy)
            minio_key: Source file key (None for legacy)
            mimetype: MIME type of file

        Returns:
            JPEG thumbnail bytes or None if failed
        """
        thumbnail_key = f"{doc_id}.jpg"

        # Step 1: Try to get cached thumbnail from MinIO
        try:
            thumbnail_bytes = await minio_service.download_file(
                minio_service.thumbnails_bucket, thumbnail_key
            )
            logger.info(
                "Served cached thumbnail from MinIO",
                doc_id=doc_id,
                bytes=len(thumbnail_bytes),
            )
            return thumbnail_bytes
        except S3Error as e:
            if e.code != "NoSuchKey":
                logger.warning(
                    "MinIO error fetching thumbnail", doc_id=doc_id, error=str(e)
                )
            # Thumbnail not cached, need to generate

        # Step 2: Generate thumbnail from source file
        if not minio_bucket or not minio_key:
            logger.warning(
                "Cannot generate thumbnail - no source file in MinIO", doc_id=doc_id
            )
            return None

        thumbnail_bytes = None

        # Step 2a: For PDFs, try gRPC directly if local PyMuPDF not available
        is_pdf = mimetype == "application/pdf"
        if is_pdf and not fitz and GRPC_AVAILABLE:
            logger.info(
                "Using gRPC for PDF thumbnail (PyMuPDF not available locally)",
                doc_id=doc_id,
                minio_key=minio_key,
            )
            thumbnail_bytes = (
                await ThumbnailService._generate_pdf_thumbnail_grpc_by_key(
                    minio_key, minio_bucket=minio_bucket or ""
                )
            )
        else:
            # Step 2b: Download to temp and generate locally
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as tmp:
                    tmp_path = Path(tmp.name)

                try:
                    await minio_service.download_to_path(
                        minio_bucket, minio_key, str(tmp_path)
                    )
                    thumbnail_bytes = await ThumbnailService.generate_thumbnail(
                        tmp_path, mimetype
                    )
                finally:
                    tmp_path.unlink(missing_ok=True)

            except Exception as e:
                logger.error(
                    "Failed to generate thumbnail from source",
                    doc_id=doc_id,
                    error=str(e),
                    exc_info=True,
                )
                return None

        # Step 3: Cache successful thumbnail in MinIO
        if thumbnail_bytes:
            try:
                await minio_service.upload_file(
                    minio_service.thumbnails_bucket,
                    thumbnail_key,
                    io.BytesIO(thumbnail_bytes),
                    len(thumbnail_bytes),
                    content_type="image/jpeg",
                )
                logger.info(
                    "Cached thumbnail in MinIO",
                    doc_id=doc_id,
                    bytes=len(thumbnail_bytes),
                )
            except Exception as cache_err:
                logger.warning(
                    "Failed to cache thumbnail in MinIO",
                    doc_id=doc_id,
                    error=str(cache_err),
                )

        return thumbnail_bytes

    @staticmethod
    async def generate_thumbnail(file_path: Path, mimetype: str) -> Optional[bytes]:
        """
        Generate thumbnail for any supported file type (internal method)

        Args:
            file_path: Path to file
            mimetype: MIME type of file

        Returns:
            JPEG thumbnail bytes or None if not supported/failed
        """
        if mimetype == "application/pdf":
            return await ThumbnailService.generate_pdf_thumbnail(file_path)
        elif mimetype.startswith("image/"):
            return await ThumbnailService.generate_image_thumbnail(file_path)
        else:
            logger.debug("Thumbnail not supported for MIME type", mimetype=mimetype)
            return None


# Singleton instance
thumbnail_service = ThumbnailService()
