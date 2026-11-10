"""
Unit tests for refusal_tracker module.

Tests:
- RefusalTracker class methods
- build_consistency_prompt method
- Refusal type constants
- get_refusal_tracker singleton
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.refusal_tracker import RefusalTracker, get_refusal_tracker

pytestmark = [pytest.mark.unit]


class TestRefusalTrackerConstants:
    """Test RefusalTracker constants."""

    def test_refusal_types_defined(self):
        """Test refusal type constants are defined."""
        assert RefusalTracker.REFUSAL_BANK_NOT_FOUND == "bank_not_found"
        assert RefusalTracker.REFUSAL_METRIC_NOT_FOUND == "metric_not_found"
        assert RefusalTracker.REFUSAL_DATA_UNAVAILABLE == "data_unavailable"
        assert RefusalTracker.REFUSAL_INVALID_QUERY == "invalid_query"


class TestRefusalTrackerInit:
    """Test RefusalTracker initialization."""

    def test_init_with_redis(self):
        """Test initialization with redis cache."""
        mock_redis = MagicMock()
        tracker = RefusalTracker(mock_redis)

        assert tracker.redis == mock_redis
        assert tracker._ttl == 3600

    def test_init_with_none_redis(self):
        """Test initialization with None redis."""
        tracker = RefusalTracker(None)

        assert tracker.redis is None


class TestRecordRefusal:
    """Test record_refusal method."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock redis with async methods."""
        redis = MagicMock()
        redis.lpush = AsyncMock(return_value=1)
        redis.expire = AsyncMock(return_value=True)
        return redis

    @pytest.fixture
    def tracker(self, mock_redis):
        """Create tracker with mock redis."""
        return RefusalTracker(mock_redis)

    @pytest.mark.asyncio
    async def test_records_refusal_successfully(self, tracker, mock_redis):
        """Test successful refusal recording."""
        result = await tracker.record_refusal(
            session_id="session_123",
            refusal_type=RefusalTracker.REFUSAL_BANK_NOT_FOUND,
            entity="Banco XYZ",
            reason="Not in CNBV database",
            suggestion="BANCODEMO",
        )

        assert result is True
        mock_redis.lpush.assert_called_once()
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_correct_key(self, tracker, mock_redis):
        """Test uses correct redis key format."""
        await tracker.record_refusal(
            session_id="session_456",
            refusal_type=RefusalTracker.REFUSAL_BANK_NOT_FOUND,
            entity="Test",
        )

        # Check key format
        call_args = mock_redis.lpush.call_args
        assert call_args[0][0] == "refusals:session_456"

    @pytest.mark.asyncio
    async def test_normalizes_entity(self, tracker, mock_redis):
        """Test entity is normalized (uppercase, stripped)."""
        await tracker.record_refusal(
            session_id="session_123",
            refusal_type=RefusalTracker.REFUSAL_BANK_NOT_FOUND,
            entity="  banco xyz  ",
        )

        # Check stored data contains normalized entity
        call_args = mock_redis.lpush.call_args
        stored_json = call_args[0][1]
        assert "BANCO XYZ" in stored_json

    @pytest.mark.asyncio
    async def test_returns_false_without_redis(self):
        """Test returns False when redis is None."""
        tracker = RefusalTracker(None)

        result = await tracker.record_refusal(
            session_id="session_123",
            refusal_type=RefusalTracker.REFUSAL_BANK_NOT_FOUND,
            entity="Test",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_handles_redis_error(self, mock_redis):
        """Test handles redis errors gracefully."""
        mock_redis.lpush = AsyncMock(side_effect=Exception("Redis error"))
        tracker = RefusalTracker(mock_redis)

        result = await tracker.record_refusal(
            session_id="session_123",
            refusal_type=RefusalTracker.REFUSAL_BANK_NOT_FOUND,
            entity="Test",
        )

        assert result is False


class TestCheckPreviousRefusal:
    """Test check_previous_refusal method."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock redis."""
        redis = MagicMock()
        redis.lrange = AsyncMock(return_value=[])
        return redis

    @pytest.fixture
    def tracker(self, mock_redis):
        """Create tracker with mock redis."""
        return RefusalTracker(mock_redis)

    @pytest.mark.asyncio
    async def test_finds_matching_refusal(self, tracker, mock_redis):
        """Test finds previously recorded refusal."""
        mock_redis.lrange = AsyncMock(
            return_value=[
                '{"type": "bank_not_found", "entity": "BANCO XYZ", "reason": "Not found"}'
            ]
        )

        result = await tracker.check_previous_refusal("session_123", "Banco XYZ")

        assert result is not None
        assert result["type"] == "bank_not_found"
        assert result["entity"] == "BANCO XYZ"

    @pytest.mark.asyncio
    async def test_returns_none_for_no_match(self, tracker, mock_redis):
        """Test returns None when no matching refusal."""
        mock_redis.lrange = AsyncMock(
            return_value=[
                '{"type": "bank_not_found", "entity": "OTHER BANK", "reason": "Not found"}'
            ]
        )

        result = await tracker.check_previous_refusal("session_123", "Banco XYZ")

        assert result is None

    @pytest.mark.asyncio
    async def test_case_insensitive_entity_match(self, tracker, mock_redis):
        """Test entity matching is case insensitive."""
        mock_redis.lrange = AsyncMock(
            return_value=['{"type": "bank_not_found", "entity": "BANCO XYZ"}']
        )

        result = await tracker.check_previous_refusal("session_123", "banco xyz")

        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_none_without_redis(self):
        """Test returns None when redis is None."""
        tracker = RefusalTracker(None)

        result = await tracker.check_previous_refusal("session_123", "Test")

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_redis_error(self, mock_redis):
        """Test handles redis errors gracefully."""
        mock_redis.lrange = AsyncMock(side_effect=Exception("Redis error"))
        tracker = RefusalTracker(mock_redis)

        result = await tracker.check_previous_refusal("session_123", "Test")

        assert result is None


class TestGetAllRefusals:
    """Test get_all_refusals method."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock redis."""
        redis = MagicMock()
        redis.lrange = AsyncMock(return_value=[])
        return redis

    @pytest.mark.asyncio
    async def test_returns_all_refusals(self, mock_redis):
        """Test returns all refusals for session."""
        mock_redis.lrange = AsyncMock(
            return_value=[
                '{"type": "bank_not_found", "entity": "BANK1"}',
                '{"type": "metric_not_found", "entity": "METRIC1"}',
            ]
        )
        tracker = RefusalTracker(mock_redis)

        result = await tracker.get_all_refusals("session_123")

        assert len(result) == 2
        assert result[0]["entity"] == "BANK1"
        assert result[1]["entity"] == "METRIC1"

    @pytest.mark.asyncio
    async def test_returns_empty_without_redis(self):
        """Test returns empty list when redis is None."""
        tracker = RefusalTracker(None)

        result = await tracker.get_all_refusals("session_123")

        assert result == []

    @pytest.mark.asyncio
    async def test_handles_redis_error(self, mock_redis):
        """Test handles redis errors gracefully."""
        mock_redis.lrange = AsyncMock(side_effect=Exception("Redis error"))
        tracker = RefusalTracker(mock_redis)

        result = await tracker.get_all_refusals("session_123")

        assert result == []


class TestClearRefusals:
    """Test clear_refusals method."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock redis."""
        redis = MagicMock()
        redis.delete = AsyncMock(return_value=1)
        return redis

    @pytest.mark.asyncio
    async def test_clears_refusals(self, mock_redis):
        """Test clears refusals successfully."""
        tracker = RefusalTracker(mock_redis)

        result = await tracker.clear_refusals("session_123")

        assert result is True
        mock_redis.delete.assert_called_once_with("refusals:session_123")

    @pytest.mark.asyncio
    async def test_returns_false_without_redis(self):
        """Test returns False when redis is None."""
        tracker = RefusalTracker(None)

        result = await tracker.clear_refusals("session_123")

        assert result is False

    @pytest.mark.asyncio
    async def test_handles_redis_error(self, mock_redis):
        """Test handles redis errors gracefully."""
        mock_redis.delete = AsyncMock(side_effect=Exception("Redis error"))
        tracker = RefusalTracker(mock_redis)

        result = await tracker.clear_refusals("session_123")

        assert result is False


class TestBuildConsistencyPrompt:
    """Test build_consistency_prompt method."""

    @pytest.fixture
    def tracker(self):
        """Create tracker (redis not needed for this method)."""
        return RefusalTracker(None)

    def test_bank_not_found_prompt(self, tracker):
        """Test prompt for bank_not_found refusal."""
        refusal = {
            "type": RefusalTracker.REFUSAL_BANK_NOT_FOUND,
            "entity": "BANCO XYZ",
            "suggestion": "BANCODEMO",
        }

        prompt = tracker.build_consistency_prompt(refusal)

        assert "BANCO XYZ" in prompt
        assert "BANCODEMO" in prompt
        assert "CONSISTENCIA" in prompt

    def test_bank_not_found_without_suggestion(self, tracker):
        """Test prompt for bank_not_found without suggestion."""
        refusal = {
            "type": RefusalTracker.REFUSAL_BANK_NOT_FOUND,
            "entity": "BANCO ABC",
        }

        prompt = tracker.build_consistency_prompt(refusal)

        assert "BANCO ABC" in prompt
        assert "Quisiste decir" not in prompt

    def test_metric_not_found_prompt(self, tracker):
        """Test prompt for metric_not_found refusal."""
        refusal = {
            "type": RefusalTracker.REFUSAL_METRIC_NOT_FOUND,
            "entity": "INVALID_METRIC",
        }

        prompt = tracker.build_consistency_prompt(refusal)

        assert "INVALID_METRIC" in prompt
        assert "métrica" in prompt.lower()
        assert "CONSISTENCIA" in prompt

    def test_generic_refusal_prompt(self, tracker):
        """Test prompt for unknown refusal type."""
        refusal = {
            "type": "unknown_type",
            "entity": "SOMETHING",
        }

        prompt = tracker.build_consistency_prompt(refusal)

        assert "SOMETHING" in prompt
        assert "CONSISTENCIA" in prompt
        assert "rechazaste" in prompt

    def test_missing_entity_uses_default(self, tracker):
        """Test uses default text when entity missing."""
        refusal = {"type": RefusalTracker.REFUSAL_BANK_NOT_FOUND}

        prompt = tracker.build_consistency_prompt(refusal)

        assert "la entidad" in prompt

    def test_prompt_discourages_invention(self, tracker):
        """Test prompt discourages inventing data."""
        refusal = {
            "type": RefusalTracker.REFUSAL_BANK_NOT_FOUND,
            "entity": "TEST",
        }

        prompt = tracker.build_consistency_prompt(refusal)

        assert "NO inventes" in prompt or "no inventes" in prompt.lower()

    def test_data_unavailable_uses_generic_prompt(self, tracker):
        """Test data_unavailable type uses generic prompt."""
        refusal = {
            "type": RefusalTracker.REFUSAL_DATA_UNAVAILABLE,
            "entity": "DATA123",
        }

        prompt = tracker.build_consistency_prompt(refusal)

        assert "DATA123" in prompt
        assert "rechazaste" in prompt
        assert "CONSISTENCIA" in prompt

    def test_invalid_query_uses_generic_prompt(self, tracker):
        """Test invalid_query type uses generic prompt."""
        refusal = {
            "type": RefusalTracker.REFUSAL_INVALID_QUERY,
            "entity": "QUERY_XYZ",
        }

        prompt = tracker.build_consistency_prompt(refusal)

        assert "QUERY_XYZ" in prompt
        assert "rechazaste" in prompt


class TestGetRefusalTrackerSingleton:
    """Test get_refusal_tracker singleton function."""

    @pytest.mark.asyncio
    async def test_creates_tracker_instance(self):
        """Test creates RefusalTracker on first call."""
        import src.services.refusal_tracker as module
        original = module._refusal_tracker_instance
        module._refusal_tracker_instance = None

        try:
            mock_cache = MagicMock()

            with patch(
                "src.core.redis_cache.get_redis_cache",
                new_callable=AsyncMock,
                return_value=mock_cache,
            ):
                tracker = await get_refusal_tracker()

                assert isinstance(tracker, RefusalTracker)
                assert tracker.redis == mock_cache
        finally:
            module._refusal_tracker_instance = original

    @pytest.mark.asyncio
    async def test_returns_same_instance_on_subsequent_calls(self):
        """Test returns same instance on subsequent calls."""
        import src.services.refusal_tracker as module
        original = module._refusal_tracker_instance
        module._refusal_tracker_instance = None

        try:
            mock_cache = MagicMock()

            with patch(
                "src.core.redis_cache.get_redis_cache",
                new_callable=AsyncMock,
                return_value=mock_cache,
            ):
                tracker1 = await get_refusal_tracker()
                tracker2 = await get_refusal_tracker()

                assert tracker1 is tracker2
        finally:
            module._refusal_tracker_instance = original

    @pytest.mark.asyncio
    async def test_returns_none_when_cache_unavailable(self):
        """Test returns None when Redis cache is unavailable."""
        import src.services.refusal_tracker as module
        original = module._refusal_tracker_instance
        module._refusal_tracker_instance = None

        try:
            with patch(
                "src.core.redis_cache.get_redis_cache",
                new_callable=AsyncMock,
                return_value=None,
            ):
                tracker = await get_refusal_tracker()

                assert tracker is None
        finally:
            module._refusal_tracker_instance = original

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        """Test returns None when exception occurs during init."""
        import src.services.refusal_tracker as module
        original = module._refusal_tracker_instance
        module._refusal_tracker_instance = None

        try:
            with patch(
                "src.core.redis_cache.get_redis_cache",
                new_callable=AsyncMock,
                side_effect=Exception("Redis connection error"),
            ):
                tracker = await get_refusal_tracker()

                assert tracker is None
        finally:
            module._refusal_tracker_instance = original

    @pytest.mark.asyncio
    async def test_uses_existing_instance(self):
        """Test uses existing instance if already set."""
        import src.services.refusal_tracker as module
        original = module._refusal_tracker_instance

        try:
            existing = RefusalTracker(MagicMock())
            module._refusal_tracker_instance = existing

            tracker = await get_refusal_tracker()

            assert tracker is existing
        finally:
            module._refusal_tracker_instance = original


class TestRecordRefusalTimestamp:
    """Test timestamp handling in record_refusal."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock redis."""
        redis = MagicMock()
        redis.lpush = AsyncMock(return_value=1)
        redis.expire = AsyncMock(return_value=True)
        return redis

    @pytest.mark.asyncio
    async def test_includes_timestamp_in_refusal(self, mock_redis):
        """Test refusal includes timestamp."""
        import json
        tracker = RefusalTracker(mock_redis)

        await tracker.record_refusal(
            session_id="session_123",
            refusal_type=RefusalTracker.REFUSAL_BANK_NOT_FOUND,
            entity="Test",
        )

        call_args = mock_redis.lpush.call_args
        stored_json = call_args[0][1]
        stored_data = json.loads(stored_json)

        assert "timestamp" in stored_data
        # Should be ISO format
        assert "T" in stored_data["timestamp"]


class TestCheckPreviousRefusalEdgeCases:
    """Additional edge cases for check_previous_refusal."""

    @pytest.mark.asyncio
    async def test_handles_empty_refusals_list(self):
        """Test handles empty refusals list."""
        mock_redis = MagicMock()
        mock_redis.lrange = AsyncMock(return_value=[])
        tracker = RefusalTracker(mock_redis)

        result = await tracker.check_previous_refusal("session_123", "Test")

        assert result is None

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_entity(self):
        """Test strips whitespace when comparing entities."""
        mock_redis = MagicMock()
        mock_redis.lrange = AsyncMock(
            return_value=['{"type": "bank_not_found", "entity": "BANCO XYZ"}']
        )
        tracker = RefusalTracker(mock_redis)

        result = await tracker.check_previous_refusal("session_123", "  Banco XYZ  ")

        assert result is not None

    @pytest.mark.asyncio
    async def test_checks_multiple_refusals(self):
        """Test checks through multiple refusals to find match."""
        mock_redis = MagicMock()
        mock_redis.lrange = AsyncMock(
            return_value=[
                '{"type": "bank_not_found", "entity": "BANK_A"}',
                '{"type": "bank_not_found", "entity": "BANK_B"}',
                '{"type": "bank_not_found", "entity": "BANCO XYZ"}',
            ]
        )
        tracker = RefusalTracker(mock_redis)

        result = await tracker.check_previous_refusal("session_123", "Banco XYZ")

        assert result is not None
        assert result["entity"] == "BANCO XYZ"


class TestBuildConsistencyPromptMetricNotFound:
    """Additional tests for metric_not_found prompt."""

    def test_metric_prompt_discourages_inventing_values(self):
        """Test metric prompt discourages inventing values."""
        tracker = RefusalTracker(None)
        refusal = {
            "type": RefusalTracker.REFUSAL_METRIC_NOT_FOUND,
            "entity": "INVALID_METRIC",
        }

        prompt = tracker.build_consistency_prompt(refusal)

        assert "NO inventes" in prompt or "no inventes" in prompt.lower()
        assert "valores" in prompt.lower() or "métrica" in prompt.lower()
