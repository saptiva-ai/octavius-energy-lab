"""
Unit tests for Chat Helpers

Tests:
- build_chat_context
- is_document_ready_and_cached
- wait_for_documents_ready
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime
import sys
import os
import asyncio

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..', 'src'))

from src.services.chat_helpers import (
    build_chat_context,
    is_document_ready_and_cached,
    wait_for_documents_ready
)
from src.schemas.chat import ChatRequest
from src.core.config import Settings
from src.models.document import Document, DocumentStatus

pytestmark = [pytest.mark.unit]


@pytest.fixture
def mock_settings():
    """Mock application settings"""
    settings = Mock(spec=Settings)
    settings.deep_research_kill_switch = False
    return settings


@pytest.mark.unit
class TestBuildChatContext:
    """Test build_chat_context function"""

    def test_builds_basic_context(self, mock_settings, monkeypatch):
        """Should build context with defaults"""
        # Sin modelo en el request se cae a default_chat_model() ->
        # get_settings() (cacheado), que refleja CHAT_DEFAULT_MODEL del
        # entorno; fijar el default real para no depender de envs/.env.
        from types import SimpleNamespace

        monkeypatch.setattr(
            "src.core.config.get_settings",
            lambda: SimpleNamespace(chat_default_model="Saptiva Turbo"),
        )
        request = ChatRequest(
            message="Hello",
            chat_id="chat-123"
        )
        user_id = "user-123"

        context = build_chat_context(request, user_id, mock_settings)

        assert context.user_id == user_id
        assert context.chat_id == "chat-123"
        assert context.message == "Hello"
        assert context.model == "Saptiva Turbo"  # Default
        assert context.stream is True  # Default in ChatRequest is True
        assert context.kill_switch_active is False
        assert context.document_ids is None

    def test_merges_document_ids(self, mock_settings):
        """Should merge file_ids and document_ids"""
        request = ChatRequest(
            message="Analyze this",
            chat_id="chat-123",
            file_ids=["file-1"],
            document_ids=["doc-2"]
        )
        
        context = build_chat_context(request, "user-123", mock_settings)
        
        assert context.document_ids == ["file-1", "doc-2"]

    def test_normalizes_tools(self, mock_settings):
        """Should normalize tools enabled state"""
        request = ChatRequest(
            message="Research",
            chat_id="chat-123",
            tools_enabled={"deep_research": True}
        )
        
        context = build_chat_context(request, "user-123", mock_settings)
        
        assert context.tools_enabled["deep_research"] is True
        # Should include defaults from normalize_tools_state
        assert "web_search" in context.tools_enabled


@pytest.mark.unit
class TestDocumentReadiness:
    """Test document readiness helpers"""

    @pytest.mark.asyncio
    async def test_is_document_ready_success(self):
        """Should return True when doc is ready and cached"""
        mock_doc = Mock(spec=Document)
        mock_doc.user_id = "user-123"
        mock_doc.status = DocumentStatus.READY
        
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "cached content"

        with patch('src.models.document.Document.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_doc
            
            result = await is_document_ready_and_cached(
                file_id="doc-123",
                user_id="user-123",
                redis_client=mock_redis
            )
            
            assert result is True
            mock_redis.get.assert_called_once_with("doc:text:doc-123")

    @pytest.mark.asyncio
    async def test_is_document_ready_fails_ownership(self):
        """Should return False if user doesn't own document"""
        mock_doc = Mock(spec=Document)
        mock_doc.user_id = "other-user"
        mock_doc.status = DocumentStatus.READY
        
        mock_redis = AsyncMock()

        with patch('src.models.document.Document.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_doc
            
            result = await is_document_ready_and_cached(
                file_id="doc-123",
                user_id="user-123",
                redis_client=mock_redis
            )
            
            assert result is False
            mock_redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_wait_for_documents_returns_early(self):
        """Should return early if all docs are ready"""
        mock_redis = AsyncMock()
        
        with patch('src.services.chat_helpers.is_document_ready_and_cached', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True
            
            await wait_for_documents_ready(
                file_ids=["doc-1", "doc-2"],
                user_id="user-123",
                redis_client=mock_redis,
                max_wait_ms=1000
            )
            
            assert mock_check.call_count == 2  # Checked both once

    @pytest.mark.asyncio
    async def test_wait_for_documents_timeouts(self):
        """Should verify timeout logic works (called multiple times)"""
        mock_redis = AsyncMock()

        with patch('src.services.chat_helpers.is_document_ready_and_cached', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = False  # Never ready

            # Small max_wait to fail fast
            await wait_for_documents_ready(
                file_ids=["doc-1"],
                user_id="user-123",
                redis_client=mock_redis,
                max_wait_ms=50,  # 50ms wait
                step_ms=20       # 20ms poll
            )

            # Should have been called at least twice (0ms, 20ms, 40ms)
            assert mock_check.call_count >= 2


class TestIsDocumentReadyAndCachedEdgeCases:
    """Additional edge case tests for is_document_ready_and_cached."""

    @pytest.mark.asyncio
    async def test_returns_false_for_empty_file_id(self):
        """Should return False when file_id is empty."""
        mock_redis = AsyncMock()

        result = await is_document_ready_and_cached(
            file_id="",
            user_id="user-123",
            redis_client=mock_redis
        )

        assert result is False
        mock_redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_for_none_file_id(self):
        """Should return False when file_id is None."""
        mock_redis = AsyncMock()

        result = await is_document_ready_and_cached(
            file_id=None,
            user_id="user-123",
            redis_client=mock_redis
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_document_lookup_exception(self):
        """Should return False when Document.get raises exception."""
        mock_redis = AsyncMock()

        with patch('src.models.document.Document.get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Database error")

            result = await is_document_ready_and_cached(
                file_id="doc-123",
                user_id="user-123",
                redis_client=mock_redis
            )

            assert result is False
            mock_redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_when_document_not_found(self):
        """Should return False when document doesn't exist."""
        mock_redis = AsyncMock()

        with patch('src.models.document.Document.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await is_document_ready_and_cached(
                file_id="doc-123",
                user_id="user-123",
                redis_client=mock_redis
            )

            assert result is False
            mock_redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_when_document_not_ready(self):
        """Should return False when document status is PROCESSING."""
        mock_doc = Mock(spec=Document)
        mock_doc.user_id = "user-123"
        mock_doc.status = DocumentStatus.PROCESSING

        mock_redis = AsyncMock()

        with patch('src.models.document.Document.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_doc

            result = await is_document_ready_and_cached(
                file_id="doc-123",
                user_id="user-123",
                redis_client=mock_redis
            )

            assert result is False
            mock_redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_when_document_status_failed(self):
        """Should return False when document status is FAILED."""
        mock_doc = Mock(spec=Document)
        mock_doc.user_id = "user-123"
        mock_doc.status = DocumentStatus.FAILED

        mock_redis = AsyncMock()

        with patch('src.models.document.Document.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_doc

            result = await is_document_ready_and_cached(
                file_id="doc-123",
                user_id="user-123",
                redis_client=mock_redis
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_redis_exception(self):
        """Should return False when Redis raises exception."""
        mock_doc = Mock(spec=Document)
        mock_doc.user_id = "user-123"
        mock_doc.status = DocumentStatus.READY

        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis connection error")

        with patch('src.models.document.Document.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_doc

            result = await is_document_ready_and_cached(
                file_id="doc-123",
                user_id="user-123",
                redis_client=mock_redis
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_cache_empty(self):
        """Should return False when cache value is None."""
        mock_doc = Mock(spec=Document)
        mock_doc.user_id = "user-123"
        mock_doc.status = DocumentStatus.READY

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Not cached

        with patch('src.models.document.Document.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_doc

            result = await is_document_ready_and_cached(
                file_id="doc-123",
                user_id="user-123",
                redis_client=mock_redis
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_cache_empty_string(self):
        """Should return False when cache value is empty string."""
        mock_doc = Mock(spec=Document)
        mock_doc.user_id = "user-123"
        mock_doc.status = DocumentStatus.READY

        mock_redis = AsyncMock()
        mock_redis.get.return_value = ""  # Empty string

        with patch('src.models.document.Document.get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_doc

            result = await is_document_ready_and_cached(
                file_id="doc-123",
                user_id="user-123",
                redis_client=mock_redis
            )

            assert result is False


class TestWaitForDocumentsReadyEdgeCases:
    """Additional edge case tests for wait_for_documents_ready."""

    @pytest.mark.asyncio
    async def test_returns_early_for_empty_list(self):
        """Should return immediately for empty file_ids list."""
        mock_redis = AsyncMock()

        with patch('src.services.chat_helpers.is_document_ready_and_cached', new_callable=AsyncMock) as mock_check:
            await wait_for_documents_ready(
                file_ids=[],
                user_id="user-123",
                redis_client=mock_redis
            )

            mock_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_for_none_list(self):
        """Should handle None file_ids gracefully."""
        mock_redis = AsyncMock()

        with patch('src.services.chat_helpers.is_document_ready_and_cached', new_callable=AsyncMock) as mock_check:
            # The function checks 'if not file_ids' so None should be handled
            await wait_for_documents_ready(
                file_ids=None,
                user_id="user-123",
                redis_client=mock_redis
            )

            mock_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_removes_duplicate_file_ids(self):
        """Should deduplicate file_ids before checking."""
        mock_redis = AsyncMock()

        with patch('src.services.chat_helpers.is_document_ready_and_cached', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True

            await wait_for_documents_ready(
                file_ids=["doc-1", "doc-1", "doc-2", "doc-1"],
                user_id="user-123",
                redis_client=mock_redis
            )

            # Should only check unique IDs: doc-1 and doc-2
            assert mock_check.call_count == 2

    @pytest.mark.asyncio
    async def test_documents_become_ready_after_waiting(self):
        """Should detect documents becoming ready after initial poll."""
        mock_redis = AsyncMock()
        call_count = 0

        async def check_ready(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First two calls return False, then True
            return call_count > 2

        with patch('src.services.chat_helpers.is_document_ready_and_cached', new_callable=AsyncMock) as mock_check:
            mock_check.side_effect = check_ready

            await wait_for_documents_ready(
                file_ids=["doc-1"],
                user_id="user-123",
                redis_client=mock_redis,
                max_wait_ms=500,
                step_ms=10
            )

            # Should have checked until ready
            assert call_count >= 3

    @pytest.mark.asyncio
    async def test_logs_when_waited_more_than_zero(self):
        """Should log when documents become ready after waiting."""
        mock_redis = AsyncMock()
        call_count = 0

        async def check_ready(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count > 1  # Ready on second call

        with patch('src.services.chat_helpers.is_document_ready_and_cached', new_callable=AsyncMock) as mock_check:
            mock_check.side_effect = check_ready

            # Should complete without error, with logging
            await wait_for_documents_ready(
                file_ids=["doc-1"],
                user_id="user-123",
                redis_client=mock_redis,
                max_wait_ms=200,
                step_ms=10
            )

            assert call_count >= 2


class TestBuildChatContextEdgeCases:
    """Additional edge case tests for build_chat_context."""

    @pytest.fixture
    def settings_with_kill_switch(self):
        """Settings with kill switch enabled."""
        settings = Mock(spec=Settings)
        settings.deep_research_kill_switch = True
        return settings

    def test_custom_model(self, mock_settings):
        """Should use custom model when specified."""
        request = ChatRequest(
            message="Hello",
            chat_id="chat-123",
            model="custom-model"
        )

        context = build_chat_context(request, "user-123", mock_settings)

        assert context.model == "custom-model"

    def test_kill_switch_enabled_no_attachments(self, settings_with_kill_switch):
        """Should enable kill switch when no attachments present."""
        request = ChatRequest(
            message="Research something",
            chat_id="chat-123"
        )

        context = build_chat_context(request, "user-123", settings_with_kill_switch)

        assert context.kill_switch_active is True

    def test_kill_switch_disabled_with_file_ids(self, settings_with_kill_switch):
        """Should disable kill switch when file_ids are present."""
        request = ChatRequest(
            message="Analyze this document",
            chat_id="chat-123",
            file_ids=["file-1"]
        )

        context = build_chat_context(request, "user-123", settings_with_kill_switch)

        assert context.kill_switch_active is False

    def test_kill_switch_disabled_with_document_ids(self, settings_with_kill_switch):
        """Should disable kill switch when document_ids are present."""
        request = ChatRequest(
            message="Analyze this document",
            chat_id="chat-123",
            document_ids=["doc-1"]
        )

        context = build_chat_context(request, "user-123", settings_with_kill_switch)

        assert context.kill_switch_active is False

    def test_only_file_ids_specified(self, mock_settings):
        """Should handle only file_ids (no document_ids)."""
        request = ChatRequest(
            message="Analyze",
            chat_id="chat-123",
            file_ids=["file-1", "file-2"]
        )

        context = build_chat_context(request, "user-123", mock_settings)

        assert context.document_ids == ["file-1", "file-2"]

    def test_only_document_ids_specified(self, mock_settings):
        """Should handle only document_ids (no file_ids)."""
        request = ChatRequest(
            message="Analyze",
            chat_id="chat-123",
            document_ids=["doc-1", "doc-2"]
        )

        context = build_chat_context(request, "user-123", mock_settings)

        assert context.document_ids == ["doc-1", "doc-2"]

    def test_empty_file_and_document_ids(self, mock_settings):
        """Should handle empty file_ids and document_ids lists."""
        request = ChatRequest(
            message="Hello",
            chat_id="chat-123",
            file_ids=[],
            document_ids=[]
        )

        context = build_chat_context(request, "user-123", mock_settings)

        assert context.document_ids is None

    def test_generates_unique_request_id(self, mock_settings):
        """Should generate unique request_id for each call."""
        request = ChatRequest(
            message="Hello",
            chat_id="chat-123"
        )

        context1 = build_chat_context(request, "user-123", mock_settings)
        context2 = build_chat_context(request, "user-123", mock_settings)

        assert context1.request_id != context2.request_id

    def test_timestamp_is_recent(self, mock_settings):
        """Should set timestamp close to current time."""
        request = ChatRequest(
            message="Hello",
            chat_id="chat-123"
        )

        before = datetime.utcnow()
        context = build_chat_context(request, "user-123", mock_settings)
        after = datetime.utcnow()

        assert before <= context.timestamp <= after

    def test_session_id_is_none(self, mock_settings):
        """Should set session_id to None (resolved later)."""
        request = ChatRequest(
            message="Hello",
            chat_id="chat-123"
        )

        context = build_chat_context(request, "user-123", mock_settings)

        assert context.session_id is None

    def test_context_field_passed_through(self, mock_settings):
        """Should pass through context field from request."""
        context_data = {"previous": "conversation context", "key": "value"}
        request = ChatRequest(
            message="Hello",
            chat_id="chat-123",
            context=context_data
        )

        context = build_chat_context(request, "user-123", mock_settings)

        assert context.context == context_data

    def test_tools_enabled_default(self, mock_settings):
        """Should use default tools when not specified."""
        request = ChatRequest(
            message="Hello",
            chat_id="chat-123"
        )

        context = build_chat_context(request, "user-123", mock_settings)

        # Should have normalized tools state (includes defaults)
        assert isinstance(context.tools_enabled, dict)


class TestBuildChatContextAttributeHandling:
    """Test attribute handling in build_chat_context."""

    @pytest.fixture
    def mock_settings(self):
        """Mock application settings."""
        settings = Mock(spec=Settings)
        settings.deep_research_kill_switch = False
        return settings

    def test_handles_missing_stream_attribute(self, mock_settings):
        """Should handle missing stream attribute with default."""
        # Create request without stream attribute
        request = MagicMock()
        request.message = "Hello"
        request.chat_id = "chat-123"
        request.file_ids = None
        request.document_ids = None
        request.model = None
        request.tools_enabled = None
        request.context = None
        del request.stream  # Remove stream attribute
        del request.temperature
        del request.max_tokens

        # Mock getattr to simulate missing attribute
        with patch('src.services.chat_helpers.normalize_tools_state', return_value={}):
            context = build_chat_context(request, "user-123", mock_settings)

        assert context.stream is False  # Default value

    def test_handles_temperature_attribute(self, mock_settings):
        """Should handle temperature attribute when present."""
        request = ChatRequest(
            message="Hello",
            chat_id="chat-123",
            temperature=0.7
        )

        context = build_chat_context(request, "user-123", mock_settings)

        assert context.temperature == 0.7

    def test_handles_max_tokens_attribute(self, mock_settings):
        """Should handle max_tokens attribute when present."""
        request = ChatRequest(
            message="Hello",
            chat_id="chat-123",
            max_tokens=500
        )

        context = build_chat_context(request, "user-123", mock_settings)

        assert context.max_tokens == 500
