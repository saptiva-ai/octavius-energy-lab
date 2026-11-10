"""
Text Extraction Abstraction Layer

This module defines the abstract interface for text extraction from documents
(PDFs and images). Implementations can use different backends:
- ThirdPartyExtractor: Uses pypdf + pytesseract (current)
- SaptivaExtractor: Uses Saptiva Native Tools API (future)

The abstraction allows switching extraction providers via EXTRACTOR_PROVIDER env var
without changing application logic.
"""

from abc import ABC, abstractmethod
from typing import Literal, Optional

# Media type constants
MediaType = Literal["pdf", "image"]


class TextExtractor(ABC):
    """
    Abstract base class for document text extraction.

    All implementations must support:
    - PDF text extraction
    - Image OCR (Optical Character Recognition)
    - Async execution
    - Consistent output format (plain text string)
    """

    @abstractmethod
    async def extract_text(
        self,
        *,
        media_type: MediaType,
        data: bytes,
        mime: str,
        filename: Optional[str] = None,
    ) -> str:
        """
        Extract text from document bytes.

        Args:
            media_type: Type of document ("pdf" or "image")
            data: Raw document bytes
            mime: MIME type (e.g., "application/pdf", "image/png")
            filename: Optional filename for context/logging

        Returns:
            Extracted text as plain string. May be empty if no text found.

        Raises:
            ValueError: If media_type or mime is unsupported
            Exception: If extraction fails (implementation-specific)

        Implementation Notes:
            - Must handle empty/malformed documents gracefully
            - Should not log or persist raw document bytes (security)
            - Timeout should be reasonable (< 30s per document)
            - Language detection/selection is implementation-specific
        """
        raise NotImplementedError("Subclasses must implement extract_text()")

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if extraction backend is available and healthy.

        Returns:
            True if backend is operational, False otherwise

        Example:
            - ThirdPartyExtractor: Check if Tesseract is installed
            - SaptivaExtractor: Ping health endpoint of Saptiva API
        """
        raise NotImplementedError("Subclasses must implement health_check()")


class ExtractionError(Exception):
    """
    Base exception for extraction failures.

    Attributes:
        media_type: Type of document that failed
        original_error: Underlying exception (if any)
    """

    def __init__(
        self,
        message: str,
        media_type: Optional[MediaType] = None,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.media_type = media_type
        self.original_error = original_error


class UnsupportedFormatError(ExtractionError):
    """Raised when document format is not supported by extractor."""

    pass


class ExtractionTimeoutError(ExtractionError):
    """Raised when extraction exceeds timeout limit."""

    pass
