"""
Hugging Face (DeepSeek) OCR Text Extraction

Integrates with Hugging Face Spaces (e.g., DeepSeek OCR) to extract text from
PDFs and images. Implements the same TextExtractor interface used by other
providers, allowing seamless swapping via EXTRACTOR_PROVIDER.
"""

from __future__ import annotations

import asyncio
import math
from io import BytesIO
from typing import List, Literal, Optional

import httpx
import structlog
from PIL import Image

from ...core.config import get_settings
from .base import ExtractionError, MediaType, TextExtractor, UnsupportedFormatError
from .cache import get_extraction_cache

logger = structlog.get_logger(__name__)

# Lazy import for PyMuPDF - not available in all environments
fitz = None


def _get_fitz():
    """Lazy import of PyMuPDF (fitz) module."""
    global fitz
    if fitz is None:
        try:
            import fitz as _fitz

            fitz = _fitz
        except ImportError:
            raise ImportError(
                "PyMuPDF (fitz) is required for HuggingFaceExtractor. "
                "Install with: pip install pymupdf"
            )
    return fitz


class HuggingFaceExtractor(TextExtractor):
    """Text extractor backed by Hugging Face OCR endpoints (DeepSeek compatible)."""

    SUPPORTED_PDF_MIMES = {"application/pdf"}
    SUPPORTED_IMAGE_MIMES = {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/heic",
        "image/heif",
        "image/gif",
    }

    def __init__(self) -> None:
        settings = get_settings()

        self.endpoint = (settings.huggingface_ocr_endpoint or "").strip()
        self.token = (settings.huggingface_ocr_token or "").strip()
        self.timeout = max(float(settings.huggingface_ocr_timeout or 45.0), 5.0)
        self.max_retries = max(int(settings.huggingface_ocr_max_retries or 3), 1)
        self.prompt_mode = (settings.huggingface_ocr_prompt_mode or "auto").lower()
        self.prompt_plain = (
            settings.huggingface_ocr_prompt_plain or "<image>\\nFree OCR."
        )
        self.prompt_markdown = (
            settings.huggingface_ocr_prompt_markdown or "<image>\\nConvert to markdown."
        )
        self.max_pages = settings.max_ocr_pages
        self.dpi = settings.ocr_raster_dpi

        if self.endpoint.endswith("/"):
            self.endpoint = self.endpoint[:-1]

        if not self.endpoint:
            logger.warning("HuggingFaceExtractor initialized without endpoint")

    async def extract_text(
        self,
        *,
        media_type: MediaType,
        data: bytes,
        mime: str,
        filename: Optional[str] = None,
    ) -> str:
        if not self.endpoint or not self.token:
            raise ExtractionError(
                "Hugging Face OCR not configured. Set HF_OCR_ENDPOINT and HF_TOKEN.",
                media_type=media_type,
            )

        self._validate_mime_type(media_type, mime)

        cache = get_extraction_cache()
        cached_text = await cache.get("huggingface", media_type, data)
        if cached_text:
            logger.info(
                "huggingface_cache_hit",
                media_type=media_type,
                filename=filename,
                length=len(cached_text),
            )
            return cached_text

        try:
            if media_type == "pdf":
                text = await self._extract_pdf_text(data, filename)
            else:
                text = await self._extract_image_text(data, mime, filename)
        except Exception as exc:
            raise ExtractionError(
                f"Failed to extract text via Hugging Face OCR: {exc}",
                media_type=media_type,
                original_error=exc if isinstance(exc, Exception) else None,
            ) from exc

        await cache.set("huggingface", media_type, data, text)
        return text

    async def health_check(self) -> bool:
        if not self.endpoint or not self.token:
            logger.warning(
                "Hugging Face OCR health check failed: missing configuration",
                has_endpoint=bool(self.endpoint),
                has_token=bool(self.token),
            )
            return False

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Lightweight HEAD isn't supported by all Spaces; use GET with minimal payload.
                response = await client.get(
                    self.endpoint,
                    params={"ping": "true"},
                    headers=self._build_auth_headers(),
                )
                response.raise_for_status()
            return True
        except Exception as exc:
            logger.warning(
                "Hugging Face OCR health check request failed",
                error=str(exc),
                endpoint=self.endpoint,
            )
            return False

    async def _extract_pdf_text(self, data: bytes, filename: Optional[str]) -> str:
        try:
            document = _get_fitz().open(stream=data, filetype="pdf")
        except Exception as exc:
            raise UnsupportedFormatError(
                f"No se pudo abrir el PDF para OCR: {exc}",
                media_type="pdf",
                original_error=exc,
            )

        try:
            total_pages = len(document)
            pages_to_process = min(total_pages, self.max_pages)
            logger.info(
                "huggingface_pdf_ocr_start",
                filename=filename,
                total_pages=total_pages,
                pages_to_process=pages_to_process,
                dpi=self.dpi,
            )

            page_texts: List[str] = []
            for index in range(pages_to_process):
                page = document.load_page(index)
                pixmap = page.get_pixmap(dpi=self.dpi)
                image = Image.frombytes(
                    "RGB", [pixmap.width, pixmap.height], pixmap.samples
                )

                buffer = BytesIO()
                image.save(buffer, format="JPEG", quality=85, optimize=True)
                jpeg_bytes = buffer.getvalue()

                prompt = self._select_prompt(media_type="pdf")
                text = await self._call_ocr_api(
                    jpeg_bytes,
                    prompt,
                    f"{filename or 'document'}_page_{index + 1}.jpg",
                )
                cleaned = text.strip() or f"[Página {index + 1} sin texto detectable]"
                page_texts.append(cleaned)

            if total_pages > pages_to_process:
                page_texts.append(
                    f"[Documento truncado: se procesaron {pages_to_process} de {total_pages} páginas debido al límite MAX_OCR_PAGES={self.max_pages}]"
                )

            return "\n\n".join(page_texts)

        finally:
            document.close()

    async def _extract_image_text(
        self, data: bytes, mime: str, filename: Optional[str]
    ) -> str:
        prompt = self._select_prompt(media_type="image")
        text = await self._call_ocr_api(data, prompt, filename or "image")
        cleaned = text.strip()
        if not cleaned:
            cleaned = "[Imagen sin texto detectable]"
        return cleaned

    async def _call_ocr_api(self, data: bytes, prompt: str, filename: str) -> str:
        headers = self._build_auth_headers()

        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self.endpoint,
                        headers=headers,
                        data={"prompt": prompt},
                        files={"file": (filename, data, "image/jpeg")},
                    )
                    response.raise_for_status()

                payload = response.json()
                generated = payload.get("generated_text") or payload.get("data") or ""

                if not generated:
                    logger.warning(
                        "huggingface_empty_response",
                        attempt=attempt,
                        endpoint=self.endpoint,
                        filename=filename,
                    )
                    if attempt == self.max_retries:
                        return "[OCR vacío - no se detectó texto]"
                    await asyncio.sleep(self._backoff(attempt))
                    continue

                return generated

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                is_retryable = status >= 500 or status in (408, 429)
                logger.warning(
                    "huggingface_http_error",
                    status=status,
                    attempt=attempt,
                    retryable=is_retryable,
                    error=str(exc),
                )
                if not is_retryable or attempt == self.max_retries:
                    raise
                await asyncio.sleep(self._backoff(attempt))

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                logger.warning(
                    "huggingface_transport_error",
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt == self.max_retries:
                    raise
                await asyncio.sleep(self._backoff(attempt))

        raise ExtractionError(
            "Hugging Face OCR agotó los reintentos", media_type="image"
        )

    def _build_auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _select_prompt(self, media_type: Literal["pdf", "image"]) -> str:
        if self.prompt_mode == "plain":
            return self.prompt_plain
        if self.prompt_mode == "markdown":
            return self.prompt_markdown
        # auto mode: prefer markdown for PDFs
        return self.prompt_markdown if media_type == "pdf" else self.prompt_plain

    def _validate_mime_type(self, media_type: MediaType, mime: str) -> None:
        mime_lower = mime.lower()
        if media_type == "pdf" and mime_lower not in self.SUPPORTED_PDF_MIMES:
            raise UnsupportedFormatError(
                f"MIME type '{mime}' no soportado para PDF.",
                media_type=media_type,
            )
        if media_type == "image" and mime_lower not in self.SUPPORTED_IMAGE_MIMES:
            raise UnsupportedFormatError(
                f"MIME type '{mime}' no soportado para imágenes.",
                media_type=media_type,
            )

    def _backoff(self, attempt: int) -> float:
        base = 0.8
        return round(base * math.pow(2, attempt - 1), 2)
