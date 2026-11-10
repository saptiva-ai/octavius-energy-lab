"""
Unit tests for session_context_manager module.

Tests:
- SessionContextManager.normalize_file_ids
- SessionContextManager.determine_current_files
- SessionContextManager.wait_for_files_ready
- SessionContextManager.adopt_orphaned_files
- SessionContextManager.update_session_files
- SessionContextManager.prepare_session_context
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.session_context_manager import SessionContextManager

pytestmark = [pytest.mark.unit]


class TestNormalizeFileIds:
    """Test normalize_file_ids method."""

    def test_removes_duplicates(self):
        """Test removes duplicate file IDs."""
        file_ids = ["doc_1", "doc_2", "doc_1", "doc_3", "doc_2"]

        result = SessionContextManager.normalize_file_ids(file_ids)

        assert result == ["doc_1", "doc_2", "doc_3"]

    def test_preserves_order(self):
        """Test preserves first occurrence order."""
        file_ids = ["doc_3", "doc_1", "doc_2", "doc_1"]

        result = SessionContextManager.normalize_file_ids(file_ids)

        assert result == ["doc_3", "doc_1", "doc_2"]

    def test_returns_empty_for_empty_input(self):
        """Test returns empty list for empty input."""
        assert SessionContextManager.normalize_file_ids([]) == []

    def test_returns_empty_for_none(self):
        """Test returns empty list for None."""
        assert SessionContextManager.normalize_file_ids(None) == []

    def test_single_item(self):
        """Test single item list."""
        result = SessionContextManager.normalize_file_ids(["doc_1"])
        assert result == ["doc_1"]

    def test_no_duplicates(self):
        """Test list with no duplicates."""
        file_ids = ["doc_1", "doc_2", "doc_3"]
        result = SessionContextManager.normalize_file_ids(file_ids)
        assert result == file_ids


class TestDetermineCurrentFiles:
    """Test determine_current_files method."""

    def test_uses_request_files_when_provided(self):
        """Test uses request files when they exist."""
        request_files = ["new_doc_1", "new_doc_2"]
        session_files = ["old_doc_1"]

        result = SessionContextManager.determine_current_files(
            request_files, session_files
        )

        assert result == ["new_doc_1", "new_doc_2"]

    def test_uses_session_files_when_no_request_files(self):
        """Test reuses session files when request is empty."""
        request_files = []
        session_files = ["old_doc_1", "old_doc_2"]

        result = SessionContextManager.determine_current_files(
            request_files, session_files
        )

        assert result == ["old_doc_1", "old_doc_2"]

    def test_returns_empty_when_both_empty(self):
        """Test returns empty when both lists are empty."""
        result = SessionContextManager.determine_current_files([], [])
        assert result == []

    def test_request_files_override_session_files(self):
        """Test request files completely replace session files."""
        request_files = ["new_doc"]
        session_files = ["old_doc_1", "old_doc_2", "old_doc_3"]

        result = SessionContextManager.determine_current_files(
            request_files, session_files
        )

        assert result == ["new_doc"]
        assert "old_doc_1" not in result


class TestWaitForFilesReady:
    """Test wait_for_files_ready method."""

    @pytest.mark.asyncio
    async def test_returns_early_for_empty_list(self):
        """Test returns early when no files."""
        mock_cache = MagicMock()

        await SessionContextManager.wait_for_files_ready([], "user_123", mock_cache)

        # No exception means success

    @pytest.mark.asyncio
    @patch("src.services.session_context_manager.wait_for_documents_ready")
    async def test_calls_wait_for_documents_ready(self, mock_wait):
        """Test calls wait_for_documents_ready with correct args."""
        mock_wait.return_value = None
        mock_cache = MagicMock()
        mock_cache.client = MagicMock()

        await SessionContextManager.wait_for_files_ready(
            ["doc_1", "doc_2"], "user_123", mock_cache
        )

        mock_wait.assert_called_once_with(
            file_ids=["doc_1", "doc_2"],
            user_id="user_123",
            redis_client=mock_cache.client,
        )


class TestAdoptOrphanedFiles:
    """Test adopt_orphaned_files method."""

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_list(self):
        """Test returns 0 when no files to adopt."""
        result = await SessionContextManager.adopt_orphaned_files(
            file_ids=[],
            session_id="session_123",
            user_id="user_456",
        )

        assert result == 0

    @pytest.mark.asyncio
    async def test_adopts_files_successfully(self):
        """Test successfully adopts orphaned files."""
        with patch("src.models.document.Document") as mock_document:
            mock_update_result = MagicMock()
            mock_update_result.modified_count = 2
            mock_update_result.matched_count = 2

            mock_find = MagicMock()
            mock_find.update = AsyncMock(return_value=mock_update_result)
            mock_document.find_many.return_value = mock_find

            result = await SessionContextManager.adopt_orphaned_files(
                file_ids=["doc_1", "doc_2"],
                session_id="session_123",
                user_id="user_456",
            )

            assert result == 2
            mock_document.find_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_partial_adoption(self):
        """Test handles partial file adoption."""
        with patch("src.models.document.Document") as mock_document:
            mock_update_result = MagicMock()
            mock_update_result.modified_count = 1
            mock_update_result.matched_count = 1

            mock_find = MagicMock()
            mock_find.update = AsyncMock(return_value=mock_update_result)
            mock_document.find_many.return_value = mock_find

            result = await SessionContextManager.adopt_orphaned_files(
                file_ids=["doc_1", "doc_2"],  # Requested 2
                session_id="session_123",
                user_id="user_456",
            )

            assert result == 1  # Only 1 adopted

    @pytest.mark.asyncio
    async def test_returns_zero_on_exception(self):
        """Test returns 0 on exception."""
        with patch("src.models.document.Document") as mock_document:
            mock_document.find_many.side_effect = Exception("DB error")

            result = await SessionContextManager.adopt_orphaned_files(
                file_ids=["doc_1"],
                session_id="session_123",
                user_id="user_456",
            )

            assert result == 0

    @pytest.mark.asyncio
    async def test_handles_object_id_format(self):
        """Test handles ObjectId format file IDs."""
        with patch("src.models.document.Document") as mock_document:
            mock_update_result = MagicMock()
            mock_update_result.modified_count = 1
            mock_update_result.matched_count = 1

            mock_find = MagicMock()
            mock_find.update = AsyncMock(return_value=mock_update_result)
            mock_document.find_many.return_value = mock_find

            # Valid ObjectId format
            result = await SessionContextManager.adopt_orphaned_files(
                file_ids=["507f1f77bcf86cd799439011"],
                session_id="session_123",
                user_id="user_456",
            )

            assert result == 1


class TestUpdateSessionFiles:
    """Test update_session_files method."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_new_files(self):
        """Test returns False when no new files."""
        mock_session = MagicMock()

        result = await SessionContextManager.update_session_files(
            chat_session=mock_session,
            new_file_ids=[],
            previous_file_ids=["old_doc"],
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_files_unchanged(self):
        """Test returns False when files are same."""
        mock_session = MagicMock()

        result = await SessionContextManager.update_session_files(
            chat_session=mock_session,
            new_file_ids=["doc_1", "doc_2"],
            previous_file_ids=["doc_1", "doc_2"],
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_updates_session_when_files_changed(self):
        """Test updates session when files changed."""
        mock_session = MagicMock()
        mock_session.update = AsyncMock()
        mock_session.id = "session_123"

        result = await SessionContextManager.update_session_files(
            chat_session=mock_session,
            new_file_ids=["new_doc_1", "new_doc_2"],
            previous_file_ids=["old_doc"],
        )

        assert result is True
        mock_session.update.assert_called_once()
        assert mock_session.attached_file_ids == ["new_doc_1", "new_doc_2"]


class TestPrepareSessionContext:
    """Test prepare_session_context orchestration method."""

    @pytest.mark.asyncio
    @patch.object(SessionContextManager, "update_session_files")
    @patch.object(SessionContextManager, "wait_for_files_ready")
    @patch.object(SessionContextManager, "adopt_orphaned_files")
    async def test_full_workflow(
        self, mock_adopt, mock_wait, mock_update
    ):
        """Test full prepare session context workflow."""
        mock_adopt.return_value = 2
        mock_wait.return_value = None
        mock_update.return_value = True

        mock_session = MagicMock()
        mock_session.id = "session_123"
        mock_session.attached_file_ids = []

        mock_cache = MagicMock()

        result = await SessionContextManager.prepare_session_context(
            chat_session=mock_session,
            request_file_ids=["doc_1", "doc_2"],
            user_id="user_456",
            redis_cache=mock_cache,
            request_id="req_789",
        )

        assert result == ["doc_1", "doc_2"]
        mock_adopt.assert_called_once()
        mock_wait.assert_called_once()
        mock_update.assert_called_once()

    @pytest.mark.asyncio
    @patch.object(SessionContextManager, "update_session_files")
    @patch.object(SessionContextManager, "wait_for_files_ready")
    @patch.object(SessionContextManager, "adopt_orphaned_files")
    async def test_uses_session_files_when_request_empty(
        self, mock_adopt, mock_wait, mock_update
    ):
        """Test uses session files when request has no files."""
        mock_wait.return_value = None
        mock_update.return_value = False

        mock_session = MagicMock()
        mock_session.id = "session_123"
        mock_session.attached_file_ids = ["existing_doc"]

        mock_cache = MagicMock()

        result = await SessionContextManager.prepare_session_context(
            chat_session=mock_session,
            request_file_ids=[],
            user_id="user_456",
            redis_cache=mock_cache,
            request_id="req_789",
        )

        assert result == ["existing_doc"]
        # No adoption when no request files
        mock_adopt.assert_not_called()

    @pytest.mark.asyncio
    @patch.object(SessionContextManager, "update_session_files")
    @patch.object(SessionContextManager, "wait_for_files_ready")
    @patch.object(SessionContextManager, "adopt_orphaned_files")
    async def test_normalizes_duplicate_files(
        self, mock_adopt, mock_wait, mock_update
    ):
        """Test normalizes duplicate file IDs in request."""
        mock_adopt.return_value = 2
        mock_wait.return_value = None
        mock_update.return_value = True

        mock_session = MagicMock()
        mock_session.id = "session_123"
        mock_session.attached_file_ids = []

        mock_cache = MagicMock()

        result = await SessionContextManager.prepare_session_context(
            chat_session=mock_session,
            request_file_ids=["doc_1", "doc_2", "doc_1"],  # Duplicate
            user_id="user_456",
            redis_cache=mock_cache,
            request_id="req_789",
        )

        # Should have deduplicated
        assert result == ["doc_1", "doc_2"]

    @pytest.mark.asyncio
    @patch.object(SessionContextManager, "update_session_files")
    @patch.object(SessionContextManager, "wait_for_files_ready")
    @patch.object(SessionContextManager, "adopt_orphaned_files")
    async def test_skips_adoption_when_no_session_id(
        self, mock_adopt, mock_wait, mock_update
    ):
        """Test skips adoption when session has no ID."""
        mock_wait.return_value = None
        mock_update.return_value = True

        mock_session = MagicMock()
        mock_session.id = None
        mock_session.attached_file_ids = []

        mock_cache = MagicMock()

        await SessionContextManager.prepare_session_context(
            chat_session=mock_session,
            request_file_ids=["doc_1"],
            user_id="user_456",
            redis_cache=mock_cache,
            request_id="req_789",
        )

        # No adoption when session has no ID
        mock_adopt.assert_not_called()
