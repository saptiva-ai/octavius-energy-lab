"""
Unit tests for Fase 5: Cache observability (stats endpoint).

Tests the /cache/stats endpoint response aggregation across all cache layers.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
class TestCacheStatsEndpoint:
    """Test the GET /cache/stats endpoint logic."""

    @pytest.mark.asyncio
    async def test_stats_aggregates_all_layers(self):
        """Verify stats returns data from extraction, mcp, and semantic caches."""
        from src.routers.internal import cache_stats

        mock_extraction = MagicMock()
        mock_extraction.get_metrics.return_value = {
            "enabled": True,
            "cache_hits": 100,
            "cache_misses": 20,
            "hit_rate": 0.833,
        }

        mock_mcp_stats = {
            "total_keys": 42,
            "by_tool": {"audit_file": 15},
        }

        mock_semantic = MagicMock()
        mock_semantic.get_stats.return_value = {
            "status": "healthy",
            "total_entries": 50,
            "cache_version": "v1",
        }

        with (
            patch(
                "src.services.extractors.cache.get_extraction_cache",
                return_value=mock_extraction,
            ),
            patch(
                "src.services.mcp_cache.get_cache_stats",
                new_callable=AsyncMock,
                return_value=mock_mcp_stats,
            ),
            patch(
                "src.services.llm_semantic_cache.get_llm_semantic_cache",
                return_value=mock_semantic,
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *a: fn(*a)),
        ):
            result = await cache_stats()

        assert "extraction" in result
        assert result["extraction"]["cache_hits"] == 100
        assert "mcp_tools" in result
        assert result["mcp_tools"]["total_keys"] == 42
        assert "semantic" in result
        assert result["semantic"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_stats_handles_extraction_error(self):
        """Verify extraction error is caught and reported."""
        from src.routers.internal import cache_stats

        mock_mcp_stats = {"total_keys": 0}
        mock_semantic = MagicMock()
        mock_semantic.get_stats.return_value = {"status": "healthy"}

        with (
            patch(
                "src.services.extractors.cache.get_extraction_cache",
                side_effect=RuntimeError("Redis down"),
            ),
            patch(
                "src.services.mcp_cache.get_cache_stats",
                new_callable=AsyncMock,
                return_value=mock_mcp_stats,
            ),
            patch(
                "src.services.llm_semantic_cache.get_llm_semantic_cache",
                return_value=mock_semantic,
            ),
            patch("asyncio.to_thread", side_effect=lambda fn, *a: fn(*a)),
        ):
            result = await cache_stats()

        assert result["extraction"]["status"] == "error"
        assert "Redis down" in result["extraction"]["error"]
        # Other layers should still work
        assert result["mcp_tools"]["total_keys"] == 0

    @pytest.mark.asyncio
    async def test_stats_handles_semantic_unavailable(self):
        """Verify semantic cache reports unavailable when not initialized."""
        from src.routers.internal import cache_stats

        mock_extraction = MagicMock()
        mock_extraction.get_metrics.return_value = {"enabled": True}

        with (
            patch(
                "src.services.extractors.cache.get_extraction_cache",
                return_value=mock_extraction,
            ),
            patch(
                "src.services.mcp_cache.get_cache_stats",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "src.services.llm_semantic_cache.get_llm_semantic_cache",
                return_value=None,
            ),
        ):
            result = await cache_stats()

        assert result["semantic"]["status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_stats_handles_mcp_error(self):
        """Verify MCP stats error is caught and reported."""
        from src.routers.internal import cache_stats

        mock_extraction = MagicMock()
        mock_extraction.get_metrics.return_value = {"enabled": True}

        with (
            patch(
                "src.services.extractors.cache.get_extraction_cache",
                return_value=mock_extraction,
            ),
            patch(
                "src.services.mcp_cache.get_cache_stats",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Cannot connect"),
            ),
            patch(
                "src.services.llm_semantic_cache.get_llm_semantic_cache",
                return_value=None,
            ),
        ):
            result = await cache_stats()

        assert result["mcp_tools"]["status"] == "error"
        assert "Cannot connect" in result["mcp_tools"]["error"]
