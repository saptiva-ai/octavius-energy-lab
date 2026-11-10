"""
Unit tests for Fase 4: Scheduled cache purge + manual purge endpoint.

Tests background purge loop behavior and /cache/purge endpoint routing.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest


# --- Tests: _scheduled_cache_purge ---


@pytest.mark.unit
class TestScheduledCachePurge:
    """Test the background purge task."""

    @pytest.mark.asyncio
    async def test_purge_calls_expired_and_cold(self):
        """Verify scheduled purge calls both purge methods."""
        from src.main import _scheduled_cache_purge

        mock_cache = MagicMock()
        mock_cache.purge_expired.return_value = 5
        mock_cache.purge_cold.return_value = 3

        call_count = 0

        async def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                # Cancel after first purge cycle
                raise asyncio.CancelledError()

        with (
            patch("src.main.get_llm_semantic_cache", return_value=mock_cache),
            patch("src.main.PURGE_INITIAL_DELAY", 0),
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch("asyncio.to_thread", side_effect=lambda fn, *a: fn(*a)),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _scheduled_cache_purge()

        mock_cache.purge_expired.assert_called_once()
        mock_cache.purge_cold.assert_called_once()

    @pytest.mark.asyncio
    async def test_purge_handles_none_cache(self):
        """Verify scheduled purge handles unavailable cache gracefully."""
        from src.main import _scheduled_cache_purge

        call_count = 0

        async def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise asyncio.CancelledError()

        with (
            patch("src.main.get_llm_semantic_cache", return_value=None),
            patch("src.main.PURGE_INITIAL_DELAY", 0),
            patch("asyncio.sleep", side_effect=fake_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _scheduled_cache_purge()

        # Should not crash — just skip purge

    @pytest.mark.asyncio
    async def test_purge_handles_exception(self):
        """Verify scheduled purge continues after exception."""
        from src.main import _scheduled_cache_purge

        mock_cache = MagicMock()
        mock_cache.purge_expired.side_effect = RuntimeError("Weaviate down")

        call_count = 0

        async def fake_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise asyncio.CancelledError()

        with (
            patch("src.main.get_llm_semantic_cache", return_value=mock_cache),
            patch("src.main.PURGE_INITIAL_DELAY", 0),
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch("asyncio.to_thread", side_effect=lambda fn, *a: fn(*a)),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _scheduled_cache_purge()

        # Should not crash — error is logged and loop continues


# --- Tests: POST /cache/purge endpoint ---


@pytest.mark.unit
class TestCachePurgeEndpoint:
    """Test the manual /cache/purge endpoint logic."""

    def test_purge_request_validates_target(self):
        """Verify CachePurgeRequest accepts valid targets."""
        from src.routers.internal import CachePurgeRequest

        req = CachePurgeRequest(target="expired")
        assert req.target == "expired"

        req = CachePurgeRequest(target="all")
        assert req.target == "all"

    def test_purge_request_defaults_to_all(self):
        """Verify default target is 'all'."""
        from src.routers.internal import CachePurgeRequest

        req = CachePurgeRequest()
        assert req.target == "all"

    def test_purge_request_version_requires_tag(self):
        """Verify version target includes version_tag field."""
        from src.routers.internal import CachePurgeRequest

        req = CachePurgeRequest(target="version", version_tag="v1")
        assert req.version_tag == "v1"

    def test_purge_response_structure(self):
        """Verify CachePurgeResponse serializes correctly."""
        from src.routers.internal import CachePurgeResponse

        resp = CachePurgeResponse(status="purged", results={"expired": 5, "cold": 3})
        data = resp.model_dump()
        assert data["status"] == "purged"
        assert data["results"]["expired"] == 5
        assert data["results"]["cold"] == 3


# --- Tests: Purge configuration constants ---


@pytest.mark.unit
class TestPurgeConfig:
    """Test purge timing constants."""

    def test_initial_delay_is_1_hour(self):
        from src.main import PURGE_INITIAL_DELAY

        assert PURGE_INITIAL_DELAY == 3600

    def test_interval_is_24_hours(self):
        from src.main import PURGE_INTERVAL

        assert PURGE_INTERVAL == 86400
