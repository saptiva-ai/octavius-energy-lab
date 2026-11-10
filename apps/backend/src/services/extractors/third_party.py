"""
Third-Party Text Extraction Implementation

Uses existing extraction libraries:
- pypdf for PDF text extraction
- pytesseract for image OCR
- Pillow for image preprocessing

This implementation wraps the legacy code in `document_extraction.py`
and `ocr_service.py` to maintain backwards compatibility while providing
a clean abstraction interface.
"""

import tempfile
from pathlib import Path
from typing import Optional

import structlog

from .base import (
    ExtractionError,
    MediaType,
    TextExtractor,
    UnsupportedFormatError,
)

logger = structlog.get_logger(__name__)

# Optional third-party dependencies (mock-friendly for unit tests)
try:
    from pypdf import PdfReader  # type: ignore
except ImportError:  # pragma: no cover - handled in runtime checks
    PdfReader = None  # type: ignore[assignment]

try:
    from PIL import Image  # type: ignore
except ImportError:  # pragma: no cover - handled in runtime checks
    Image = None  # type: ignore[assignment]

try:
    import pytesseract  # type: ignore
except ImportError:  # pragma: no cover - handled in runtime checks
    pytesseract = None  # type: ignore[assignment]


class ThirdPartyExtractor(TextExtractor):
    """
    Text extractor using third-party libraries (pypdf + pytesseract).

    This implementation maintains compatibility with the existing extraction
    pipeline while conforming to the new TextExtractor interface.

    Implementation Details:
        - PDF: Uses pypdf.PdfReader.extract_text()
        - Image: Uses pytesseract with Spanish+English language support
        - Temporary files: Creates /tmp files for Path-based legacy code
        - Cleanup: Removes temp files after extraction
    """

    async def extract_text(
        self,
        *,
        media_type: MediaType,
        data: bytes,
        mime: str,
        filename: Optional[str] = None,
    ) -> str:
        """
        Extract text using pypdf or pytesseract.

        Args:
            media_type: "pdf" or "image"
            data: Raw document bytes
            mime: MIME type (e.g., "application/pdf", "image/png")
            filename: Optional filename for logging/context

        Returns:
            Extracted text as plain string. Returns empty string if no text found.

        Raises:
            UnsupportedFormatError: If MIME type is not supported
            ExtractionError: If extraction fails
        """
        # Validate media type matches MIME
        self._validate_mime_type(media_type, mime)

        # Create temporary file (legacy code requires Path)
        temp_file = None
        try:
            # Determine file suffix from MIME type
            suffix = self._get_suffix_from_mime(mime)

            # Write bytes to temporary file
            temp_file = tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=suffix,
                delete=False,  # We'll delete manually
            )
            temp_file.write(data)
            temp_file.flush()
            temp_file.close()  # Close before reading (Windows compatibility)

            temp_path = Path(temp_file.name)

            # Route to appropriate extraction method
            if media_type == "pdf":
                text = await self._extract_pdf_text(
                    temp_path, filename or "document.pdf"
                )
            else:  # media_type == "image"
                text = await self._extract_image_text(
                    temp_path, mime, filename or "image"
                )

            logger.info(
                "Third-party extraction successful",
                media_type=media_type,
                mime=mime,
                text_length=len(text),
                filename=filename,
            )

            return text

        except Exception as exc:
            logger.error(
                "Third-party extraction failed",
                media_type=media_type,
                mime=mime,
                error=str(exc),
                filename=filename,
            )
            raise ExtractionError(
                f"Failed to extract text from {media_type}: {str(exc)}",
                media_type=media_type,
                original_error=exc,
            )

        finally:
            # Clean up temporary file
            if temp_file:
                try:
                    Path(temp_file.name).unlink(missing_ok=True)
                except Exception as cleanup_error:
                    logger.warning(
                        "Failed to delete temp file",
                        temp_file=temp_file.name,
                        error=str(cleanup_error),
                    )

    async def _extract_pdf_text(self, file_path: Path, filename: str) -> str:
        """
        Extract text from PDF using pypdf.

        Args:
            file_path: Path to temporary PDF file
            filename: Original filename for logging

        Returns:
            Concatenated text from all pages

        Raises:
            ImportError: If pypdf is not installed
            ExtractionError: If PDF reading fails
        """
        if PdfReader is None:
            raise ExtractionError(
                "pypdf not installed. Install with: pip install pypdf>=3.17.0",
                media_type="pdf",
            )

        try:
            reader = PdfReader(str(file_path))
            all_text = []

            for page_num, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                text = text.strip()

                if not text:
                    text = f"[Página {page_num} sin texto extraíble]"

                all_text.append(text)

            # Join all pages with double newlines
            result = "\n\n".join(all_text)

            logger.debug(
                "PDF extraction completed",
                filename=filename,
                pages=len(reader.pages),
                text_length=len(result),
            )

            return result

        except Exception as exc:
            raise ExtractionError(
                f"Failed to extract text from PDF '{filename}': {str(exc)}",
                media_type="pdf",
                original_error=exc,
            )

    async def _extract_image_text(
        self, file_path: Path, content_type: str, filename: str
    ) -> str:
        """
        Extract text from image using Tesseract OCR.

        Args:
            file_path: Path to temporary image file
            content_type: MIME type for format handling
            filename: Original filename for logging

        Returns:
            OCR-extracted text

        Raises:
            ImportError: If pytesseract or PIL is not installed
            ExtractionError: If OCR processing fails
        """
        if Image is None or pytesseract is None:
            raise ExtractionError(
                "OCR dependencies not installed. Install with: pip install pytesseract Pillow",
                media_type="image",
            )

        try:
            # Load and preprocess image
            image = Image.open(str(file_path))

            # Convert HEIC/HEIF if needed
            if content_type in ["image/heic", "image/heif"]:
                try:
                    import pillow_heif

                    pillow_heif.register_heif_opener()
                except ImportError:
                    logger.warning(
                        "pillow-heif not installed, HEIC/HEIF may fail",
                        content_type=content_type,
                    )

            # Preprocessing: Convert to RGB
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")

            # Preprocessing: Resize if too large (performance + memory)
            max_dimension = 4000
            if max(image.size) > max_dimension:
                ratio = max_dimension / max(image.size)
                new_size = tuple(int(dim * ratio) for dim in image.size)
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                logger.debug(
                    "Resized image for OCR",
                    original_size=image.size,
                    new_size=new_size,
                    filename=filename,
                )

            # OCR configuration: LSTM engine + auto page segmentation
            config = "--oem 3 --psm 3"

            # Try Spanish + English first, fallback to English only
            try:
                text = pytesseract.image_to_string(
                    image,
                    lang="spa+eng",
                    config=config,
                )
            except Exception as lang_error:
                logger.warning(
                    "Spanish language pack not available, falling back to English",
                    error=str(lang_error),
                    filename=filename,
                )
                text = pytesseract.image_to_string(
                    image,
                    lang="eng",
                    config=config,
                )

            # Clean up extracted text
            text = text.strip()

            if not text:
                return "[Imagen sin texto detectable - la imagen puede estar vacía o el texto es demasiado borroso]"

            logger.info(
                "image_extraction_summary",
                file_id=locals().get("file_id"),
                filename=filename,
                content_type=content_type,
                text_len=len(text),
                image_size=image.size,
            )

            logger.debug(
                "OCR extraction completed",
                filename=filename,
                content_type=content_type,
                text_length=len(text),
                image_size=image.size,
            )

            return text

        except FileNotFoundError as exc:
            raise ExtractionError(
                f"Image file not found: {filename}",
                media_type="image",
                original_error=exc,
            )

        except Exception as exc:
            raise ExtractionError(
                f"Failed to extract text from image '{filename}': {str(exc)}",
                media_type="image",
                original_error=exc,
            )

    async def health_check(self) -> bool:
        """
        Check if third-party extraction tools are available.

        Checks:
            - pypdf can be imported
            - pytesseract can be imported
            - Tesseract binary is installed on system

        Returns:
            True if all dependencies are available, False otherwise
        """
        if PdfReader is None or pytesseract is None:
            logger.warning(
                "Third-party extractor health check failed: dependencies missing",
                has_pdf_reader=PdfReader is not None,
                has_pytesseract=pytesseract is not None,
            )
            return False

        try:
            pytesseract.get_tesseract_version()
        except Exception as exc:
            logger.warning(
                "Third-party extractor health check failed: tesseract unavailable",
                error=str(exc),
            )
            return False

        logger.debug("Third-party extractor health check passed")
        return True

    def _validate_mime_type(self, media_type: MediaType, mime: str) -> None:
        """
        Validate that MIME type matches media type.

        Args:
            media_type: Expected media type ("pdf" or "image")
            mime: MIME type to validate

        Raises:
            UnsupportedFormatError: If MIME type is not supported
        """
        if media_type == "pdf":
            if mime != "application/pdf":
                raise UnsupportedFormatError(
                    f"MIME type '{mime}' is not supported for PDF extraction. Expected 'application/pdf'.",
                    media_type=media_type,
                )
        elif media_type == "image":
            supported_image_mimes = {
                "image/png",
                "image/jpeg",
                "image/jpg",
                "image/heic",
                "image/heif",
                "image/gif",
            }
            if mime not in supported_image_mimes:
                raise UnsupportedFormatError(
                    f"MIME type '{mime}' is not supported for image extraction. "
                    f"Supported types: {', '.join(supported_image_mimes)}",
                    media_type=media_type,
                )

    def _get_suffix_from_mime(self, mime: str) -> str:
        """
        Get file suffix from MIME type.

        Args:
            mime: MIME type

        Returns:
            File suffix with leading dot (e.g., ".pdf", ".png")
        """
        mime_to_suffix = {
            "application/pdf": ".pdf",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/heic": ".heic",
            "image/heif": ".heif",
            "image/gif": ".gif",
        }
        return mime_to_suffix.get(mime, ".tmp")
