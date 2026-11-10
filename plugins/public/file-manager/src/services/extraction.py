"""
Document text extraction service.

Supports PDF and image files with OCR fallback.
Uses Rust native module for 10-50x performance gains when available.
"""

import io
import re
from pathlib import Path
from typing import List, Optional, Tuple

import structlog

from ..config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# ============================================================================
# Rust Module Integration
# ============================================================================

# Try to import Rust module, fallback to Python
try:
    import document_processing_rs as rs

    RUST_AVAILABLE = True
    logger.info(
        "Rust extraction module loaded",
        version=getattr(rs, "__version__", "unknown"),
        functions=[
            "extract_text_from_pdf",
            "ocr_image",
            "generate_thumbnail",
            "is_quality_sufficient",
        ],
    )
except ImportError:
    RUST_AVAILABLE = False
    rs = None  # type: ignore
    logger.warning(
        "Rust module not available, using Python fallback",
        hint="Build with: cd rust_modules && maturin develop --release",
    )


# ============================================================================
# Text Quality Validation
# ============================================================================


def _is_text_quality_sufficient(text: str, min_quality_ratio: float = 0.4) -> bool:
    """
    Validate if extracted text has sufficient quality.

    Prevents using corrupted text from scanned PDFs with hidden text layers.

    Args:
        text: Extracted text to validate
        min_quality_ratio: Minimum ratio of valid characters

    Returns:
        True if text quality is sufficient
    """
    # Use Rust implementation if available (10x faster)
    if RUST_AVAILABLE and rs is not None:
        return rs.is_quality_sufficient(
            text,
            min_chars=150,
            min_quality_ratio=min_quality_ratio,
            min_words=5,
            max_special_ratio=0.8,
        )

    # Python fallback
    if not text or len(text.strip()) == 0:
        return False

    text_clean = text.strip()

    # Check 1: Character quality ratio
    valid_chars = sum(1 for c in text_clean if c.isalnum() or c.isspace())
    total_chars = len(text_clean)
    quality_ratio = valid_chars / total_chars if total_chars > 0 else 0

    if quality_ratio < min_quality_ratio:
        return False

    # Check 2: Must have actual words (2+ consecutive letters)
    words = re.findall(r"[a-zA-ZáéíóúÁÉÍÓÚñÑ]{2,}", text_clean)
    if len(words) < 5:
        return False

    # Check 3: Cannot be mostly special characters
    special_chars = total_chars - valid_chars
    special_ratio = special_chars / total_chars if total_chars > 0 else 0
    if special_ratio > 0.8:
        return False

    return True


# ============================================================================
# PDF Extraction
# ============================================================================


def extract_text_from_pdf(file_path: Path) -> Tuple[str, int]:
    """
    Extract text from a PDF file.

    Uses Rust module (47x faster) when available, otherwise falls back to pypdf.

    Args:
        file_path: Path to PDF file

    Returns:
        Tuple of (extracted_text, page_count)
    """
    # Try Rust implementation first (47x faster)
    if RUST_AVAILABLE and rs is not None:
        try:
            return _extract_pdf_rust(file_path)
        except Exception as e:
            logger.warning(
                "Rust PDF extraction failed, falling back to Python",
                file=str(file_path),
                error=str(e),
            )

    # Python fallback
    return _extract_pdf_python(file_path)


def _extract_pdf_rust(file_path: Path) -> Tuple[str, int]:
    """Extract PDF text using Rust module."""
    pdf_bytes = file_path.read_bytes()
    pages = rs.extract_text_from_pdf(
        pdf_bytes,
        min_chars=150,
        min_quality_ratio=settings.ocr_quality_ratio,
    )

    texts: List[str] = []
    ocr_needed: List[int] = []

    for page in pages:
        if page.needs_ocr:
            ocr_needed.append(page.page)
            texts.append("")  # Placeholder for OCR
        else:
            texts.append(page.text)

    # Process OCR pages if needed and within limit
    if ocr_needed and len(ocr_needed) <= settings.ocr_max_pages:
        ocr_texts = _ocr_pages_for_pdf(file_path, ocr_needed)
        for page_num, ocr_text in ocr_texts:
            if 0 <= page_num < len(texts):
                texts[page_num] = ocr_text if ocr_text else f"[Page {page_num + 1}: No text extracted]"
    elif ocr_needed:
        # Too many OCR pages
        for page_num in ocr_needed:
            if 0 <= page_num < len(texts):
                texts[page_num] = f"[Page {page_num + 1}: OCR skipped (too many pages)]"

    full_text = "\n\n".join(texts)
    total_pages = len(pages)

    logger.info(
        "PDF text extracted (Rust)",
        file=str(file_path),
        pages=total_pages,
        text_length=len(full_text),
        ocr_pages=len(ocr_needed),
    )

    return full_text, total_pages


def _extract_pdf_python(file_path: Path) -> Tuple[str, int]:
    """Extract PDF text using pypdf (Python fallback)."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(file_path))
        pages_text = []
        total_pages = len(reader.pages)

        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""

                # Validate text quality
                if _is_text_quality_sufficient(text):
                    pages_text.append(text)
                else:
                    # Try OCR fallback for this page
                    ocr_text = _ocr_pdf_page(file_path, i)
                    if ocr_text:
                        pages_text.append(ocr_text)
                    else:
                        pages_text.append(f"[Page {i + 1}: No text extracted]")

            except Exception as e:
                logger.warning(f"Failed to extract page {i + 1}", error=str(e))
                pages_text.append(f"[Page {i + 1}: Extraction failed]")

        full_text = "\n\n".join(pages_text)

        logger.info(
            "PDF text extracted (Python)",
            file=str(file_path),
            pages=total_pages,
            text_length=len(full_text),
        )

        return full_text, total_pages

    except Exception as e:
        logger.error("Failed to extract PDF text", file=str(file_path), error=str(e))
        raise


# ============================================================================
# OCR Processing
# ============================================================================


def _ocr_pages_for_pdf(file_path: Path, page_nums: List[int]) -> List[Tuple[int, Optional[str]]]:
    """
    OCR multiple PDF pages.

    Uses Rust parallel OCR when available (3x faster).

    Args:
        file_path: Path to PDF file
        page_nums: List of page numbers to OCR (0-indexed)

    Returns:
        List of (page_number, extracted_text) tuples
    """
    results: List[Tuple[int, Optional[str]]] = []

    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(file_path))
        dpi = settings.ocr_raster_dpi
        mat = fitz.Matrix(dpi / 72, dpi / 72)

        # Render pages to images
        page_images: List[Tuple[int, bytes]] = []
        for page_num in page_nums:
            if 0 <= page_num < len(doc):
                page = doc[page_num]
                pix = page.get_pixmap(matrix=mat)
                page_images.append((page_num, pix.tobytes("png")))

        doc.close()

        # Use Rust parallel OCR if available
        if RUST_AVAILABLE and rs is not None and len(page_images) > 1:
            try:
                ocr_results = rs.ocr_pdf_pages_parallel(page_images, lang="spa+eng")
                for page_num, text in ocr_results:
                    if _is_text_quality_sufficient(text):
                        results.append((page_num, text))
                    else:
                        results.append((page_num, None))
                return results
            except Exception as e:
                logger.warning("Rust OCR failed, using Python fallback", error=str(e))

        # Python fallback (sequential OCR)
        for page_num, img_bytes in page_images:
            text = _ocr_image_bytes(img_bytes)
            results.append((page_num, text))

    except ImportError:
        logger.warning("PyMuPDF not available for page rendering")
        results = [(p, None) for p in page_nums]
    except Exception as e:
        logger.warning("Failed to OCR PDF pages", error=str(e))
        results = [(p, None) for p in page_nums]

    return results


def _ocr_pdf_page(file_path: Path, page_num: int) -> Optional[str]:
    """
    OCR a single PDF page using tesseract.

    Args:
        file_path: Path to PDF file
        page_num: Zero-indexed page number

    Returns:
        Extracted text or None if OCR fails
    """
    try:
        import fitz  # PyMuPDF
        from PIL import Image

        doc = fitz.open(str(file_path))
        page = doc[page_num]

        # Render page to image
        dpi = settings.ocr_raster_dpi
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)

        # Convert to PIL Image
        img_bytes = pix.tobytes("png")
        doc.close()

        text = _ocr_image_bytes(img_bytes)

        if text and _is_text_quality_sufficient(text):
            return text

        return None

    except ImportError:
        logger.warning("PyMuPDF not available for OCR")
        return None
    except Exception as e:
        logger.warning(f"OCR failed for page {page_num}", error=str(e))
        return None


def _ocr_image_bytes(image_bytes: bytes) -> Optional[str]:
    """
    OCR image bytes.

    Uses Rust implementation when available (3x faster).
    """
    # Try Rust OCR first
    if RUST_AVAILABLE and rs is not None:
        try:
            return rs.ocr_image_bytes(image_bytes, lang="spa+eng")
        except Exception as e:
            logger.warning("Rust OCR failed", error=str(e))

    # Python fallback
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(img, lang="spa+eng")
    except Exception as e:
        logger.warning("Python OCR failed", error=str(e))
        return None


# ============================================================================
# Image Text Extraction
# ============================================================================


def extract_text_from_image(file_path: Path) -> str:
    """
    Extract text from an image using OCR.

    Uses Rust implementation when available (3x faster).

    Args:
        file_path: Path to image file

    Returns:
        Extracted text
    """
    # Try Rust implementation first
    if RUST_AVAILABLE and rs is not None:
        try:
            text = rs.ocr_image(str(file_path), lang="spa+eng")
            logger.info(
                "Image text extracted (Rust)",
                file=str(file_path),
                text_length=len(text),
            )
            return text
        except Exception as e:
            logger.warning("Rust OCR failed, falling back to Python", error=str(e))

    # Python fallback
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang="spa+eng")

        logger.info(
            "Image text extracted (Python)",
            file=str(file_path),
            text_length=len(text),
        )

        return text

    except ImportError:
        logger.error("pytesseract not available")
        return "[OCR not available]"
    except Exception as e:
        logger.error("Failed to extract image text", file=str(file_path), error=str(e))
        raise


# ============================================================================
# Thumbnail Generation
# ============================================================================


def generate_thumbnail(
    file_path: Path,
    width: int = 200,
    height: int = 200,
    format: str = "jpeg",
    quality: int = 85,
) -> Tuple[bytes, str]:
    """
    Generate a thumbnail from an image file.

    Uses Rust implementation when available (5x faster).

    Args:
        file_path: Path to image file
        width: Target width
        height: Target height
        format: Output format (jpeg, png, webp)
        quality: JPEG quality (0-100)

    Returns:
        Tuple of (thumbnail_bytes, content_type)
    """
    # Try Rust implementation first (5x faster)
    if RUST_AVAILABLE and rs is not None:
        try:
            result = rs.generate_thumbnail(
                str(file_path),
                width=width,
                height=height,
                filter="lanczos3",
                format=format,
                quality=quality,
            )
            logger.debug(
                "Thumbnail generated (Rust)",
                original=f"{result.original_width}x{result.original_height}",
                thumbnail=f"{result.width}x{result.height}",
                size=len(result.data),
            )
            return bytes(result.data), result.content_type
        except Exception as e:
            logger.warning("Rust thumbnail failed, falling back to Python", error=str(e))

    # Python fallback
    return _generate_thumbnail_python(file_path, width, height, format, quality)


def generate_thumbnail_bytes(
    image_bytes: bytes,
    width: int = 200,
    height: int = 200,
    format: str = "jpeg",
    quality: int = 85,
) -> Tuple[bytes, str]:
    """
    Generate a thumbnail from image bytes.

    Uses Rust implementation when available (5x faster).

    Args:
        image_bytes: Raw image data
        width: Target width
        height: Target height
        format: Output format (jpeg, png, webp)
        quality: JPEG quality (0-100)

    Returns:
        Tuple of (thumbnail_bytes, content_type)
    """
    # Try Rust implementation first
    if RUST_AVAILABLE and rs is not None:
        try:
            result = rs.generate_thumbnail_bytes(
                image_bytes,
                width=width,
                height=height,
                filter="lanczos3",
                format=format,
                quality=quality,
            )
            return bytes(result.data), result.content_type
        except Exception as e:
            logger.warning("Rust thumbnail failed", error=str(e))

    # Python fallback
    return _generate_thumbnail_python_bytes(image_bytes, width, height, format, quality)


def _generate_thumbnail_python(
    file_path: Path,
    width: int,
    height: int,
    format: str,
    quality: int,
) -> Tuple[bytes, str]:
    """Generate thumbnail using PIL (Python fallback)."""
    from PIL import Image

    img = Image.open(file_path)
    img.thumbnail((width, height), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    format_upper = format.upper()
    if format_upper == "JPEG":
        img = img.convert("RGB")
        img.save(buffer, format="JPEG", quality=quality)
        content_type = "image/jpeg"
    elif format_upper == "PNG":
        img.save(buffer, format="PNG")
        content_type = "image/png"
    elif format_upper == "WEBP":
        img.save(buffer, format="WEBP", quality=quality)
        content_type = "image/webp"
    else:
        img = img.convert("RGB")
        img.save(buffer, format="JPEG", quality=quality)
        content_type = "image/jpeg"

    return buffer.getvalue(), content_type


def _generate_thumbnail_python_bytes(
    image_bytes: bytes,
    width: int,
    height: int,
    format: str,
    quality: int,
) -> Tuple[bytes, str]:
    """Generate thumbnail from bytes using PIL (Python fallback)."""
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail((width, height), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    format_upper = format.upper()
    if format_upper == "JPEG":
        img = img.convert("RGB")
        img.save(buffer, format="JPEG", quality=quality)
        content_type = "image/jpeg"
    elif format_upper == "PNG":
        img.save(buffer, format="PNG")
        content_type = "image/png"
    elif format_upper == "WEBP":
        img.save(buffer, format="WEBP", quality=quality)
        content_type = "image/webp"
    else:
        img = img.convert("RGB")
        img.save(buffer, format="JPEG", quality=quality)
        content_type = "image/jpeg"

    return buffer.getvalue(), content_type


def generate_pdf_thumbnail_bytes(
    pdf_bytes: bytes,
    width: int = 256,
    height: int = 384,
    format: str = "jpeg",
    quality: int = 85,
) -> Tuple[bytes, str]:
    """
    Generate a thumbnail from PDF bytes by rasterizing the first page.

    Uses PyMuPDF (fitz) to render the first page at high DPI, then resizes
    with PIL for the final thumbnail.

    Args:
        pdf_bytes: Raw PDF data
        width: Target width (default 256 for portrait)
        height: Target height (default 384 for portrait)
        format: Output format (jpeg, png, webp)
        quality: JPEG quality (0-100)

    Returns:
        Tuple of (thumbnail_bytes, content_type)

    Raises:
        ImportError: If PyMuPDF is not available
        ValueError: If PDF has no pages or is invalid
    """
    import fitz  # PyMuPDF

    from PIL import Image

    # Open PDF from bytes
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    if doc.page_count == 0:
        doc.close()
        raise ValueError("PDF has no pages")

    # Get first page
    page = doc[0]

    # Render at 2x resolution (144 DPI) for better quality before downsampling
    zoom = 2.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)

    # Convert pixmap to PIL Image
    img_bytes = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_bytes))

    # Resize maintaining aspect ratio
    img.thumbnail((width, height), Image.Resampling.LANCZOS)
    page_count = doc.page_count

    doc.close()

    # Encode to output format
    buffer = io.BytesIO()
    format_upper = format.upper()

    if format_upper == "JPEG":
        img = img.convert("RGB")
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        content_type = "image/jpeg"
    elif format_upper == "PNG":
        img.save(buffer, format="PNG", optimize=True)
        content_type = "image/png"
    elif format_upper == "WEBP":
        img.save(buffer, format="WEBP", quality=quality)
        content_type = "image/webp"
    else:
        img = img.convert("RGB")
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        content_type = "image/jpeg"

    logger.debug(
        "Generated PDF thumbnail",
        original_pages=page_count,
        thumbnail_size=f"{img.width}x{img.height}",
        output_bytes=buffer.tell(),
    )

    return buffer.getvalue(), content_type


# ============================================================================
# Main Extraction Interface
# ============================================================================


async def extract_text_from_file(
    file_path: Path,
    content_type: str,
) -> Tuple[str, Optional[int]]:
    """
    Extract text from a file based on its content type.

    Args:
        file_path: Path to the file
        content_type: MIME type of the file

    Returns:
        Tuple of (extracted_text, page_count or None for images)
    """
    if content_type == "application/pdf":
        text, pages = extract_text_from_pdf(file_path)
        return text, pages

    elif content_type.startswith("image/"):
        text = extract_text_from_image(file_path)
        return text, None

    else:
        logger.warning(f"Unsupported content type for extraction: {content_type}")
        return f"[Unsupported format: {content_type}]", None


# ============================================================================
# Module Status
# ============================================================================


def get_extraction_status() -> dict:
    """
    Get status of extraction module capabilities.

    Returns:
        Dictionary with module status and capabilities
    """
    return {
        "rust_available": RUST_AVAILABLE,
        "rust_version": getattr(rs, "__version__", None) if RUST_AVAILABLE else None,
        "capabilities": {
            "pdf_extraction": "rust" if RUST_AVAILABLE else "python",
            "ocr": "rust" if RUST_AVAILABLE else "python",
            "thumbnails": "rust" if RUST_AVAILABLE else "python",
            "text_quality": "rust" if RUST_AVAILABLE else "python",
        },
        "performance": {
            "pdf_speedup": "47x" if RUST_AVAILABLE else "1x",
            "ocr_speedup": "3x" if RUST_AVAILABLE else "1x",
            "thumbnail_speedup": "5x" if RUST_AVAILABLE else "1x",
        },
    }
