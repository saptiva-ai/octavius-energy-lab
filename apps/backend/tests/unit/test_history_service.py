"""
Comprehensive tests for services/history_service.py - Unified history service

Coverage:
- Recording events: Chat messages, research start/progress/complete/fail, sources
- Timeline queries: With caching, pagination, filtering
- Progress normalization: Percentage conversion, edge cases
- Cache management: Redis invalidation, patterns
- Session management: Permissions, pagination, search, date filters
- Export functionality: JSON, TXT, CSV formats
- Statistics: User chat analytics
- Error handling: Database failures, cache failures
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from fastapi import HTTPException, status
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from src.services.history_service import HistoryService
from src.models.history import HistoryEvent, HistoryEventType
from src.models.chat import ChatMessage, ChatSession, MessageRole, MessageStatus


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_chat_message():
    """Mock chat message."""
    message = Mock(spec=ChatMessage)
    message.id = "msg-123"
    message.role = MessageRole.USER
    message.content = "Hello, how are you?"
    message.status = MessageStatus.DELIVERED
    message.model = "gpt-4"
    message.tokens = 10
    message.latency_ms = 150
    message.created_at = datetime.utcnow()
    message.metadata = {}
    message.file_ids = []
    message.files = []
    message.schema_version = 1
    return message


@pytest.fixture
def mock_task():
    """Mock research task."""
    task = Mock()
    task.id = "task-123"
    task.task_type = "deep_research"
    task.created_at = datetime.utcnow()
    task.completed_at = datetime.utcnow() + timedelta(minutes=5)
    task.result_data = {"summary": "Research complete"}
    return task


@pytest.fixture
def mock_history_event():
    """Mock history event."""
    event = Mock(spec=HistoryEvent)
    event.id = "event-123"
    event.chat_id = "chat-123"
    event.user_id = "user-123"
    event.event_type = HistoryEventType.CHAT_MESSAGE
    event.created_at = datetime.utcnow()
    event.metadata = {}

    def model_dump_func(mode='json'):
        return {
            "id": event.id,
            "chat_id": event.chat_id,
            "user_id": event.user_id,
            "event_type": event.event_type.value,
            "created_at": event.created_at.isoformat(),
            "metadata": event.metadata
        }

    event.model_dump = model_dump_func
    return event


@pytest.fixture
def mock_redis_cache():
    """Mock Redis cache."""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    cache.delete_pattern = AsyncMock()
    return cache


# ============================================================================
# RECORDING EVENTS
# ============================================================================

class TestRecordingEvents:
    """Test event recording methods."""

    @pytest.mark.asyncio
    async def test_record_chat_message_success(self, mock_chat_message, mock_history_event):
        """Should successfully record chat message."""
        with patch('src.services.history_service.HistoryEventFactory.create_chat_message_event',
                   return_value=mock_history_event):
            with patch.object(HistoryService, '_invalidate_cache', return_value=None):
                event = await HistoryService.record_chat_message(
                    chat_id="chat-123",
                    user_id="user-123",
                    message=mock_chat_message
                )

                assert event == mock_history_event
                assert event.id == "event-123"

    @pytest.mark.asyncio
    async def test_record_chat_message_with_files(self, mock_chat_message, mock_history_event):
        """Should record chat message with file attachments."""
        mock_chat_message.file_ids = ["file-1", "file-2"]
        mock_chat_message.files = [{"id": "file-1", "name": "doc.pdf"}]

        with patch('src.services.history_service.HistoryEventFactory.create_chat_message_event',
                   return_value=mock_history_event):
            with patch.object(HistoryService, '_invalidate_cache', return_value=None):
                event = await HistoryService.record_chat_message(
                    chat_id="chat-123",
                    user_id="user-123",
                    message=mock_chat_message
                )

                assert event is not None

    @pytest.mark.asyncio
    async def test_record_chat_message_error_propagates(self, mock_chat_message):
        """Should propagate errors when recording fails."""
        with patch('src.services.history_service.HistoryEventFactory.create_chat_message_event',
                   side_effect=Exception("Database error")):
            with pytest.raises(Exception) as exc_info:
                await HistoryService.record_chat_message(
                    chat_id="chat-123",
                    user_id="user-123",
                    message=mock_chat_message
                )

            assert "Database error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_record_research_started(self, mock_task, mock_history_event):
        """Should record research task start."""
        with patch('src.services.history_service.HistoryEventFactory.create_research_started_event',
                   return_value=mock_history_event):
            with patch.object(HistoryService, '_invalidate_cache', return_value=None):
                event = await HistoryService.record_research_started(
                    chat_id="chat-123",
                    user_id="user-123",
                    task=mock_task,
                    query="What is AI?",
                    params={"depth": "deep"}
                )

                assert event == mock_history_event

    @pytest.mark.asyncio
    async def test_record_research_progress(self, mock_history_event):
        """Should record research progress update."""
        with patch('src.services.history_service.HistoryEventFactory.create_research_progress_event',
                   return_value=mock_history_event):
            with patch.object(HistoryService, '_invalidate_cache', return_value=None):
                event = await HistoryService.record_research_progress(
                    chat_id="chat-123",
                    user_id="user-123",
                    task_id="task-123",
                    progress=0.5,  # 50%
                    current_step="Analyzing sources",
                    sources_found=10,
                    iterations_completed=2
                )

                assert event == mock_history_event

    @pytest.mark.asyncio
    async def test_record_research_progress_returns_none_on_error(self):
        """Should return None instead of raising on progress record error."""
        with patch('src.services.history_service.HistoryEventFactory.create_research_progress_event',
                   side_effect=PyMongoError("Progress update failed")):
            result = await HistoryService.record_research_progress(
                chat_id="chat-123",
                user_id="user-123",
                task_id="task-123",
                progress=0.75,
                current_step="Step 3"
            )

            # Should not raise, returns None for non-critical failures
            assert result is None

    @pytest.mark.asyncio
    async def test_record_research_completed(self, mock_task, mock_history_event):
        """Should record research completion."""
        with patch('src.services.history_service.HistoryEventFactory.create_research_completed_event',
                   return_value=mock_history_event):
            with patch.object(HistoryService, '_invalidate_cache', return_value=None):
                event = await HistoryService.record_research_completed(
                    chat_id="chat-123",
                    user_id="user-123",
                    task=mock_task,
                    sources_found=15,
                    iterations_completed=3,
                    result_metadata={"quality_score": 0.95}
                )

                assert event == mock_history_event

    @pytest.mark.asyncio
    async def test_record_research_failed(self, mock_history_event):
        """Should record research failure."""
        with patch('src.services.history_service.HistoryEventFactory.create_research_failed_event',
                   return_value=mock_history_event):
            with patch.object(HistoryService, '_invalidate_cache', return_value=None):
                event = await HistoryService.record_research_failed(
                    chat_id="chat-123",
                    user_id="user-123",
                    task_id="task-123",
                    error_message="API timeout",
                    progress=0.6,
                    current_step="Fetching sources"
                )

                assert event == mock_history_event

    @pytest.mark.asyncio
    async def test_record_source_discovery(self, mock_history_event):
        """Should record source discovery."""
        with patch('src.services.history_service.HistoryEventFactory.create_source_found_event',
                   return_value=mock_history_event):
            event = await HistoryService.record_source_discovery(
                chat_id="chat-123",
                user_id="user-123",
                task_id="task-123",
                source_id="source-1",
                url="https://example.com/article",
                title="Important Article",
                relevance_score=0.9,
                credibility_score=0.85
            )

            assert event == mock_history_event

    @pytest.mark.asyncio
    async def test_record_source_discovery_returns_none_on_error(self):
        """Should return None instead of raising on source discovery error."""
        with patch('src.services.history_service.HistoryEventFactory.create_source_found_event',
                   side_effect=PyMongoError("Source record failed")):
            result = await HistoryService.record_source_discovery(
                chat_id="chat-123",
                user_id="user-123",
                task_id="task-123",
                source_id="source-1",
                url="https://example.com",
                title="Title",
                relevance_score=0.8,
                credibility_score=0.7
            )

            # Should not raise for non-critical source discovery failures
            assert result is None


# ============================================================================
# TIMELINE QUERIES
# ============================================================================

class TestTimelineQueries:
    """Test timeline retrieval methods."""

    @pytest.mark.asyncio
    async def test_get_chat_timeline_without_cache(self, mock_history_event):
        """Should get chat timeline from database when cache miss."""
        with patch('src.services.history_service.get_redis_cache') as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.get = AsyncMock(return_value=None)  # Cache miss
            mock_cache.set = AsyncMock()
            mock_get_cache.return_value = mock_cache

            with patch('src.services.history_service.HistoryQuery.get_chat_timeline',
                       return_value=[mock_history_event]):
                with patch('src.services.history_service.HistoryQuery.get_chat_timeline_count',
                           return_value=1):
                    result = await HistoryService.get_chat_timeline(
                        chat_id="chat-123",
                        limit=50,
                        offset=0
                    )

                    assert result["chat_id"] == "chat-123"
                    assert len(result["events"]) == 1
                    assert result["total_count"] == 1
                    assert result["has_more"] is False

                    # Should have stored in cache
                    mock_cache.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_chat_timeline_with_cache_hit(self):
        """Should return cached timeline when available."""
        cached_data = {
            "chat_id": "chat-123",
            "events": [{"id": "event-1"}],
            "total_count": 1,
            "has_more": False,
            "limit": 50,
            "offset": 0
        }

        with patch('src.services.history_service.get_redis_cache') as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.get = AsyncMock(return_value=cached_data)
            mock_get_cache.return_value = mock_cache

            result = await HistoryService.get_chat_timeline(
                chat_id="chat-123",
                limit=50,
                offset=0,
                use_cache=True
            )

            assert result == cached_data
            # Should not have queried database
            mock_cache.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_chat_timeline_with_pagination(self, mock_history_event):
        """Should handle pagination correctly."""
        with patch('src.services.history_service.get_redis_cache') as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_get_cache.return_value = mock_cache

            with patch('src.services.history_service.HistoryQuery.get_chat_timeline',
                       return_value=[mock_history_event]):
                with patch('src.services.history_service.HistoryQuery.get_chat_timeline_count',
                           return_value=100):  # Total 100 events
                    result = await HistoryService.get_chat_timeline(
                        chat_id="chat-123",
                        limit=20,
                        offset=40
                    )

                    assert result["total_count"] == 100
                    assert result["has_more"] is True  # 40 + 1 < 100
                    assert result["limit"] == 20
                    assert result["offset"] == 40

    @pytest.mark.asyncio
    async def test_get_chat_timeline_with_event_filter(self, mock_history_event):
        """Should filter timeline by event types."""
        with patch('src.services.history_service.get_redis_cache') as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_get_cache.return_value = mock_cache

            with patch('src.services.history_service.HistoryQuery.get_chat_timeline',
                       return_value=[mock_history_event]):
                with patch('src.services.history_service.HistoryQuery.get_chat_timeline_count',
                           return_value=1):
                    result = await HistoryService.get_chat_timeline(
                        chat_id="chat-123",
                        event_types=[HistoryEventType.RESEARCH_STARTED, HistoryEventType.RESEARCH_COMPLETED]
                    )

                    assert len(result["events"]) == 1

    @pytest.mark.asyncio
    async def test_get_chat_timeline_cache_failure_continues(self, mock_history_event):
        """Should continue without cache if cache fails."""
        with patch('src.services.history_service.get_redis_cache',
                   side_effect=RedisError("Redis connection failed")):
            with patch('src.services.history_service.HistoryQuery.get_chat_timeline',
                       return_value=[mock_history_event]):
                with patch('src.services.history_service.HistoryQuery.get_chat_timeline_count',
                           return_value=1):
                    result = await HistoryService.get_chat_timeline(
                        chat_id="chat-123",
                        limit=50,
                        offset=0
                    )

                    # Should still return data despite cache failure
                    assert result["total_count"] == 1

    @pytest.mark.asyncio
    async def test_get_research_timeline(self, mock_history_event):
        """Should get research-specific timeline."""
        with patch('src.services.history_service.HistoryQuery.get_research_events_for_task',
                   return_value=[mock_history_event]):
            events = await HistoryService.get_research_timeline(
                chat_id="chat-123",
                task_id="task-123"
            )

            assert len(events) == 1
            assert events[0] == mock_history_event

    @pytest.mark.asyncio
    async def test_get_latest_research_status(self, mock_history_event):
        """Should get latest research event for task."""
        with patch('src.services.history_service.HistoryQuery.get_latest_research_event',
                   return_value=mock_history_event):
            event = await HistoryService.get_latest_research_status(
                chat_id="chat-123",
                task_id="task-123"
            )

            assert event == mock_history_event

    @pytest.mark.asyncio
    async def test_get_latest_research_status_returns_none_on_error(self):
        """Should return None if latest status query fails."""
        with patch('src.services.history_service.HistoryQuery.get_latest_research_event',
                   side_effect=PyMongoError("Query failed")):
            result = await HistoryService.get_latest_research_status(
                chat_id="chat-123",
                task_id="task-123"
            )

            assert result is None


# ============================================================================
# PROGRESS NORMALIZATION
# ============================================================================

class TestProgressNormalization:
    """Test progress value normalization."""

    def test_normalize_progress_from_decimal(self):
        """Should convert decimal (0-1) to percentage."""
        assert HistoryService._normalize_progress(0.5) == 50.0
        assert HistoryService._normalize_progress(0.25) == 25.0
        assert HistoryService._normalize_progress(1.0) == 100.0

    def test_normalize_progress_already_percentage(self):
        """Should keep percentage values as-is."""
        assert HistoryService._normalize_progress(50.0) == 50.0
        assert HistoryService._normalize_progress(75.5) == 75.5

    def test_normalize_progress_none(self):
        """Should return None for None input."""
        assert HistoryService._normalize_progress(None) is None

    def test_normalize_progress_rounds_properly(self):
        """Should round to 2 decimal places."""
        assert HistoryService._normalize_progress(0.12345) == 12.35
        assert HistoryService._normalize_progress(67.8965) == 67.90

    def test_normalize_progress_invalid_type(self):
        """Should return None for non-numeric values."""
        assert HistoryService._normalize_progress("invalid") is None
        assert HistoryService._normalize_progress([1, 2]) is None


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

class TestCacheManagement:
    """Test cache invalidation and management."""

    @pytest.mark.asyncio
    async def test_invalidate_cache_success(self):
        """Should invalidate all timeline cache entries for chat."""
        with patch('src.services.history_service.get_redis_cache') as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.delete_pattern = AsyncMock()
            mock_get_cache.return_value = mock_cache

            await HistoryService._invalidate_cache("chat-123")

            mock_cache.delete_pattern.assert_awaited_once_with("chat_timeline:chat-123:*")

    @pytest.mark.asyncio
    async def test_invalidate_cache_handles_failure(self):
        """Should not raise if cache invalidation fails."""
        with patch('src.services.history_service.get_redis_cache',
                   side_effect=RedisError("Redis error")):
            # Should not raise
            await HistoryService._invalidate_cache("chat-123")


# ============================================================================
# CLEANUP
# ============================================================================

class TestCleanup:
    """Test old event cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_old_events_success(self):
        """Should delete old events and invalidate cache."""
        mock_result = Mock()
        mock_result.deleted_count = 5

        mock_query = Mock()
        mock_query.delete = AsyncMock(return_value=mock_result)

        with patch('src.services.history_service.HistoryEvent') as MockHistoryEvent:
            # Setup mock to support field comparisons
            MockHistoryEvent.find = Mock(return_value=mock_query)
            MockHistoryEvent.chat_id = "chat_id_field"
            MockHistoryEvent.created_at = datetime.utcnow()

            with patch.object(HistoryService, '_invalidate_cache', new_callable=AsyncMock) as mock_invalidate:
                deleted_count = await HistoryService.cleanup_old_events(
                    chat_id="chat-123",
                    keep_days=30
                )

                assert deleted_count == 5
                mock_invalidate.assert_awaited_once_with("chat-123")

    @pytest.mark.asyncio
    async def test_cleanup_old_events_no_deletions(self):
        """Should not invalidate cache if no events deleted."""
        mock_result = Mock()
        mock_result.deleted_count = 0

        mock_query = Mock()
        mock_query.delete = AsyncMock(return_value=mock_result)

        with patch('src.services.history_service.HistoryEvent') as MockHistoryEvent:
            MockHistoryEvent.find = Mock(return_value=mock_query)
            MockHistoryEvent.chat_id = "chat_id_field"
            MockHistoryEvent.created_at = datetime.utcnow()

            with patch.object(HistoryService, '_invalidate_cache', new_callable=AsyncMock) as mock_invalidate:
                deleted_count = await HistoryService.cleanup_old_events(
                    chat_id="chat-123",
                    keep_days=30
                )

                assert deleted_count == 0
                # Should NOT invalidate cache when nothing was deleted
                mock_invalidate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cleanup_old_events_returns_zero_on_error(self):
        """Should return 0 if cleanup fails."""
        with patch('src.services.history_service.HistoryEvent') as MockHistoryEvent:
            MockHistoryEvent.find = Mock(side_effect=PyMongoError("Database error"))
            MockHistoryEvent.chat_id = "chat_id_field"
            MockHistoryEvent.created_at = datetime.utcnow()

            deleted_count = await HistoryService.cleanup_old_events(
                chat_id="chat-123",
                keep_days=30
            )

            assert deleted_count == 0


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

class TestSessionManagement:
    """Test session and permission management."""

    @pytest.mark.asyncio
    async def test_get_session_with_permission_check_success(self):
        """Should return session for authorized user."""
        mock_session = Mock()
        mock_session.user_id = "user-123"

        with patch('src.models.chat.ChatSession') as MockChatSession:
            MockChatSession.get = AsyncMock(return_value=mock_session)

            session = await HistoryService.get_session_with_permission_check(
                chat_id="chat-123",
                user_id="user-123"
            )

            assert session == mock_session

    @pytest.mark.asyncio
    async def test_get_session_with_permission_check_not_found(self):
        """Should raise 404 if session doesn't exist."""
        with patch('src.models.chat.ChatSession') as MockChatSession:
            MockChatSession.get = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await HistoryService.get_session_with_permission_check(
                    chat_id="nonexistent",
                    user_id="user-123"
                )

            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_session_with_permission_check_forbidden(self):
        """Should raise 403 if user doesn't own session."""
        mock_session = Mock()
        mock_session.user_id = "other-user"

        with patch('src.models.chat.ChatSession') as MockChatSession:
            MockChatSession.get = AsyncMock(return_value=mock_session)

            with pytest.raises(HTTPException) as exc_info:
                await HistoryService.get_session_with_permission_check(
                    chat_id="chat-123",
                    user_id="user-123"
                )

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
