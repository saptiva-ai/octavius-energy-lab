"""
Utilities for extracting text/tables from uploaded documents.

This module provides a high-level interface for document text extraction.
Uses pluggable extractors (pypdf+pytesseract or Saptiva) via factory pattern.

Configuration:
    EXTRACTOR_PROVIDER: "third_party" (default) | "saptiva" | "huggingface"
    MAX_OCR_PAGES: Maximum pages to OCR for image-only PDFs (default: 30)
    OCR_RASTER_DPI: Rasterization DPI for OCR fallback (default: 180)
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from ..core.config import get_settings
from ..models.document import PageContent
from .extractors import ExtractionError, UnsupportedFormatError, get_text_extractor
from .extractors.pdf_raster_ocr import raster_single_page_and_ocr

logger = structlog.get_logger(__name__)


def _is_text_quality_sufficient(text: str, min_quality_ratio: float = 0.4) -> bool:
    """
    Validate if extracted text has sufficient quality to be usable.

    Prevents using corrupted text from scanned PDFs that have hidden text layers
    with metadata or garbage characters.

    Args:
        text: Extracted text to validate
        min_quality_ratio: Minimum ratio of valid characters (default: 0.4 = 40%)

    Returns:
        True if text quality is sufficient, False otherwise

    Criteria:
        - At least 40% of characters must be alphanumeric or spaces
        - Must have at least 5 actual words (sequences of 2+ letters)
        - Cannot be >80% special characters
        - This filters out text layers with only metadata/control characters
    """
    if not text or len(text.strip()) == 0:
        return False

    text_clean = text.strip()

    # Check 1: Character quality ratio
    valid_chars = sum(1 for c in text_clean if c.isalnum() or c.isspace())
    total_chars = len(text_clean)
    quality_ratio = valid_chars / total_chars if total_chars > 0 else 0

    if quality_ratio < min_quality_ratio:
        return False

    # Check 2: Must have actual words (not just random chars)
    # A "word" is 2+ consecutive letters
    import re

    words = re.findall(r"[a-zA-ZáéíóúÁÉÍÓÚñÑ]{2,}", text_clean)
    if len(words) < 5:
        # Less than 5 words → probably garbage
        return False

    # Check 3: Cannot be mostly special characters
    special_chars = total_chars - valid_chars
    special_ratio = special_chars / total_chars if total_chars > 0 else 0
    if special_ratio > 0.8:  # More than 80% special chars
        return False

    return True


async def extract_text_from_file(
    file_path: Path, content_type: str
) -> List[PageContent]:
    """
    Extract text from PDF or image files using pluggable extractor.

    This function routes to the appropriate extraction backend based on
    EXTRACTOR_PROVIDER environment variable:
        - third_party: pypdf + pytesseract (current default)
        - saptiva: Saptiva Native Tools API
        - huggingface: DeepSeek OCR via Hugging Face Space

    Args:
        file_path: Path to document file on disk
        content_type: MIME type (e.g., "application/pdf", "image/png")

    Returns:
        List of PageContent objects with extracted text

        For PDFs: One PageContent per page
        For Images: Single PageContent with OCR text
        For Unsupported: Single PageContent with error message

    Example:
        pages = await extract_text_from_file(
            Path("/tmp/document.pdf"),
            "application/pdf"
        )
        for page in pages:
            print(f"Page {page.page}: {page.text_md[:100]}...")
    """
    pages: List[PageContent] = []

    try:
        # Determine media type from content_type
        if content_type == "application/pdf":
            media_type = "pdf"
        elif content_type in [
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/heic",
            "image/heif",
            "image/gif",
        ]:
            media_type = "image"
        else:
            # Unsupported format
            logger.warning(
                "Unsupported content type for extraction",
                content_type=content_type,
                file_path=str(file_path),
            )
            pages.append(
                PageContent(
                    page=1,
                    text_md=f"[Formato no soportado: {content_type}]",
                    has_table=False,
                )
            )
            return pages

        # Read file bytes
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        # Special handling for PDFs: Hybrid extraction (pypdf + selective OCR)
        if media_type == "pdf":
            # Hybrid approach: Try pypdf first, apply OCR to pages with insufficient text
            try:
                import fitz  # PyMuPDF for OCR fallback
                from pypdf import PdfReader

                settings = get_settings()
                # ANTI-HALLUCINATION FIX: Increased from 50 to 150 chars
                # Many scanned PDFs have hidden text layers with 50-100 chars of garbage
                MIN_CHARS_THRESHOLD = 150

                reader = PdfReader(io.BytesIO(file_bytes))
                total_pages = len(reader.pages)
                temp_pages: List[PageContent] = []

                # Counters for telemetry
                pypdf_count = 0
                ocr_count = 0
                error_count = 0

                logger.info(
                    "Starting hybrid PDF extraction (pypdf + selective OCR)",
                    total_pages=total_pages,
                    min_chars_threshold=MIN_CHARS_THRESHOLD,
                    file_path=str(file_path),
                )

                # Open PDF with PyMuPDF for OCR fallback (if needed)
                fitz_doc = None
                try:
                    fitz_doc = fitz.open(stream=file_bytes, filetype="pdf")
                except Exception as fitz_exc:
                    logger.warning(
                        "PyMuPDF failed to open PDF, OCR fallback unavailable",
                        error=str(fitz_exc),
                        file_path=str(file_path),
                    )

                # Determine OCR extractor for fallback pages
                extractor_provider = (
                    (settings.extractor_provider or "third_party").lower().strip()
                )
                hybrid_ocr_extractor = None
                if extractor_provider == "huggingface":
                    try:
                        from .extractors.huggingface import HuggingFaceExtractor

                        hybrid_ocr_extractor = HuggingFaceExtractor()
                    except Exception as exc:
                        logger.warning(
                            "Failed to initialize HuggingFaceExtractor for hybrid OCR, defaulting to Saptiva",
                            error=str(exc),
                        )

                # Process each page with hybrid approach
                for page_idx, page in enumerate(reader.pages):
                    page_num = page_idx + 1

                    try:
                        # Step 1: Try pypdf extraction
                        text = page.extract_text() or ""
                        text_stripped = text.strip()

                        # Step 2: Determine if OCR is needed
                        # ANTI-HALLUCINATION FIX: Check both length AND quality
                        # This prevents using corrupted text from scanned PDFs
                        has_insufficient_length = (
                            len(text_stripped) < MIN_CHARS_THRESHOLD
                        )
                        has_poor_quality = not _is_text_quality_sufficient(
                            text_stripped
                        )

                        needs_ocr = (
                            has_insufficient_length or has_poor_quality
                        ) and fitz_doc is not None

                        if needs_ocr:
                            # Step 3: Apply OCR to this page
                            ocr_reason = []
                            if has_insufficient_length:
                                ocr_reason.append(
                                    f"insufficient text ({len(text_stripped)} < {MIN_CHARS_THRESHOLD})"
                                )
                            if has_poor_quality:
                                valid_ratio = (
                                    sum(
                                        1
                                        for c in text_stripped
                                        if c.isalnum() or c.isspace()
                                    )
                                    / len(text_stripped)
                                    if text_stripped
                                    else 0
                                )
                                ocr_reason.append(
                                    f"poor quality ({valid_ratio:.1%} valid chars)"
                                )

                            logger.debug(
                                "Applying OCR to page with insufficient/poor text",
                                page=page_num,
                                pypdf_chars=len(text_stripped),
                                threshold=MIN_CHARS_THRESHOLD,
                                reason=", ".join(ocr_reason),
                            )

                            ocr_text = await raster_single_page_and_ocr(
                                doc=fitz_doc,
                                page_idx=page_idx,
                                dpi=settings.ocr_raster_dpi,
                                image_extractor=hybrid_ocr_extractor,
                            )

                            # Use OCR text if it's better than pypdf
                            if len(ocr_text.strip()) > len(text_stripped):
                                text_stripped = ocr_text.strip()
                                ocr_count += 1
                                logger.debug(
                                    "OCR text used for page",
                                    page=page_num,
                                    ocr_chars=len(text_stripped),
                                )
                            else:
                                pypdf_count += 1
                                logger.debug(
                                    "pypdf text retained (OCR did not improve)",
                                    page=page_num,
                                )
                        else:
                            pypdf_count += 1

                        # Store page content
                        temp_pages.append(
                            PageContent(
                                page=page_num,
                                text_md=text_stripped
                                or f"[Página {page_num} sin texto extraíble]",
                                has_table=False,
                                has_images=False,
                            )
                        )

                    except Exception as page_exc:
                        error_count += 1
                        logger.warning(
                            "Page extraction failed",
                            page=page_num,
                            error=str(page_exc),
                        )
                        temp_pages.append(
                            PageContent(
                                page=page_num,
                                text_md=f"[Página {page_num} error: {page_exc}]",
                                has_table=False,
                                has_images=False,
                            )
                        )

                # Close PyMuPDF document
                if fitz_doc is not None:
                    fitz_doc.close()

                pages = temp_pages

                logger.info(
                    "Hybrid PDF extraction completed",
                    total_pages=total_pages,
                    pypdf_pages=pypdf_count,
                    ocr_pages=ocr_count,
                    error_pages=error_count,
                    total_chars=sum(len(p.text_md) for p in pages),
                    file_path=str(file_path),
                )

                return pages

            except ImportError:
                # pypdf or PyMuPDF not installed, fall back to extractor pattern
                logger.warning(
                    "pypdf or PyMuPDF not installed, falling back to extractor pattern",
                    file_path=str(file_path),
                )

            except Exception as exc:
                # Hybrid extraction failed, fall back to extractor pattern
                logger.warning(
                    "Hybrid extraction failed, falling back to extractor pattern",
                    error=str(exc),
                    file_path=str(file_path),
                )

        # Standard extraction path (for images and PDF fallback)
        extractor = get_text_extractor()

        logger.info(
            "Starting text extraction",
            media_type=media_type,
            content_type=content_type,
            file_path=str(file_path),
            file_size=len(file_bytes),
            extractor_type=type(extractor).__name__,
        )

        # Extract text using abstraction layer
        extracted_text = await extractor.extract_text(
            media_type=media_type,
            data=file_bytes,
            mime=content_type,
            filename=file_path.name,
        )

        # Convert extracted text to PageContent format
        if media_type == "pdf":
            # PDF: Split by double newlines (page separators from ThirdPartyExtractor)
            page_texts = extracted_text.split("\n\n")
            for page_num, page_text in enumerate(page_texts, start=1):
                text = page_text.strip()
                if not text:
                    text = f"[Página {page_num} sin texto extraíble]"

                pages.append(
                    PageContent(
                        page=page_num,
                        text_md=text,
                        has_table=False,
                    )
                )
        else:  # media_type == "image"
            # Image: Single page with OCR text
            pages.append(
                PageContent(
                    page=1,
                    text_md=extracted_text,
                    has_table=False,
                )
            )

        logger.info(
            "Text extraction successful",
            media_type=media_type,
            pages_extracted=len(pages),
            total_chars=sum(len(p.text_md) for p in pages),
            file_path=str(file_path),
        )

    except UnsupportedFormatError as exc:
        logger.warning(
            "Unsupported format for extraction",
            content_type=content_type,
            error=str(exc),
            file_path=str(file_path),
        )
        pages = [
            PageContent(
                page=1,
                text_md=f"[Formato no soportado: {content_type}]",
                has_table=False,
            )
        ]

    except ExtractionError as exc:
        logger.error(
            "Text extraction failed",
            error=str(exc),
            media_type=getattr(exc, "media_type", None),
            file_path=str(file_path),
            exc_info=True,
        )
        pages = _fallback_mock_pages()

    except Exception as exc:  # pragma: no cover - unexpected errors
        logger.error(
            "Unexpected extraction error",
            error=str(exc),
            file_path=str(file_path),
            exc_info=True,
        )
        pages = _fallback_mock_pages()

    return pages


def _serialize_pages(pages: List[PageContent]) -> List[Dict[str, Any]]:
    serialized: List[Dict[str, Any]] = []
    for page in pages:
        text = page.text_md or ""
        serialized.append(
            {
                "page_number": page.page,
                "text": text,
                "word_count": len(text.split()) if text else 0,
            }
        )
    return serialized


async def extract_text_from_pdf(
    *,
    pdf_path: Path,
    doc_id: Optional[str] = None,
    cache_ttl_seconds: int = 3600,
) -> Dict[str, Any]:
    """
    Backward-compatible helper for MCP tool. Uses the hybrid extraction pipeline
    and returns a dict similar to the legacy implementation.
    """
    pages = await extract_text_from_file(pdf_path, "application/pdf")
    text = "\n\n".join(page.text_md or "" for page in pages)

    return {
        "doc_id": doc_id,
        "text": text,
        "method": "hybrid",
        "pages": _serialize_pages(pages),
        "metadata": {
            "total_pages": len(pages),
            "cache_ttl_seconds": cache_ttl_seconds,
        },
    }


async def extract_text_from_document(**kwargs) -> Dict[str, Any]:
    """
    Legacy alias so existing imports continue working.
    """
    return await extract_text_from_pdf(**kwargs)


def _fallback_mock_pages() -> List[PageContent]:
    return [
        PageContent(
            page=1,
            text_md="# Documento de Prueba\n\nEste es un documento de ejemplo (modo fallback).",
            has_table=False,
        )
    ]
