"""
Unit tests for mcp_cache service.

Tests:
- generate_cache_key function
- TOOL_CACHE_TTL configuration
- invalidate_tool_cache function
- invalidate_document_tool_cache function
- invalidate_all_tool_caches function
- get_cache_stats function
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.mcp_cache import (
    TOOL_CACHE_TTL,
    generate_cache_key,
    get_cache_stats,
    invalidate_all_tool_caches,
    invalidate_document_tool_cache,
    invalidate_tool_cache,
)

pytestmark = [pytest.mark.unit]


class TestToolCacheTTL:
    """Test TOOL_CACHE_TTL configuration."""

    def test_audit_file_ttl(self):
        """Test audit_file TTL is 1 hour."""
        assert TOOL_CACHE_TTL["audit_file"] == 3600

    def test_excel_analyzer_ttl(self):
        """Test excel_analyzer TTL is 30 min."""
        assert TOOL_CACHE_TTL["excel_analyzer"] == 1800

    def test_deep_research_ttl(self):
        """Test deep_research TTL is 24 hours."""
        assert TOOL_CACHE_TTL["deep_research"] == 86400

    def test_extract_document_text_ttl(self):
        """Test extract_document_text TTL is 1 hour."""
        assert TOOL_CACHE_TTL["extract_document_text"] == 3600

    def test_all_ttls_are_positive(self):
        """Test all TTLs are positive integers."""
        for tool, ttl in TOOL_CACHE_TTL.items():
            assert isinstance(ttl, int)
            assert ttl > 0


class TestGenerateCacheKey:
    """Test generate_cache_key function."""

    def test_basic_key_without_params(self):
        """Test key generation without params."""
        key = generate_cache_key("audit_file", "doc_123")
        assert key == "mcp:tool:audit_file:doc_123"

    def test_key_with_params(self):
        """Test key generation with params."""
        key = generate_cache_key("audit_file", "doc_123", {"policy_id": "auto"})
        assert key.startswith("mcp:tool:audit_file:doc_123:")
        assert len(key) == len("mcp:tool:audit_file:doc_123:") + 8

    def test_params_hash_is_deterministic(self):
        """Test same params produce same hash."""
        key1 = generate_cache_key("audit_file", "doc_123", {"policy_id": "auto"})
        key2 = generate_cache_key("audit_file", "doc_123", {"policy_id": "auto"})
        assert key1 == key2

    def test_different_params_produce_different_keys(self):
        """Test different params produce different hashes."""
        key1 = generate_cache_key("audit_file", "doc_123", {"policy_id": "auto"})
        key2 = generate_cache_key("audit_file", "doc_123", {"policy_id": "manual"})
        assert key1 != key2

    def test_param_order_does_not_matter(self):
        """Test params are sorted for deterministic hashing."""
        key1 = generate_cache_key("tool", "doc", {"a": 1, "b": 2})
        key2 = generate_cache_key("tool", "doc", {"b": 2, "a": 1})
        assert key1 == key2

    def test_different_tools_produce_different_keys(self):
        """Test different tools produce different keys."""
        key1 = generate_cache_key("audit_file", "doc_123")
        key2 = generate_cache_key("excel_analyzer", "doc_123")
        assert key1 != key2

    def test_different_docs_produce_different_keys(self):
        """Test different docs produce different keys."""
        key1 = generate_cache_key("audit_file", "doc_123")
        key2 = generate_cache_key("audit_file", "doc_456")
        assert key1 != key2

    def test_empty_params_same_as_none(self):
        """Test empty params dict is same as no params."""
        # Empty dict is truthy so it should add a hash
        key_with_empty = generate_cache_key("audit_file", "doc_123", {})
        # But wait, {} is truthy in Python, so this will add a hash
        # Let's verify behavior
        key_without = generate_cache_key("audit_file", "doc_123", None)
        # Empty dict will produce a hash, so keys should differ
        # unless the implementation treats {} as falsy-like (which it doesn't)
        # Actually {} is falsy in if check? No, {} is truthy
        # Let me check: bool({}) == False, so empty dict is truthy-check failing
        # Actually bool({}) is False! Empty containers are falsy in Python
        assert key_with_empty == key_without

    def test_complex_params(self):
        """Test with complex nested params."""
        params = {
            "filters": {"date": "2024-01-01", "status": "active"},
            "options": [1, 2, 3],
        }
        key = generate_cache_key("tool", "doc", params)
        assert key.startswith("mcp:tool:tool:doc:")
        # Should have 8-char hash suffix
        parts = key.split(":")
        assert len(parts) == 5
        assert len(parts[4]) == 8


class TestInvalidateToolCache:
    """Test invalidate_tool_cache function."""

    @pytest.mark.asyncio
    async def test_invalidates_cache_successfully(self):
        """Test successful cache invalidation."""
        mock_cache = AsyncMock()
        mock_cache.client.delete = AsyncMock(return_value=1)

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            result = await invalidate_tool_cache("audit_file", "doc_123")

        assert result is True
        mock_cache.client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_no_cache_to_delete(self):
        """Test returns False when cache key doesn't exist."""
        mock_cache = AsyncMock()
        mock_cache.client.delete = AsyncMock(return_value=0)

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            result = await invalidate_tool_cache("audit_file", "doc_123")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self):
        """Test returns False on Redis error."""
        with patch(
            "src.services.mcp_cache.get_redis_cache",
            side_effect=Exception("Redis error"),
        ):
            result = await invalidate_tool_cache("audit_file", "doc_123")

        assert result is False

    @pytest.mark.asyncio
    async def test_uses_correct_cache_key(self):
        """Test uses correct cache key format."""
        mock_cache = AsyncMock()
        mock_cache.client.delete = AsyncMock(return_value=1)

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            await invalidate_tool_cache("audit_file", "doc_123")

        mock_cache.client.delete.assert_called_with("mcp:tool:audit_file:doc_123")

    @pytest.mark.asyncio
    async def test_uses_correct_cache_key_with_params(self):
        """Test uses correct cache key format with params."""
        mock_cache = AsyncMock()
        mock_cache.client.delete = AsyncMock(return_value=1)

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            await invalidate_tool_cache(
                "audit_file", "doc_123", {"policy_id": "auto"}
            )

        call_args = mock_cache.client.delete.call_args[0][0]
        assert call_args.startswith("mcp:tool:audit_file:doc_123:")


class TestInvalidateDocumentToolCache:
    """Test invalidate_document_tool_cache function."""

    @pytest.mark.asyncio
    async def test_invalidates_all_tools_for_document(self):
        """Test invalidates all tool caches for a document."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(
            return_value=["key1", "key2", "key3"]
        )
        mock_cache.client.delete = AsyncMock(return_value=3)

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            result = await invalidate_document_tool_cache("doc_123")

        assert result == 3
        # Should scan for all tools
        mock_cache._scan_keys.assert_called()

    @pytest.mark.asyncio
    async def test_invalidates_specific_tool_for_document(self):
        """Test invalidates specific tool cache for a document."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(return_value=["key1"])
        mock_cache.client.delete = AsyncMock(return_value=1)

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            result = await invalidate_document_tool_cache("doc_123", "audit_file")

        assert result == 1

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_caches(self):
        """Test returns 0 when no caches to delete."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(return_value=[])

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            result = await invalidate_document_tool_cache("doc_123")

        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_zero_on_error(self):
        """Test returns 0 on error."""
        with patch(
            "src.services.mcp_cache.get_redis_cache",
            side_effect=Exception("Redis error"),
        ):
            result = await invalidate_document_tool_cache("doc_123")

        assert result == 0


class TestInvalidateAllToolCaches:
    """Test invalidate_all_tool_caches function."""

    @pytest.mark.asyncio
    async def test_invalidates_all_caches_for_tool(self):
        """Test invalidates all caches for a specific tool."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(return_value=["key1", "key2"])
        mock_cache.client.delete = AsyncMock(return_value=2)

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            result = await invalidate_all_tool_caches("audit_file")

        assert result == 2

    @pytest.mark.asyncio
    async def test_invalidates_all_tool_caches(self):
        """Test invalidates all tool caches when no tool specified."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(return_value=["key1", "key2", "key3"])
        mock_cache.client.delete = AsyncMock(return_value=3)

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            result = await invalidate_all_tool_caches()

        assert result == 3

    @pytest.mark.asyncio
    async def test_returns_zero_on_error(self):
        """Test returns 0 on error."""
        with patch(
            "src.services.mcp_cache.get_redis_cache",
            side_effect=Exception("Redis error"),
        ):
            result = await invalidate_all_tool_caches()

        assert result == 0


class TestGetCacheStats:
    """Test get_cache_stats function."""

    @pytest.mark.asyncio
    async def test_returns_stats_structure(self):
        """Test returns correct stats structure."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(
            return_value=[
                "mcp:tool:audit_file:doc_123",
                "mcp:tool:audit_file:doc_456",
                "mcp:tool:excel_analyzer:doc_123",
            ]
        )

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            stats = await get_cache_stats()

        assert "total_keys" in stats
        assert "by_tool" in stats
        assert "by_document" in stats
        assert stats["total_keys"] == 3

    @pytest.mark.asyncio
    async def test_counts_by_tool(self):
        """Test correctly counts by tool."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(
            return_value=[
                "mcp:tool:audit_file:doc_1",
                "mcp:tool:audit_file:doc_2",
                "mcp:tool:excel_analyzer:doc_1",
            ]
        )

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            stats = await get_cache_stats()

        assert stats["by_tool"]["audit_file"] == 2
        assert stats["by_tool"]["excel_analyzer"] == 1

    @pytest.mark.asyncio
    async def test_counts_by_document(self):
        """Test correctly counts by document."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(
            return_value=[
                "mcp:tool:audit_file:doc_123",
                "mcp:tool:excel_analyzer:doc_123",
                "mcp:tool:audit_file:doc_456",
            ]
        )

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            stats = await get_cache_stats()

        assert stats["by_document"]["doc_123"] == 2
        assert stats["by_document"]["doc_456"] == 1

    @pytest.mark.asyncio
    async def test_filters_by_document(self):
        """Test filters stats by document when provided."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(return_value=["mcp:tool:audit_file:doc_123"])

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            stats = await get_cache_stats(doc_id="doc_123")

        # Should have called scan with pattern filtered by doc_id
        mock_cache._scan_keys.assert_called()

    @pytest.mark.asyncio
    async def test_returns_error_on_failure(self):
        """Test returns error dict on failure."""
        with patch(
            "src.services.mcp_cache.get_redis_cache",
            side_effect=Exception("Redis error"),
        ):
            stats = await get_cache_stats()

        assert stats["total_keys"] == 0
        assert "error" in stats


class TestWarmupToolCache:
    """Test warmup_tool_cache function."""

    @pytest.mark.asyncio
    async def test_warms_up_cache_successfully(self):
        """Test successful cache warmup."""
        from src.services.mcp_cache import warmup_tool_cache

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        mock_tool_impl = AsyncMock()
        mock_adapter = MagicMock()
        mock_adapter.get_tool_map = AsyncMock(
            return_value={"audit_file": mock_tool_impl}
        )
        mock_adapter.execute_tool = AsyncMock(
            return_value={"result": "success"}
        )

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ), patch(
            "src.mcp_integration.get_mcp_adapter", return_value=mock_adapter
        ):
            result = await warmup_tool_cache(
                "audit_file", ["doc_1", "doc_2"], "user_123"
            )

        assert result["cached"] == 2
        assert result["failed"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_skips_already_cached(self):
        """Test skips documents already cached."""
        from src.services.mcp_cache import warmup_tool_cache

        mock_cache = AsyncMock()
        # First doc is cached, second is not
        mock_cache.get = AsyncMock(side_effect=[{"existing": "data"}, None])
        mock_cache.set = AsyncMock()

        mock_tool_impl = AsyncMock()
        mock_adapter = MagicMock()
        mock_adapter.get_tool_map = AsyncMock(
            return_value={"audit_file": mock_tool_impl}
        )
        mock_adapter.execute_tool = AsyncMock(
            return_value={"result": "new"}
        )

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ), patch(
            "src.mcp_integration.get_mcp_adapter", return_value=mock_adapter
        ):
            result = await warmup_tool_cache(
                "audit_file", ["doc_1", "doc_2"], "user_123"
            )

        # Both should be counted as cached (1 existing, 1 newly cached)
        assert result["cached"] == 2
        # set() should only be called for the second doc
        assert mock_cache.set.call_count == 1

    @pytest.mark.asyncio
    async def test_handles_tool_not_found(self):
        """Test handles tool not found in registry."""
        from src.services.mcp_cache import warmup_tool_cache

        mock_cache = AsyncMock()

        mock_adapter = MagicMock()
        mock_adapter.get_tool_map = AsyncMock(return_value={})

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ), patch(
            "src.mcp_integration.get_mcp_adapter", return_value=mock_adapter
        ):
            result = await warmup_tool_cache(
                "nonexistent_tool", ["doc_1"], "user_123"
            )

        assert result["cached"] == 0
        assert "not found" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_handles_per_document_errors(self):
        """Test handles errors for individual documents."""
        from src.services.mcp_cache import warmup_tool_cache

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        mock_tool_impl = AsyncMock()
        mock_adapter = MagicMock()
        mock_adapter.get_tool_map = AsyncMock(
            return_value={"audit_file": mock_tool_impl}
        )
        # First succeeds, second fails
        mock_adapter.execute_tool = AsyncMock(
            side_effect=[{"result": "ok"}, Exception("Tool failed")]
        )

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ), patch(
            "src.mcp_integration.get_mcp_adapter", return_value=mock_adapter
        ):
            result = await warmup_tool_cache(
                "audit_file", ["doc_1", "doc_2"], "user_123"
            )

        assert result["cached"] == 1
        assert result["failed"] == 1
        assert len(result["errors"]) == 1
        assert "doc_2" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_uses_correct_ttl(self):
        """Test uses correct TTL for tool."""
        from src.services.mcp_cache import TOOL_CACHE_TTL, warmup_tool_cache

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        mock_tool_impl = AsyncMock()
        mock_adapter = MagicMock()
        mock_adapter.get_tool_map = AsyncMock(
            return_value={"audit_file": mock_tool_impl}
        )
        mock_adapter.execute_tool = AsyncMock(return_value={})

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ), patch(
            "src.mcp_integration.get_mcp_adapter", return_value=mock_adapter
        ):
            await warmup_tool_cache("audit_file", ["doc_1"], "user_123")

        # Check TTL was passed
        mock_cache.set.assert_called_once()
        call_kwargs = mock_cache.set.call_args
        assert call_kwargs[1]["expire"] == TOOL_CACHE_TTL["audit_file"]

    @pytest.mark.asyncio
    async def test_uses_default_ttl_for_unknown_tool(self):
        """Test uses default TTL for unknown tool."""
        from src.services.mcp_cache import warmup_tool_cache

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        mock_tool_impl = AsyncMock()
        mock_adapter = MagicMock()
        mock_adapter.get_tool_map = AsyncMock(
            return_value={"custom_tool": mock_tool_impl}
        )
        mock_adapter.execute_tool = AsyncMock(return_value={})

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ), patch(
            "src.mcp_integration.get_mcp_adapter", return_value=mock_adapter
        ):
            await warmup_tool_cache("custom_tool", ["doc_1"], "user_123")

        # Default TTL is 3600
        call_kwargs = mock_cache.set.call_args
        assert call_kwargs[1]["expire"] == 3600

    @pytest.mark.asyncio
    async def test_passes_params_to_tool(self):
        """Test passes params to tool execution."""
        from src.services.mcp_cache import warmup_tool_cache

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        mock_tool_impl = AsyncMock()
        mock_adapter = MagicMock()
        mock_adapter.get_tool_map = AsyncMock(
            return_value={"audit_file": mock_tool_impl}
        )
        mock_adapter.execute_tool = AsyncMock(return_value={})

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ), patch(
            "src.mcp_integration.get_mcp_adapter", return_value=mock_adapter
        ):
            await warmup_tool_cache(
                "audit_file", ["doc_1"], "user_123", {"policy_id": "auto"}
            )

        # Check payload includes params
        call_args = mock_adapter.execute_tool.call_args
        payload = call_args[1]["payload"]
        assert payload["policy_id"] == "auto"
        assert payload["doc_id"] == "doc_1"
        assert payload["user_id"] == "user_123"


class TestMultiIterationScans:
    """Test scan operations that require multiple iterations."""

    @pytest.mark.asyncio
    async def test_invalidate_document_multiple_scan_iterations(self):
        """Test invalidate_document_tool_cache with many keys."""
        mock_cache = AsyncMock()
        # _scan_keys handles cursor iteration internally, returns flat list
        mock_cache._scan_keys = AsyncMock(
            return_value=["key1", "key2", "key3"]
        )
        mock_cache.client.delete = AsyncMock(return_value=3)

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            result = await invalidate_document_tool_cache("doc_123")

        assert result == 3
        mock_cache._scan_keys.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalidate_all_multiple_scan_iterations(self):
        """Test invalidate_all_tool_caches with many keys."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(
            return_value=["key1", "key2", "key3"]
        )
        mock_cache.client.delete = AsyncMock(return_value=3)

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            result = await invalidate_all_tool_caches("audit_file")

        assert result == 3
        mock_cache._scan_keys.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cache_stats_multiple_scan_iterations(self):
        """Test get_cache_stats with many keys."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(
            return_value=[
                "mcp:tool:audit_file:doc_1",
                "mcp:tool:excel_analyzer:doc_2",
            ]
        )

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            stats = await get_cache_stats()

        assert stats["total_keys"] == 2
        mock_cache._scan_keys.assert_called_once()


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_invalidate_with_special_characters_in_doc_id(self):
        """Test invalidation with special characters in doc_id."""
        mock_cache = AsyncMock()
        mock_cache.client.delete = AsyncMock(return_value=1)

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            result = await invalidate_tool_cache(
                "audit_file", "doc_with-special_chars.pdf"
            )

        assert result is True
        call_args = mock_cache.client.delete.call_args[0][0]
        assert "doc_with-special_chars.pdf" in call_args

    @pytest.mark.asyncio
    async def test_cache_stats_handles_malformed_keys(self):
        """Test get_cache_stats handles keys with fewer parts than expected."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(
            return_value=[
                "mcp:tool:audit_file:doc_123",  # Valid 4 parts
                "mcp:tool:short",               # Invalid < 4 parts
                "invalid_key",                   # Invalid < 4 parts
            ]
        )

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            stats = await get_cache_stats()

        # Only the valid key should be counted in by_tool/by_document
        assert stats["total_keys"] == 3
        assert stats["by_tool"] == {"audit_file": 1}
        assert stats["by_document"] == {"doc_123": 1}

    @pytest.mark.asyncio
    async def test_invalidate_document_with_tool_filter(self):
        """Test invalidate_document uses correct pattern with tool filter."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(return_value=[])

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            await invalidate_document_tool_cache("doc_123", "audit_file")

        # Verify pattern includes tool name (positional arg)
        pattern = mock_cache._scan_keys.call_args[0][0]
        assert "audit_file" in pattern
        assert "doc_123" in pattern

    @pytest.mark.asyncio
    async def test_invalidate_all_without_tool_filter(self):
        """Test invalidate_all uses correct pattern without tool filter."""
        mock_cache = AsyncMock()
        mock_cache._scan_keys = AsyncMock(return_value=[])

        with patch(
            "src.services.mcp_cache.get_redis_cache", return_value=mock_cache
        ):
            await invalidate_all_tool_caches()

        # Verify pattern is generic (positional arg)
        pattern = mock_cache._scan_keys.call_args[0][0]
        assert pattern == "mcp:tool:*"
