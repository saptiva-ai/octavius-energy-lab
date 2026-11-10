"""
Text Extraction Abstraction Layer

This package provides a pluggable architecture for document text extraction.
Supports multiple backends controlled by EXTRACTOR_PROVIDER environment variable.

Quick Start:
    from services.extractors import get_text_extractor

    extractor = get_text_extractor()
    text = await extractor.extract_text(
        media_type="pdf",
        data=file_bytes,
        mime="application/pdf",
        filename="document.pdf",
    )

Available Extractors:
    - ThirdPartyExtractor: Uses pypdf + pytesseract (current production)
    - SaptivaExtractor: Uses Saptiva Native Tools API (Phase 2)

Configuration:
    EXTRACTOR_PROVIDER=third_party  # Default (pypdf + pytesseract)
    EXTRACTOR_PROVIDER=saptiva      # Saptiva Native Tools (Phase 2)

    SAPTIVA_BASE_URL=https://api.saptiva.ai
    SAPTIVA_API_KEY=<your-key-here>
"""

from .base import (
    ExtractionError,
    ExtractionTimeoutError,
    MediaType,
    TextExtractor,
    UnsupportedFormatError,
)
from .factory import (
    clear_extractor_cache,
    get_text_extractor,
    health_check_extractor,
)

# Lazy imports for concrete implementations to avoid loading heavy dependencies
# (fitz, pytesseract) at module load time. Import explicitly when needed:
#   from services.extractors.huggingface import HuggingFaceExtractor
#   from services.extractors.saptiva import SaptivaExtractor
#   from services.extractors.third_party import ThirdPartyExtractor

# Cache and A/B testing modules are available but not imported by default
# to avoid circular dependencies. Import explicitly if needed:
#   from services.extractors.cache import get_extraction_cache
#   from services.extractors.ab_testing import get_ab_test_framework

__all__ = [
    # Abstract interface
    "TextExtractor",
    "MediaType",
    # Exceptions
    "ExtractionError",
    "UnsupportedFormatError",
    "ExtractionTimeoutError",
    # Factory functions
    "get_text_extractor",
    "clear_extractor_cache",
    "health_check_extractor",
    # Note: Concrete implementations (ThirdPartyExtractor, SaptivaExtractor,
    # HuggingFaceExtractor) are NOT exported at module level to avoid loading
    # heavy dependencies. Import them explicitly from their modules when needed.
]

__version__ = "2.0.0"
