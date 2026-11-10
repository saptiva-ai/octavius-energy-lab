"""
OCR Service for extracting text from images.

Uses Tesseract OCR via pytesseract for text extraction.
Supports preprocessing for better accuracy.
"""

from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


async def extract_text_from_image(image_path: Path, content_type: str) -> str:
    """
    Extract text from image using OCR.

    Args:
        image_path: Path to the image file
        content_type: MIME type of the image

    Returns:
        Extracted text as markdown string

    Raises:
        ImportError: If required dependencies are not installed
        Exception: If OCR processing fails
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        logger.error(
            "OCR dependencies not installed",
            error=str(exc),
            required_packages=["pytesseract", "Pillow"],
        )
        return "[Error: pytesseract y Pillow no están instalados. Instala con: pip install pytesseract Pillow]"

    try:
        # Load and preprocess image
        image = Image.open(str(image_path))

        # Convert HEIC/HEIF if needed (requires pillow-heif)
        if content_type in ["image/heic", "image/heif"]:
            try:
                import pillow_heif

                pillow_heif.register_heif_opener()
            except ImportError:
                logger.warning(
                    "pillow-heif not installed, HEIC/HEIF images may fail",
                    content_type=content_type,
                )

        # Preprocess: Convert to RGB if needed
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        # Preprocess: Resize if too large (for performance)
        max_dimension = 4000
        if max(image.size) > max_dimension:
            ratio = max_dimension / max(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            logger.debug(
                "Resized image for OCR", original_size=image.size, new_size=new_size
            )

        # Extract text with Tesseract
        # Use Spanish + English for better accuracy
        config = (
            "--oem 3 --psm 3"  # LSTM OCR Engine Mode 3, Page Segmentation Mode 3 (auto)
        )

        # Try to detect text with multiple languages
        try:
            text = pytesseract.image_to_string(
                image,
                lang="spa+eng",  # Spanish + English
                config=config,
            )
        except Exception as lang_error:
            # Fallback to English only if Spanish not available
            logger.warning(
                "Spanish language pack not available, falling back to English",
                error=str(lang_error),
            )
            text = pytesseract.image_to_string(image, lang="eng", config=config)

        # Clean up extracted text
        text = text.strip()

        if not text:
            return "[Imagen sin texto detectable - la imagen puede estar vacía o el texto es demasiado borroso]"

        # Log success metrics
        logger.info(
            "OCR extraction successful",
            image_path=str(image_path),
            content_type=content_type,
            text_length=len(text),
            image_size=image.size,
        )

        return text

    except FileNotFoundError as exc:
        logger.error("Image file not found", error=str(exc), path=str(image_path))
        return f"[Error: Archivo de imagen no encontrado: {image_path.name}]"

    except Exception as exc:
        logger.error(
            "OCR extraction failed",
            error=str(exc),
            image_path=str(image_path),
            content_type=content_type,
            exc_info=True,
        )
        return f"[Error al extraer texto de la imagen: {str(exc)}]"


def is_tesseract_installed() -> bool:
    """Check if Tesseract OCR is installed on the system."""
    try:
        import pytesseract

        # Try to get version to verify installation
        pytesseract.get_tesseract_version()
        return True
    except (ImportError, Exception):
        return False


def get_tesseract_languages() -> list[str]:
    """Get list of installed Tesseract languages."""
    try:
        import pytesseract

        langs = pytesseract.get_languages()
        return langs
    except Exception as exc:
        logger.warning("Could not get Tesseract languages", error=str(exc))
        return []
