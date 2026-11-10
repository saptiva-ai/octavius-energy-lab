"""
PDF Rasterization + OCR Fallback for Image-Only PDFs

This module provides text extraction for scanned/image-only PDFs that cannot
be processed with pypdf's text extraction.

Strategy:
    1. Rasterize each page with PyMuPDF (fitz) at configurable DPI
    2. Convert raster images to PNG format
    3. Send each PNG to configured OCR extractor (default: Saptiva)
    4. Return List[PageContent] maintaining existing format

Configuration (via Settings):
    - MAX_OCR_PAGES: Maximum pages to OCR (default: 30)
    - OCR_RASTER_DPI: Rasterization DPI (default: 180, range: 150-200)

Cost/Latency Optimization:
    - Limit pages processed via MAX_OCR_PAGES
    - Retry with exponential backoff (max 3 attempts per page)
    - Log detailed metrics (page processing time, text length)
    - Truncate with clear marker when hitting page limit

Example:
    from apps.api.src.services.extractors.pdf_raster_ocr import raster_pdf_then_ocr_pages

    pdf_bytes = Path("scanned.pdf").read_bytes()
    pages = await raster_pdf_then_ocr_pages(pdf_bytes)
    for page in pages:
        print(f"Page {page.page}: {page.text_md[:100]}...")
"""

from __future__ import annotations

import asyncio
import time
from io import BytesIO
from typing import TYPE_CHECKING, List

import structlog
from PIL import Image

# Lazy import: fitz (PyMuPDF) imported inside functions to allow backend to start
# without this heavy dependency when extraction is delegated to file-manager.
if TYPE_CHECKING:
    import fitz

from ...core.config import get_settings
from ...models.document import PageContent
from .base import TextExtractor
from .saptiva import SaptivaExtractor

logger = structlog.get_logger(__name__)


async def raster_pdf_then_ocr_pages(
    pdf_bytes: bytes, image_extractor: TextExtractor | None = None
) -> List[PageContent]:
    """
    Rasterize PDF pages and extract text via OCR.

    This function is called when pypdf extraction yields insufficient text
    (< 10% of pages have extractable content), indicating an image-only/scanned PDF.

    Process:
        1. Open PDF with PyMuPDF (fitz)
        2. Determine page limit (min(total_pages, MAX_OCR_PAGES))
        3. For each page within limit:
           a. Rasterize at OCR_RASTER_DPI
           b. Convert to PNG bytes
           c. Send to configured OCR extractor (default: Saptiva)
           d. Retry up to 3 times with exponential backoff
           e. Create PageContent with extracted text
        4. If PDF has more pages than limit, append truncation marker

    Args:
        pdf_bytes: Raw PDF file bytes
        image_extractor: Optional TextExtractor to OCR rasterized pages.
            Defaults to SaptivaExtractor for backwards compatibility.

    Returns:
        List of PageContent objects, one per processed page
        If truncated: Last PageContent contains truncation notice

    Raises:
        Exception: Propagates fitz exceptions if PDF cannot be opened

    Example:
        >>> pdf_bytes = Path("scan.pdf").read_bytes()
        >>> pages = await raster_pdf_then_ocr_pages(pdf_bytes)
        >>> assert len(pages) <= settings.max_ocr_pages + 1  # +1 for truncation marker
    """
    import fitz  # PyMuPDF - lazy import

    settings = get_settings()
    max_pages = settings.max_ocr_pages
    dpi = settings.ocr_raster_dpi

    # Open PDF with PyMuPDF
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        logger.error(
            "Failed to open PDF with PyMuPDF",
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise

    total_pages = len(doc)
    pages_to_process = min(total_pages, max_pages)

    logger.info(
        "PDF OCR rasterization started",
        total_pages=total_pages,
        pages_to_process=pages_to_process,
        max_ocr_pages=max_pages,
        dpi=dpi,
        truncated=total_pages > max_pages,
    )

    # Initialize OCR extractor
    ocr_extractor = image_extractor or SaptivaExtractor()
    pages: List[PageContent] = []

    # Process each page
    for page_idx in range(pages_to_process):
        page_start_time = time.time()

        try:
            # Load and rasterize page
            page = doc.load_page(page_idx)
            pix = page.get_pixmap(dpi=dpi)

            # Convert to PIL Image
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            # Convert to JPEG bytes with compression (much smaller than PNG)
            # JPEG at 85% quality is ~5-10x smaller than PNG while maintaining OCR accuracy
            img_buffer = BytesIO()
            img.save(img_buffer, format="JPEG", quality=85, optimize=True)
            png_bytes = img_buffer.getvalue()

            logger.debug(
                "Page rasterized",
                page=page_idx + 1,
                width=pix.width,
                height=pix.height,
                jpeg_size_kb=len(png_bytes) // 1024,
            )

            # OCR with retries
            extracted_text = ""
            for attempt in range(3):
                try:
                    extracted_text = await ocr_extractor.extract_text(
                        media_type="image",
                        data=png_bytes,
                        mime="image/jpeg",
                        filename=f"page_{page_idx + 1}.jpg",
                    )
                    break  # Success

                except Exception as exc:
                    if attempt == 2:  # Last attempt failed
                        logger.error(
                            "OCR failed after 3 attempts",
                            page=page_idx + 1,
                            error=str(exc),
                            error_type=type(exc).__name__,
                        )
                        extracted_text = f"[Página {page_idx + 1} - OCR fallido: {type(exc).__name__}]"
                    else:
                        # Retry with exponential backoff
                        delay = 0.7 * (attempt + 1)
                        logger.warning(
                            "OCR attempt failed, retrying",
                            page=page_idx + 1,
                            attempt=attempt + 1,
                            retry_in_seconds=delay,
                            error=str(exc),
                        )
                        await asyncio.sleep(delay)

            # Clean up text
            final_text = (extracted_text or "").strip()
            if not final_text:
                final_text = f"[Página {page_idx + 1} sin texto detectable]"

            # Create PageContent
            pages.append(
                PageContent(
                    page=page_idx + 1,
                    text_md=final_text,
                    has_table=False,
                    has_images=False,
                )
            )

            # Log metrics
            page_duration = time.time() - page_start_time
            logger.info(
                "Page OCR completed",
                page=page_idx + 1,
                text_length=len(final_text),
                duration_seconds=round(page_duration, 2),
                chars_per_second=(
                    int(len(final_text) / page_duration) if page_duration > 0 else 0
                ),
            )

        except Exception as exc:
            logger.error(
                "Unexpected error processing page",
                page=page_idx + 1,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            # Add error page
            pages.append(
                PageContent(
                    page=page_idx + 1,
                    text_md=f"[Error procesando página {page_idx + 1}: {type(exc).__name__}]",
                    has_table=False,
                    has_images=False,
                )
            )

    # Add truncation marker if needed
    if total_pages > max_pages:
        pages.append(
            PageContent(
                page=max_pages + 1,
                text_md=f"[⚠️  Documento truncado: OCR aplicado solo a las primeras {max_pages} páginas. "
                f"Total de páginas: {total_pages}. Para procesar más páginas, ajustar MAX_OCR_PAGES.]",
                has_table=False,
                has_images=False,
            )
        )
        logger.warning(
            "PDF truncated due to MAX_OCR_PAGES limit",
            total_pages=total_pages,
            processed_pages=max_pages,
            skipped_pages=total_pages - max_pages,
        )

    logger.info(
        "PDF OCR rasterization completed",
        total_pages=total_pages,
        pages_processed=len(pages)
        - (1 if total_pages > max_pages else 0),  # Exclude truncation marker
        pages_returned=len(pages),
        total_chars=sum(len(p.text_md) for p in pages),
        truncated=total_pages > max_pages,
    )

    return pages


async def raster_single_page_and_ocr(
    doc: fitz.Document,
    page_idx: int,
    dpi: int = 180,
    image_extractor: TextExtractor | None = None,
) -> str:
    """
    Rasterize a single PDF page and extract text via OCR.

    This function is used by hybrid extraction when pypdf yields insufficient text
    for a specific page in an otherwise searchable PDF.

    Args:
        doc: Opened PyMuPDF document (fitz.Document)
        page_idx: Zero-based page index to process
        dpi: Rasterization DPI (default: 180)
        image_extractor: Optional TextExtractor used for OCR. Defaults to
            SaptivaExtractor if not provided.

    Returns:
        Extracted text from OCR, or error message if all retries fail

    Example:
        >>> doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        >>> text = await raster_single_page_and_ocr(doc, page_idx=5)
        >>> print(f"OCR text: {text[:100]}...")
    """
    page_start_time = time.time()
    ocr_extractor = image_extractor or SaptivaExtractor()

    try:
        # Load and rasterize page
        page = doc.load_page(page_idx)
        pix = page.get_pixmap(dpi=dpi)

        # Convert to PIL Image
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        # Convert to JPEG bytes with compression (much smaller than PNG)
        # JPEG at 85% quality is ~5-10x smaller than PNG while maintaining OCR accuracy
        img_buffer = BytesIO()
        img.save(img_buffer, format="JPEG", quality=85, optimize=True)
        png_bytes = img_buffer.getvalue()

        logger.debug(
            "Single page rasterized for OCR",
            page=page_idx + 1,
            width=pix.width,
            height=pix.height,
            jpeg_size_kb=len(png_bytes) // 1024,
        )

        # OCR with retries
        extracted_text = ""
        for attempt in range(3):
            try:
                extracted_text = await ocr_extractor.extract_text(
                    media_type="image",
                    data=png_bytes,
                    mime="image/jpeg",
                    filename=f"page_{page_idx + 1}.jpg",
                )
                break  # Success

            except Exception as exc:
                if attempt == 2:  # Last attempt failed
                    logger.error(
                        "Single page OCR failed after 3 attempts",
                        page=page_idx + 1,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
                    extracted_text = (
                        f"[Página {page_idx + 1} - OCR fallido: {type(exc).__name__}]"
                    )
                else:
                    # Retry with exponential backoff
                    delay = 0.7 * (attempt + 1)
                    logger.warning(
                        "Single page OCR attempt failed, retrying",
                        page=page_idx + 1,
                        attempt=attempt + 1,
                        retry_in_seconds=delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)

        # Clean up text
        final_text = (extracted_text or "").strip()
        if not final_text:
            final_text = f"[Página {page_idx + 1} sin texto detectable]"

        # Log metrics
        page_duration = time.time() - page_start_time
        logger.info(
            "Single page OCR completed",
            page=page_idx + 1,
            text_length=len(final_text),
            duration_seconds=round(page_duration, 2),
            chars_per_second=(
                int(len(final_text) / page_duration) if page_duration > 0 else 0
            ),
        )

        return final_text

    except Exception as exc:
        logger.error(
            "Unexpected error processing single page OCR",
            page=page_idx + 1,
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return f"[Error procesando página {page_idx + 1}: {type(exc).__name__}]"
