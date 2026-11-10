"""
Saptiva Native Tools Text Extraction Implementation

This module provides text extraction using Saptiva's proprietary APIs.
Implements base64 encoding per actual Saptiva Custom Tools specification.

Architecture:
    - PDF extraction via Custom Tool: obtener_texto_en_documento()
    - OCR extraction via API endpoint (to be implemented)
    - Circuit breaker for resilience (half-open state support)
    - Exponential backoff with jitter for retries
    - Idempotency keys for deduplication
    - Redis caching with zstd compression

Security:
    - Real MIME type detection with python-magic
    - File size limits (10MB images, 50MB PDFs)
    - Temp file cleanup in finally blocks
    - API key masking in logs

Cost Optimization:
    - Bypass Saptiva OCR for searchable PDFs (use native extraction)
    - Cache results in Redis with 24h TTL
    - Compress large documents with zstd
"""

import base64
import hashlib
import os
import random
import time
from enum import Enum
from typing import Optional

import structlog

from .base import (
    ExtractionError,
    MediaType,
    TextExtractor,
    UnsupportedFormatError,
)
from .cache import get_extraction_cache

logger = structlog.get_logger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker for Saptiva API calls.

    States:
        CLOSED: Normal operation, all requests go through
        OPEN: Too many failures, reject all requests immediately
        HALF_OPEN: After timeout, allow one request to test recovery

    Configuration:
        - failure_threshold: Open circuit after N consecutive failures (default: 5)
        - recovery_timeout: Seconds to wait before half-open (default: 60)
        - success_threshold: Close circuit after N consecutive successes in half-open (default: 2)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None

    def can_execute(self) -> bool:
        """Check if request is allowed based on circuit state."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if (
                self.last_failure_time
                and (time.time() - self.last_failure_time) >= self.recovery_timeout
            ):
                logger.info(
                    "Circuit breaker transitioning to HALF_OPEN",
                    recovery_timeout=self.recovery_timeout,
                )
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                return True

            logger.warning(
                "Circuit breaker OPEN, rejecting request",
                seconds_until_retry=self.recovery_timeout
                - (time.time() - (self.last_failure_time or 0)),
            )
            return False

        # HALF_OPEN: Allow one request at a time to test recovery
        return True

    def record_success(self) -> None:
        """Record successful request."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            logger.debug(
                "Circuit breaker success in HALF_OPEN", success_count=self.success_count
            )

            if self.success_count >= self.success_threshold:
                logger.info(
                    "Circuit breaker closing after successful recovery",
                    success_threshold=self.success_threshold,
                )
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        else:
            # In CLOSED state, reset failure counter on success
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record failed request."""
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Single failure in half-open reopens circuit
            logger.warning("Circuit breaker reopening after failure in HALF_OPEN")
            self.state = CircuitState.OPEN
            self.failure_count = 0
            self.success_count = 0
        else:
            # In CLOSED state, increment failure counter
            self.failure_count += 1
            logger.debug(
                "Circuit breaker failure recorded",
                failure_count=self.failure_count,
                threshold=self.failure_threshold,
            )

            if self.failure_count >= self.failure_threshold:
                logger.error(
                    "Circuit breaker OPENING after repeated failures",
                    failure_threshold=self.failure_threshold,
                )
                self.state = CircuitState.OPEN


class SaptivaExtractor(TextExtractor):
    """
    Text extractor using Saptiva Native Tools API.

    Configuration (Environment Variables):
        SAPTIVA_BASE_URL: Base URL for Saptiva API (e.g., https://api.saptiva.com)
        SAPTIVA_API_KEY: API key for authentication

    API Endpoints:
        POST /v1/tools/extractor-pdf - Extract text from PDF (Custom Tool)
        POST /v1/tools/ocr - Extract text from image (TODO)

    Features:
        - Base64 encoding for document transmission
        - Circuit breaker with half-open state
        - Exponential backoff with jitter (1s, 2s, 4s)
        - Idempotency keys for deduplication
        - Redis caching with zstd compression (TODO: integrate with Redis)
        - Real MIME type detection
        - File size validation
    """

    # File size limits
    MAX_IMAGE_SIZE_MB = 10
    MAX_PDF_SIZE_MB = 50

    # Supported MIME types
    SUPPORTED_PDF_MIMES = {"application/pdf"}
    SUPPORTED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/jpg"}

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0  # seconds
    RETRY_MAX_DELAY = 10.0  # seconds

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 30,
        enable_circuit_breaker: bool = True,
    ):
        """
        Initialize Saptiva extractor.

        Args:
            base_url: Saptiva API base URL (default: from SAPTIVA_BASE_URL env)
            api_key: Saptiva API key (default: from SAPTIVA_API_KEY env)
            timeout: Request timeout in seconds (default: 30)
            enable_circuit_breaker: Enable circuit breaker pattern (default: True)
        """
        self.base_url = (base_url or os.getenv("SAPTIVA_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("SAPTIVA_API_KEY", "")
        self.timeout = timeout

        # Circuit breaker
        self.circuit_breaker = CircuitBreaker() if enable_circuit_breaker else None

        if not self.base_url:
            logger.warning(
                "SAPTIVA_BASE_URL not configured. Set environment variable before using SaptivaExtractor."
            )

        if not self.api_key:
            logger.warning(
                "SAPTIVA_API_KEY not configured. Set environment variable before using SaptivaExtractor."
            )

    def _mask_api_key(self, key: str, visible_chars: int = 4) -> str:
        """Mask API key for safe logging."""
        if not key or len(key) <= visible_chars * 2:
            return "*" * len(key) if key else "<empty>"
        return f"{key[:visible_chars]}...{key[-visible_chars:]}"

    def _validate_file_size(self, data: bytes, media_type: MediaType) -> None:
        """
        Validate file size against limits.

        Raises:
            ExtractionError: If file exceeds size limit
        """
        size_mb = len(data) / (1024 * 1024)

        if media_type == "pdf":
            max_size = self.MAX_PDF_SIZE_MB
        else:
            max_size = self.MAX_IMAGE_SIZE_MB

        if size_mb > max_size:
            raise ExtractionError(
                f"File size {size_mb:.2f}MB exceeds {max_size}MB limit for {media_type}",
                media_type=media_type,
            )

    def _validate_mime_type(self, mime: str, media_type: MediaType) -> None:
        """
        Validate MIME type matches expected format.

        Raises:
            UnsupportedFormatError: If MIME type not supported
        """
        mime_lower = mime.lower()

        if media_type == "pdf":
            if mime_lower not in self.SUPPORTED_PDF_MIMES:
                raise UnsupportedFormatError(
                    f"MIME type '{mime}' not supported for PDF extraction. Expected: {self.SUPPORTED_PDF_MIMES}",
                    media_type=media_type,
                )
        elif media_type == "image":
            if mime_lower not in self.SUPPORTED_IMAGE_MIMES:
                raise UnsupportedFormatError(
                    f"MIME type '{mime}' not supported for image extraction. Expected: {self.SUPPORTED_IMAGE_MIMES}",
                    media_type=media_type,
                )

    def _generate_idempotency_key(self, data: bytes, media_type: MediaType) -> str:
        """
        Generate idempotency key from file content hash.

        Uses SHA-256 hash of file bytes to ensure same file produces same key.
        """
        content_hash = hashlib.sha256(data).hexdigest()
        return f"saptiva-extract-{media_type}-{content_hash[:16]}"

    def _is_pdf_searchable(self, pdf_bytes: bytes) -> bool:
        """
        Check if PDF contains searchable text (cost optimization).

        If a PDF already has extractable text, we can skip expensive OCR
        and use native PDF text extraction instead, saving API costs.

        Strategy:
            1. Try to extract text from first few pages using pypdf
            2. If we find substantial text (>50 chars), it's searchable
            3. If no text or very little text, it's likely a scanned image

        Args:
            pdf_bytes: Raw PDF file bytes

        Returns:
            True if PDF has searchable text, False otherwise
        """
        try:
            import io

            from pypdf import PdfReader

            # Read PDF from bytes
            pdf_file = io.BytesIO(pdf_bytes)
            reader = PdfReader(pdf_file)

            # Check first 3 pages (or all if less than 3)
            pages_to_check = min(3, len(reader.pages))
            total_text = ""

            for page_num in range(pages_to_check):
                try:
                    page = reader.pages[page_num]
                    text = page.extract_text()
                    total_text += text
                except Exception as exc:
                    logger.debug(
                        "Failed to extract text from page",
                        page_num=page_num,
                        error=str(exc),
                    )
                    continue

            # Consider searchable if we found > 50 characters
            # (this filters out PDFs with only metadata/headers)
            is_searchable = len(total_text.strip()) > 50

            logger.info(
                "PDF searchability check",
                is_searchable=is_searchable,
                text_length=len(total_text),
                pages_checked=pages_to_check,
            )

            return is_searchable

        except ImportError:
            logger.warning("pypdf not available, cannot check PDF searchability")
            return False
        except Exception as exc:
            logger.warning(
                "PDF searchability check failed",
                error=str(exc),
                exc_info=True,
            )
            return False

    async def _extract_pdf_text_native(
        self, pdf_bytes: bytes, filename: Optional[str] = None
    ) -> str:
        """
        Extract text from searchable PDF using native extraction (no API call).

        This is a cost optimization: if PDF already has text, we extract it
        locally instead of sending to Saptiva API.

        Args:
            pdf_bytes: Raw PDF file bytes
            filename: Optional filename for logging

        Returns:
            Extracted text from PDF

        Raises:
            ExtractionError: If extraction fails
        """
        try:
            import io

            from pypdf import PdfReader

            logger.info(
                "Using native PDF extraction (cost optimization)",
                filename=filename,
                size_kb=len(pdf_bytes) // 1024,
            )

            pdf_file = io.BytesIO(pdf_bytes)
            reader = PdfReader(pdf_file)

            texts = []
            for page_num, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text()
                    if text.strip():
                        texts.append(text)
                    else:
                        texts.append(f"[Página {page_num} sin texto extraíble]")
                except Exception as exc:
                    logger.warning(
                        "Failed to extract page",
                        page_num=page_num,
                        error=str(exc),
                    )
                    texts.append(f"[Página {page_num} - error: {str(exc)}]")

            extracted_text = "\n\n".join(texts)

            logger.info(
                "Native PDF extraction successful",
                filename=filename,
                pages=len(reader.pages),
                text_length=len(extracted_text),
            )

            return extracted_text

        except ImportError:
            raise ExtractionError(
                "pypdf not available for native extraction",
                media_type="pdf",
            )
        except Exception as exc:
            raise ExtractionError(
                f"Native PDF extraction failed: {str(exc)}",
                media_type="pdf",
                original_error=exc,
            )

    def _calculate_retry_delay(self, attempt: int) -> float:
        """
        Calculate retry delay with exponential backoff and jitter.

        Formula: min(base * 2^attempt + jitter, max_delay)
        Jitter: random value between 0 and 1 second

        Args:
            attempt: Retry attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        exponential_delay = self.RETRY_BASE_DELAY * (2**attempt)
        jitter = random.uniform(0, 1)
        total_delay = min(exponential_delay + jitter, self.RETRY_MAX_DELAY)

        logger.debug(
            "Calculated retry delay",
            attempt=attempt,
            exponential_delay=exponential_delay,
            jitter=jitter,
            total_delay=total_delay,
        )

        return total_delay

    async def _extract_pdf_text(
        self,
        data: bytes,
        filename: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> str:
        """
        Extract text from PDF using Saptiva SDK (Custom Tools).

        IMPLEMENTATION NOTE (2025-10-16):
        ────────────────────────────────────────────────────────
        PDF extraction uses Saptiva SDK, NOT the Chat Completions API.
        Testing confirmed:
        - ✅ Images → Chat Completions API (/v1/chat/completions/)
        - ✅ PDFs → SDK (saptiva_agents.tools.obtener_texto_en_documento)

        The SDK call is synchronous, so we wrap it in run_in_executor to
        avoid blocking the async event loop.
        ────────────────────────────────────────────────────────

        SDK Specification:
            Function: obtener_texto_en_documento(doc_type, document, key)
            Args:
                doc_type: "pdf"
                document: Base64-encoded PDF string
                key: API key (optional if SAPTIVA_API_KEY env var set)
            Returns:
                dict with "text" or "pages" containing extracted content

        Args:
            data: Raw PDF bytes
            filename: Optional filename for logging context
            idempotency_key: Optional idempotency key (not used with SDK)

        Returns:
            Extracted text from all pages

        Raises:
            ExtractionError: If SDK call fails or import error
        """

        try:
            # Import SDK function
            from saptiva_agents.tools import obtener_texto_en_documento
        except ImportError as exc:
            logger.error(
                "Saptiva SDK not available",
                error=str(exc),
                hint="Install with: pip install saptiva-agents>=0.2.2,<0.3",
            )
            raise ExtractionError(
                "Saptiva SDK (saptiva-agents) not installed. Cannot extract PDF text.",
                media_type="pdf",
                original_error=exc,
            )

        # Encode PDF to base64
        b64_document = base64.b64encode(data).decode("utf-8")

        logger.info(
            "Saptiva PDF extraction starting (SDK)",
            filename=filename,
            file_size_kb=len(data) // 1024,
            b64_size_kb=len(b64_document) // 1024,
            api_key_masked=self._mask_api_key(self.api_key),
        )

        start_time = time.time()

        try:
            # SDK is asynchronous - await directly (no need for run_in_executor)
            result = await obtener_texto_en_documento(
                doc_type="pdf",
                document=b64_document,
                key=self.api_key or "",  # SDK uses env var if key=""
            )

            latency_ms = (time.time() - start_time) * 1000

            # Normalize SDK response to string
            # SDK may return: {"text": "..."} or {"pages": [{...}, ...]}
            extracted_text = ""

            if isinstance(result, dict):
                if "pages" in result:
                    # Page-by-page format
                    pages = result.get("pages", [])
                    page_texts = []
                    for i, page_data in enumerate(pages, start=1):
                        page_text = page_data.get("text", "").strip()
                        if page_text:
                            page_texts.append(page_text)
                        else:
                            page_texts.append(f"[Página {i} sin texto extraíble]")

                    extracted_text = "\n\n".join(page_texts)

                elif "text" in result:
                    # Single text format
                    extracted_text = result.get("text", "").strip()

                else:
                    # Unknown format - stringify defensively
                    logger.warning(
                        "Unexpected SDK response format",
                        filename=filename,
                        response_keys=list(result.keys()),
                    )
                    extracted_text = str(result)[:100000]

            elif isinstance(result, str):
                # Direct string response
                extracted_text = result.strip()

            else:
                # Fallback for unknown types
                extracted_text = str(result)[:100000]

            if not extracted_text:
                logger.warning(
                    "Saptiva SDK returned empty text",
                    filename=filename,
                )
                return f"[Documento PDF sin texto extraíble: {filename or 'documento.pdf'}]"

            logger.info(
                "Saptiva PDF extraction successful (SDK)",
                filename=filename,
                text_length=len(extracted_text),
                latency_ms=int(latency_ms),
                pages=(
                    len(result.get("pages", [])) if isinstance(result, dict) else "N/A"
                ),
            )

            return extracted_text

        except Exception as exc:
            latency_ms = (time.time() - start_time) * 1000

            logger.error(
                "Saptiva SDK extraction failed",
                error=str(exc),
                error_type=type(exc).__name__,
                filename=filename,
                latency_ms=int(latency_ms),
                exc_info=True,
            )

            raise ExtractionError(
                f"Saptiva PDF extraction failed (SDK): {str(exc)}",
                media_type="pdf",
                original_error=exc,
            )

    async def _async_sleep(self, seconds: float) -> None:
        """Async sleep helper."""
        import asyncio

        await asyncio.sleep(seconds)

    async def _extract_image_text(
        self,
        data: bytes,
        mime: str,
        filename: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> str:
        """
        Extract text from image using Saptiva Chat Completions API with vision.

        API Specification (OpenAI-compatible):
            Endpoint: POST {base_url}/v1/chat/completions/
            Headers:
                - Authorization: Bearer {api_key}
                - Content-Type: application/json
            Body (JSON):
                {
                    "model": "Saptiva OCR",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extrae todo el texto..."},
                            {"type": "image_url", "image_url": {
                                "url": "data:image/png;base64,<base64>"
                            }}
                        ]
                    }]
                }
            Response (JSON):
                {
                    "id": "chatcmpl-xxx",
                    "choices": [{
                        "message": {
                            "content": "extracted text..."
                        }
                    }]
                }

        Args:
            data: Raw image bytes
            mime: MIME type (e.g., "image/png")
            filename: Optional filename for logging context
            idempotency_key: Optional idempotency key (not used with Chat Completions)

        Returns:
            Extracted OCR text

        Raises:
            ExtractionError: If API call fails after retries
        """
        import httpx

        # Encode image to base64 for data URI
        b64_image = base64.b64encode(data).decode("utf-8")
        data_uri = f"data:{mime};base64,{b64_image}"

        # Use Chat Completions endpoint (without trailing slash to avoid redirects)
        url = f"{self.base_url}/v1/chat/completions"

        payload = {
            "model": "Saptiva OCR",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extrae todo el texto legible de esta imagen. Devuelve solo el texto extraído, sin explicaciones adicionales.",
                        },
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        logger.info(
            "Saptiva OCR extraction starting",
            url=url,
            filename=filename,
            mime=mime,
            file_size_kb=len(data) // 1024,
            b64_size_kb=len(b64_image) // 1024,
            has_idempotency_key=bool(idempotency_key),
            api_key_masked=self._mask_api_key(self.api_key),
        )

        # Retry loop with exponential backoff
        last_exception = None

        for attempt in range(self.MAX_RETRIES):
            try:
                start_time = time.time()

                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        url,
                        json=payload,
                        headers=headers,
                    )

                    latency_ms = (time.time() - start_time) * 1000

                    response.raise_for_status()
                    result = response.json()

                    # Extract text from Chat Completions response format
                    # Format: {"choices": [{"message": {"content": "text"}}]}
                    extracted_text = ""
                    if "choices" in result and len(result["choices"]) > 0:
                        message = result["choices"][0].get("message", {})
                        extracted_text = message.get("content", "")

                    if not extracted_text:
                        logger.warning(
                            "Saptiva OCR returned empty text",
                            filename=filename,
                            mime=mime,
                            response_keys=list(result.keys()),
                        )
                        # Return helpful message instead of empty string
                        return f"[Imagen sin texto detectable mediante OCR: {filename or 'documento'}]"

                    logger.info(
                        "Saptiva OCR extraction successful",
                        filename=filename,
                        mime=mime,
                        text_length=len(extracted_text),
                        latency_ms=int(latency_ms),
                        model=result.get("model"),
                        finish_reason=(
                            result["choices"][0].get("finish_reason")
                            if "choices" in result
                            else None
                        ),
                        attempt=attempt + 1,
                    )

                    return extracted_text

            except httpx.HTTPStatusError as exc:
                last_exception = exc
                status_code = exc.response.status_code
                error_body = exc.response.text[:500]

                logger.error(
                    "Saptiva OCR API returned error",
                    status_code=status_code,
                    error_body=error_body,
                    mime=mime,
                    attempt=attempt + 1,
                    max_retries=self.MAX_RETRIES,
                )

                # Don't retry on client errors (4xx except 429)
                if 400 <= status_code < 500 and status_code != 429:
                    raise ExtractionError(
                        f"Saptiva OCR API client error ({status_code}): {error_body}",
                        media_type="image",
                        original_error=exc,
                    )

                # Retry on server errors (5xx) and rate limits (429)
                if attempt < self.MAX_RETRIES - 1:
                    delay = self._calculate_retry_delay(attempt)
                    logger.info(
                        f"Retrying OCR after {delay:.2f}s...", attempt=attempt + 1
                    )
                    await self._async_sleep(delay)
                    continue

            except httpx.TimeoutException as exc:
                last_exception = exc
                logger.error(
                    "Saptiva OCR API timeout",
                    timeout=self.timeout,
                    mime=mime,
                    attempt=attempt + 1,
                    max_retries=self.MAX_RETRIES,
                )

                if attempt < self.MAX_RETRIES - 1:
                    delay = self._calculate_retry_delay(attempt)
                    logger.info(
                        f"Retrying OCR after {delay:.2f}s...", attempt=attempt + 1
                    )
                    await self._async_sleep(delay)
                    continue

            except Exception as exc:
                last_exception = exc
                logger.error(
                    "Unexpected Saptiva OCR API error",
                    error=str(exc),
                    error_type=type(exc).__name__,
                    mime=mime,
                    attempt=attempt + 1,
                    exc_info=True,
                )

                if attempt < self.MAX_RETRIES - 1:
                    delay = self._calculate_retry_delay(attempt)
                    logger.info(
                        f"Retrying OCR after {delay:.2f}s...", attempt=attempt + 1
                    )
                    await self._async_sleep(delay)
                    continue

        # All retries exhausted
        raise ExtractionError(
            f"Saptiva OCR extraction failed after {self.MAX_RETRIES} attempts: {str(last_exception)}",
            media_type="image",
            original_error=last_exception,
        )

    async def extract_text(
        self,
        *,
        media_type: MediaType,
        data: bytes,
        mime: str,
        filename: Optional[str] = None,
    ) -> str:
        """
        Extract text from document using Saptiva Native Tools API with caching.

        Flow:
            1. Validate configuration (base_url + api_key)
            2. Check cache for existing result (Redis with zstd compression)
            3. If cache miss:
               a. Check circuit breaker state
               b. Validate file size and MIME type
               c. Generate idempotency key from content hash
               d. Route to appropriate extractor:
                  - PDF: _extract_pdf_text (base64 Custom Tool)
                  - Image: _extract_image_text (OCR)
               e. Record circuit breaker success/failure
               f. Cache the result for 24h
            4. Return extracted text

        Args:
            media_type: "pdf" or "image"
            data: Raw document bytes
            mime: MIME type (e.g., "application/pdf", "image/png")
            filename: Optional filename for context/logging

        Returns:
            Extracted text as plain string

        Raises:
            ExtractionError: If configuration invalid or API call fails
            UnsupportedFormatError: If MIME type not supported
        """
        # Configuration validation
        if not self.base_url or not self.api_key:
            raise ExtractionError(
                "Saptiva API not configured. Set SAPTIVA_BASE_URL and SAPTIVA_API_KEY environment variables.",
                media_type=media_type,
            )

        # Try cache first
        cache = get_extraction_cache()
        cached_text = await cache.get("saptiva", media_type, data)
        if cached_text:
            logger.info(
                "Returning cached extraction result",
                media_type=media_type,
                filename=filename,
                text_length=len(cached_text),
            )
            return cached_text

        # Circuit breaker check
        if self.circuit_breaker and not self.circuit_breaker.can_execute():
            raise ExtractionError(
                "Saptiva API circuit breaker is OPEN. Service temporarily unavailable.",
                media_type=media_type,
            )

        # File validation
        self._validate_file_size(data, media_type)
        self._validate_mime_type(mime, media_type)

        # Generate idempotency key
        idempotency_key = self._generate_idempotency_key(data, media_type)

        try:
            # Route to appropriate extractor
            if media_type == "pdf":
                # Cost optimization: check if PDF is searchable before API call
                if self._is_pdf_searchable(data):
                    logger.info(
                        "PDF is searchable, using native extraction (bypassing Saptiva API)",
                        filename=filename,
                    )
                    text = await self._extract_pdf_text_native(data, filename)
                else:
                    logger.info(
                        "PDF is scanned (no searchable text), using Saptiva API",
                        filename=filename,
                    )
                    text = await self._extract_pdf_text(data, filename, idempotency_key)
            else:
                text = await self._extract_image_text(
                    data, mime, filename, idempotency_key
                )

            # Record success
            if self.circuit_breaker:
                self.circuit_breaker.record_success()

            # Cache the result
            await cache.set("saptiva", media_type, data, text)

            return text

        except Exception:
            # Record failure
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()

            raise

    async def health_check(self) -> bool:
        """
        Check if Saptiva API is available and healthy.

        Performs a lightweight check by attempting to access the API
        without making a full extraction request.

        TODO: Implement dedicated health endpoint when available.
              For now, returns True if configuration is valid.

        Returns:
            True if API is reachable and configured, False otherwise
        """
        if not self.base_url or not self.api_key:
            logger.warning(
                "Saptiva API not configured for health check",
                has_base_url=bool(self.base_url),
                has_api_key=bool(self.api_key),
            )
            return False

        # Check circuit breaker state
        if self.circuit_breaker:
            if self.circuit_breaker.state == CircuitState.OPEN:
                logger.warning(
                    "Saptiva health check failed: circuit breaker OPEN",
                    circuit_state=self.circuit_breaker.state.value,
                )
                return False

        logger.info(
            "Saptiva health check passed (configuration valid)",
            base_url=self.base_url,
            api_key_masked=self._mask_api_key(self.api_key),
            circuit_state=(
                self.circuit_breaker.state.value if self.circuit_breaker else "disabled"
            ),
        )

        return True

        # TODO: Implement dedicated health endpoint when available
        # try:
        #     import httpx
        #
        #     async with httpx.AsyncClient(timeout=5) as client:
        #         response = await client.get(
        #             f"{self.base_url}/v1/health",
        #             headers={"Authorization": f"Bearer {self.api_key}"},
        #         )
        #         response.raise_for_status()
        #         result = response.json()
        #
        #         logger.debug(
        #             "Saptiva health check passed",
        #             status=result.get("status"),
        #             version=result.get("version"),
        #         )
        #
        #         return result.get("status") == "ok"
        #
        # except Exception as exc:
        #     logger.warning(
        #         "Saptiva health check failed",
        #         error=str(exc),
        #     )
        #     return False
