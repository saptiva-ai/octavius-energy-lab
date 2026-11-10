"""
Dependency Injection Container for FastAPI.

This module provides a centralized service registry and dependency providers
for the application. It follows FastAPI's Depends() pattern for consistency.

Usage in routers:
    from ..core.dependencies import get_chat_service, get_saptiva_client

    @router.post("/chat")
    async def chat(
        chat_service: ChatService = Depends(get_chat_service),
    ):
        ...

Usage in tests:
    from app.core.dependencies import DependencyOverride

    def test_chat(app):
        mock_saptiva = MockSaptivaClient()
        with DependencyOverride(app, get_saptiva_client, lambda: mock_saptiva):
            ...

Design Principles:
1. All service providers are async-compatible
2. Services are lazily initialized on first use
3. Dependencies can be overridden for testing
4. No global state modification at module load time
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import Depends

from .config import Settings, get_settings
from .redis_cache import RedisCache, get_redis_cache

if TYPE_CHECKING:
    from ..services.chat_service import ChatService
    from ..services.file_ingest import FileIngestService
    from ..services.review_service import ReviewService
    from ..services.saptiva_client import SaptivaClient

# ============================================================================
# Service Instance Cache (lazy singletons)
# ============================================================================

_saptiva_client: Optional["SaptivaClient"] = None
_chat_service: Optional["ChatService"] = None
_file_ingest_service: Optional["FileIngestService"] = None
_review_service: Optional["ReviewService"] = None


# ============================================================================
# Dependency Providers
# ============================================================================


async def get_saptiva_client() -> "SaptivaClient":
    """
    Provide SaptivaClient instance.

    This provider creates a singleton SaptivaClient instance
    and reuses it across requests. API key is loaded from
    storage on first initialization.

    Returns:
        SaptivaClient singleton instance
    """
    from ..services.saptiva_client import SaptivaClient, load_saptiva_api_key

    global _saptiva_client
    if _saptiva_client is None:
        _saptiva_client = SaptivaClient()
        # Load stored API key if available
        stored_key = await load_saptiva_api_key()
        if stored_key:
            _saptiva_client.set_api_key(stored_key)
    return _saptiva_client


async def get_chat_service(
    settings: Settings = Depends(get_settings),
    saptiva_client: "SaptivaClient" = Depends(get_saptiva_client),
) -> "ChatService":
    """
    Provide ChatService instance with injected dependencies.

    This provider creates a ChatService with properly injected
    SaptivaClient and Settings, enabling easier testing and
    swappable implementations.

    Args:
        settings: Application settings (injected)
        saptiva_client: Saptiva API client (injected)

    Returns:
        ChatService instance with injected dependencies
    """
    from ..services.chat_service import ChatService

    # Note: We create a new instance each request to ensure fresh state.
    # For singleton behavior, cache in _chat_service (see pattern below).
    return ChatService(settings, saptiva_client=saptiva_client)


async def get_file_ingest_service() -> "FileIngestService":
    """
    Provide FileIngestService instance.

    Returns:
        FileIngestService singleton instance
    """
    from ..services.file_ingest import FileIngestService

    global _file_ingest_service
    if _file_ingest_service is None:
        _file_ingest_service = FileIngestService()
    return _file_ingest_service


async def get_review_service() -> "ReviewService":
    """
    Provide ReviewService instance.

    Returns:
        ReviewService singleton instance
    """
    from ..services.review_service import ReviewService

    global _review_service
    if _review_service is None:
        _review_service = ReviewService()
    return _review_service


async def get_redis_cache_dep() -> RedisCache:
    """
    Provide RedisCache instance.

    Wrapper around the existing get_redis_cache() for consistency
    with other dependency providers.

    Returns:
        RedisCache singleton instance
    """
    return await get_redis_cache()


# ============================================================================
# Test Utilities
# ============================================================================


def reset_service_instances() -> None:
    """
    Reset all cached service instances.

    Call this in test fixtures to ensure clean state between tests.

    Example:
        @pytest.fixture(autouse=True)
        def reset_di():
            yield
            reset_service_instances()
    """
    global _saptiva_client, _chat_service, _file_ingest_service, _review_service
    _saptiva_client = None
    _chat_service = None
    _file_ingest_service = None
    _review_service = None


class DependencyOverride:
    """
    Context manager for overriding dependencies in tests.

    Usage:
        def test_chat(app):
            mock = MockSaptivaClient()
            with DependencyOverride(app, get_saptiva_client, lambda: mock):
                # Test code here - all requests use mock
                response = client.post("/chat", ...)

    Args:
        app: FastAPI application instance
        original: Original dependency function to override
        override: Replacement function that returns the mock
    """

    def __init__(self, app, original, override):
        self.app = app
        self.original = original
        self.override = override
        self._original_value = None

    def __enter__(self):
        self._original_value = self.app.dependency_overrides.get(self.original)
        self.app.dependency_overrides[self.original] = self.override
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._original_value is None:
            self.app.dependency_overrides.pop(self.original, None)
        else:
            self.app.dependency_overrides[self.original] = self._original_value
        return False


# ============================================================================
# Convenience Aliases (for backwards compatibility)
# ============================================================================

# These aliases allow gradual migration from direct imports
# to the DI pattern without breaking existing code.

get_saptiva_client_dep = get_saptiva_client
get_chat_service_dep = get_chat_service
