"""
Unit tests for core/dependencies module.

Tests:
- reset_service_instances function
- DependencyOverride context manager
- get_saptiva_client dependency
- get_chat_service dependency
- get_file_ingest_service dependency
- get_review_service dependency
- get_redis_cache_dep dependency
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.dependencies import (
    DependencyOverride,
    get_chat_service,
    get_file_ingest_service,
    get_redis_cache_dep,
    get_review_service,
    get_saptiva_client,
    reset_service_instances,
)

pytestmark = [pytest.mark.unit]


class TestResetServiceInstances:
    """Test reset_service_instances function."""

    def test_resets_all_service_instances(self):
        """Test resets all service instances to None."""
        import src.core.dependencies as module

        # Set some values
        module._saptiva_client = MagicMock()
        module._chat_service = MagicMock()
        module._file_ingest_service = MagicMock()
        module._review_service = MagicMock()

        reset_service_instances()

        assert module._saptiva_client is None
        assert module._chat_service is None
        assert module._file_ingest_service is None
        assert module._review_service is None


class TestDependencyOverride:
    """Test DependencyOverride context manager."""

    def test_overrides_dependency(self):
        """Test overrides dependency in app."""
        mock_app = MagicMock()
        mock_app.dependency_overrides = {}

        original_dep = MagicMock()
        override_dep = MagicMock()

        with DependencyOverride(mock_app, original_dep, override_dep):
            assert mock_app.dependency_overrides[original_dep] == override_dep

    def test_restores_after_exit(self):
        """Test restores original state after exit."""
        mock_app = MagicMock()
        mock_app.dependency_overrides = {}

        original_dep = MagicMock()
        override_dep = MagicMock()

        with DependencyOverride(mock_app, original_dep, override_dep):
            pass

        assert original_dep not in mock_app.dependency_overrides

    def test_restores_previous_override(self):
        """Test restores previous override if one existed."""
        mock_app = MagicMock()
        previous_override = MagicMock()

        original_dep = MagicMock()
        mock_app.dependency_overrides = {original_dep: previous_override}

        new_override = MagicMock()

        with DependencyOverride(mock_app, original_dep, new_override):
            assert mock_app.dependency_overrides[original_dep] == new_override

        assert mock_app.dependency_overrides[original_dep] == previous_override

    def test_returns_self(self):
        """Test __enter__ returns self."""
        mock_app = MagicMock()
        mock_app.dependency_overrides = {}

        override = DependencyOverride(mock_app, MagicMock(), MagicMock())

        with override as o:
            assert o is override

    def test_exit_returns_false(self):
        """Test __exit__ returns False to not suppress exceptions."""
        mock_app = MagicMock()
        mock_app.dependency_overrides = {}

        override = DependencyOverride(mock_app, MagicMock(), MagicMock())
        override.__enter__()

        result = override.__exit__(None, None, None)
        assert result is False


class TestGetSaptivaClient:
    """Test get_saptiva_client dependency."""

    @pytest.mark.asyncio
    async def test_returns_cached_instance(self):
        """Test returns cached instance on subsequent calls."""
        import src.core.dependencies as module

        mock_client = MagicMock()
        module._saptiva_client = mock_client

        result = await get_saptiva_client()

        assert result is mock_client


class TestGetFileIngestService:
    """Test get_file_ingest_service dependency."""

    @pytest.mark.asyncio
    async def test_returns_cached_instance(self):
        """Test returns cached instance on subsequent calls."""
        import src.core.dependencies as module

        mock_service = MagicMock()
        module._file_ingest_service = mock_service

        result = await get_file_ingest_service()

        assert result is mock_service


class TestGetReviewService:
    """Test get_review_service dependency."""

    @pytest.mark.asyncio
    async def test_returns_cached_instance(self):
        """Test returns cached instance on subsequent calls."""
        import src.core.dependencies as module

        mock_service = MagicMock()
        module._review_service = mock_service

        result = await get_review_service()

        assert result is mock_service


class TestGetRedisCacheDep:
    """Test get_redis_cache_dep dependency."""

    @pytest.mark.asyncio
    async def test_calls_get_redis_cache(self):
        """Test calls get_redis_cache function."""
        mock_cache = MagicMock()

        with patch(
            "src.core.dependencies.get_redis_cache",
            new_callable=AsyncMock,
            return_value=mock_cache,
        ):
            result = await get_redis_cache_dep()

            assert result is mock_cache
