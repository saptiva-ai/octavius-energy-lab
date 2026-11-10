"""
Text Extractor Factory

Provides dependency injection for text extraction implementations.
Selects extraction backend based on EXTRACTOR_PROVIDER environment variable.

Usage:
    from services.extractors.factory import get_text_extractor

    extractor = get_text_extractor()
    text = await extractor.extract_text(
        media_type="pdf",
        data=pdf_bytes,
        mime="application/pdf",
    )

Configuration:
    EXTRACTOR_PROVIDER: "third_party" (default) | "saptiva" | "huggingface"

    third_party: Uses pypdf + pytesseract (current production)
    saptiva: Uses Saptiva Native Tools API
    huggingface: Uses DeepSeek OCR via Hugging Face Spaces
"""

import os
from typing import TYPE_CHECKING, Optional

import structlog

from .base import TextExtractor

# Lazy imports to avoid loading heavy dependencies (fitz, pytesseract) at module load.
# Extractors are only imported when actually requested by EXTRACTOR_PROVIDER.
if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

# Module-level cache for singleton pattern
_cached_extractor: Optional[TextExtractor] = None


def get_text_extractor(*, force_new: bool = False) -> TextExtractor:
    """
    Get text extractor instance based on EXTRACTOR_PROVIDER env var.

    This function implements the singleton pattern - returns the same
    extractor instance across multiple calls unless force_new=True.

    Args:
        force_new: If True, creates new instance instead of using cached one.
                   Useful for testing or config reloading.

    Returns:
        TextExtractor implementation (ThirdPartyExtractor, SaptivaExtractor or HuggingFaceExtractor)

    Environment Variables:
        EXTRACTOR_PROVIDER: Controls which implementation to use
            - "third_party" (default): pypdf + pytesseract
            - "saptiva": Saptiva Native Tools API
            - "huggingface": DeepSeek OCR (Hugging Face Space)

    Example:
        # In service code
        extractor = get_text_extractor()
        text = await extractor.extract_text(...)

        # In tests (force new instance)
        with patch.dict(os.environ, {"EXTRACTOR_PROVIDER": "third_party"}):
            extractor = get_text_extractor(force_new=True)

    Thread Safety:
        ⚠️ Not thread-safe. If running with multiple workers (e.g., Uvicorn),
        each worker process will have its own singleton instance.
        This is acceptable for most use cases.
    """
    global _cached_extractor

    # Return cached instance if available and not forced
    if _cached_extractor is not None and not force_new:
        return _cached_extractor

    # Read configuration
    provider = (os.getenv("EXTRACTOR_PROVIDER") or "third_party").lower().strip()

    # Validate provider value
    valid_providers = {"third_party", "saptiva", "huggingface"}
    if provider not in valid_providers:
        logger.warning(
            "Invalid EXTRACTOR_PROVIDER value, falling back to third_party",
            provided=provider,
            valid_values=list(valid_providers),
        )
        provider = "third_party"

    # Create appropriate extractor (with lazy imports)
    if provider == "saptiva":
        from .saptiva import SaptivaExtractor

        logger.info(
            "Initializing SaptivaExtractor (Saptiva Native Tools API)",
            base_url=os.getenv("SAPTIVA_BASE_URL", ""),
            has_api_key=bool(os.getenv("SAPTIVA_API_KEY")),
        )
        _cached_extractor = SaptivaExtractor()
    elif provider == "huggingface":
        from .huggingface import HuggingFaceExtractor

        logger.info(
            "Initializing HuggingFaceExtractor (DeepSeek OCR)",
            endpoint=os.getenv("HF_OCR_ENDPOINT", ""),
            has_token=bool(os.getenv("HF_TOKEN")),
        )
        _cached_extractor = HuggingFaceExtractor()
    else:  # provider == "third_party"
        from .third_party import ThirdPartyExtractor

        logger.info(
            "Initializing ThirdPartyExtractor (pypdf + pytesseract)",
            provider=provider,
        )
        _cached_extractor = ThirdPartyExtractor()

    return _cached_extractor


def clear_extractor_cache() -> None:
    """
    Clear cached extractor instance.

    Useful for:
        - Testing: Reset state between tests
        - Config reload: Force recreation with new env vars
        - Memory cleanup: Release resources

    Example:
        # In pytest fixture
        @pytest.fixture(autouse=True)
        def reset_extractor():
            clear_extractor_cache()
            yield
            clear_extractor_cache()
    """
    global _cached_extractor
    _cached_extractor = None
    logger.debug("Cleared text extractor cache")


async def health_check_extractor() -> bool:
    """
    Check if current extractor is healthy.

    Convenience function that gets the current extractor and runs health check.

    Returns:
        True if extractor is operational, False otherwise

    Example:
        # In FastAPI health endpoint
        @router.get("/health")
        async def health():
            extractor_ok = await health_check_extractor()
            return {"extractor": "ok" if extractor_ok else "degraded"}
    """
    extractor = get_text_extractor()
    return await extractor.health_check()
