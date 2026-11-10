"""
Unit tests for File Context Persistence - MVP-FILE-CONTEXT

Tests the new attached_file_ids field and file merging logic to ensure
PDF context persists across multiple messages in a conversation.
"""

import pytest

from src.models.chat import ChatSession


@pytest.mark.unit
class TestChatSessionAttachedFileIds:
    """Test ChatSession.attached_file_ids field"""

    def test_chat_session_has_attached_file_ids_field(self):
        """Should have attached_file_ids field with default empty list"""
        # Use .construct() to bypass Beanie initialization in unit tests
        session = ChatSession.construct(
            id="test-session",
            title="Test Chat",
            user_id="user-123"
        )

        assert hasattr(session, 'attached_file_ids')
        assert isinstance(session.attached_file_ids, list)
        assert len(session.attached_file_ids) == 0

    def test_chat_session_stores_file_ids(self):
        """Should store multiple file IDs"""
        # Use .construct() to bypass Beanie initialization in unit tests
        session = ChatSession.construct(
            id="test-session",
            title="Test Chat",
            user_id="user-123",
            attached_file_ids=["file-1", "file-2", "file-3"]
        )

        assert len(session.attached_file_ids) == 3
        assert "file-1" in session.attached_file_ids
        assert "file-2" in session.attached_file_ids
        assert "file-3" in session.attached_file_ids

    def test_chat_session_file_ids_are_mutable(self):
        """Should allow adding/removing file IDs"""
        # Use .construct() to bypass Beanie initialization in unit tests
        session = ChatSession.construct(
            id="test-session",
            title="Test Chat",
            user_id="user-123",
            attached_file_ids=["file-1"]
        )

        # Add new file
        session.attached_file_ids.append("file-2")
        assert len(session.attached_file_ids) == 2

        # Remove file
        session.attached_file_ids.remove("file-1")
        assert len(session.attached_file_ids) == 1
        assert session.attached_file_ids[0] == "file-2"

    def test_chat_session_serialization_includes_file_ids(self):
        """Should serialize attached_file_ids when converting to dict"""
        # Use .construct() to bypass Beanie initialization in unit tests
        session = ChatSession.construct(
            id="test-session",
            title="Test Chat",
            user_id="user-123",
            attached_file_ids=["file-1", "file-2"]
        )

        # Convert to dict (Pydantic model_dump)
        session_dict = session.model_dump()

        assert "attached_file_ids" in session_dict
        assert session_dict["attached_file_ids"] == ["file-1", "file-2"]


@pytest.mark.unit
class TestFileIdsMergingLogic:
    """Test file_ids merging logic from chat router"""

    def test_merge_empty_lists_returns_empty(self):
        """Should return empty list when both are empty"""
        request_file_ids = []
        session_file_ids = []

        # Simulate merge logic: request + session
        all_file_ids = list(dict.fromkeys(request_file_ids + session_file_ids))

        assert all_file_ids == []

    def test_merge_request_only_returns_request(self):
        """Should return request file_ids when session is empty"""
        request_file_ids = ["file-1", "file-2"]
        session_file_ids = []

        all_file_ids = list(dict.fromkeys(request_file_ids + session_file_ids))

        assert all_file_ids == ["file-1", "file-2"]

    def test_merge_session_only_returns_session(self):
        """Should return session file_ids when request is empty"""
        request_file_ids = []
        session_file_ids = ["file-3", "file-4"]

        all_file_ids = list(dict.fromkeys(request_file_ids + session_file_ids))

        assert all_file_ids == ["file-3", "file-4"]

    def test_merge_both_deduplicates(self):
        """Should merge and deduplicate file_ids from both sources"""
        request_file_ids = ["file-1", "file-2"]
        session_file_ids = ["file-2", "file-3"]  # file-2 is duplicate

        all_file_ids = list(dict.fromkeys(request_file_ids + session_file_ids))

        # Should have 3 unique files
        assert len(all_file_ids) == 3
        assert "file-1" in all_file_ids
        assert "file-2" in all_file_ids
        assert "file-3" in all_file_ids

        # Request files should come first (order preserved)
        assert all_file_ids.index("file-1") < all_file_ids.index("file-3")

    def test_merge_prioritizes_request_order(self):
        """Should preserve request file order when merging"""
        request_file_ids = ["file-3", "file-1", "file-2"]
        session_file_ids = ["file-4", "file-5"]

        all_file_ids = list(dict.fromkeys(request_file_ids + session_file_ids))

        # Request files should appear first in their original order
        assert all_file_ids[0] == "file-3"
        assert all_file_ids[1] == "file-1"
        assert all_file_ids[2] == "file-2"
        # Then session files
        assert all_file_ids[3] == "file-4"
        assert all_file_ids[4] == "file-5"

    def test_merge_handles_none_values(self):
        """Should handle None values gracefully"""
        request_file_ids = None
        session_file_ids = ["file-1"]

        # Simulate router logic with None handling
        request_safe = request_file_ids or []
        session_safe = session_file_ids or []
        all_file_ids = list(dict.fromkeys(request_safe + session_safe))

        assert all_file_ids == ["file-1"]

    def test_merge_large_list_deduplication(self):
        """Should handle large lists with many duplicates efficiently"""
        request_file_ids = [f"file-{i}" for i in range(10)]
        session_file_ids = [f"file-{i}" for i in range(5, 15)]  # 5-9 are duplicates

        all_file_ids = list(dict.fromkeys(request_file_ids + session_file_ids))

        # Should have 15 unique files (0-14)
        assert len(all_file_ids) == 15
        assert all_file_ids == [f"file-{i}" for i in range(15)]


@pytest.mark.unit
class TestNewFileDetection:
    """Test logic for detecting new files in request"""

    def test_detects_all_new_files_when_session_empty(self):
        """Should detect all request files as new when session has none"""
        request_file_ids = ["file-1", "file-2"]
        session_file_ids = []

        new_file_ids = [fid for fid in request_file_ids if fid not in session_file_ids]

        assert len(new_file_ids) == 2
        assert new_file_ids == ["file-1", "file-2"]

    def test_detects_no_new_files_when_all_exist(self):
        """Should detect no new files when all already in session"""
        request_file_ids = ["file-1", "file-2"]
        session_file_ids = ["file-1", "file-2"]

        new_file_ids = [fid for fid in request_file_ids if fid not in session_file_ids]

        assert len(new_file_ids) == 0

    def test_detects_only_new_files(self):
        """Should detect only the new files not in session"""
        request_file_ids = ["file-1", "file-2", "file-3"]
        session_file_ids = ["file-1"]  # file-1 already exists

        new_file_ids = [fid for fid in request_file_ids if fid not in session_file_ids]

        assert len(new_file_ids) == 2
        assert new_file_ids == ["file-2", "file-3"]

    def test_empty_request_returns_no_new_files(self):
        """Should return empty when request has no files"""
        request_file_ids = []
        session_file_ids = ["file-1", "file-2"]

        new_file_ids = [fid for fid in request_file_ids if fid not in session_file_ids]

        assert len(new_file_ids) == 0


@pytest.mark.unit
class TestContextMergingScenarios:
    """Test realistic multi-turn conversation scenarios"""

    def test_first_message_with_file(self):
        """
        Scenario: User uploads PDF and asks first question
        Expected: Session stores file_id, context includes file
        """
        # Request: First message with file
        request_file_ids = ["pdf-123"]
        session_file_ids = []  # Empty session (new conversation)

        # Merge logic
        all_file_ids = list(dict.fromkeys(request_file_ids + session_file_ids))
        new_file_ids = [fid for fid in request_file_ids if fid not in session_file_ids]

        # Should have file in context
        assert all_file_ids == ["pdf-123"]
        # Should detect as new file
        assert new_file_ids == ["pdf-123"]
        # Session should be updated with this file
        updated_session_files = all_file_ids
        assert updated_session_files == ["pdf-123"]

    def test_second_message_without_file(self):
        """
        Scenario: User asks follow-up question without uploading again
        Expected: Context still includes file from session
        """
        # Request: Second message, no files
        request_file_ids = []
        session_file_ids = ["pdf-123"]  # File stored from first message

        # Merge logic
        all_file_ids = list(dict.fromkeys(request_file_ids + session_file_ids))
        new_file_ids = [fid for fid in request_file_ids if fid not in session_file_ids]

        # Should still have file in context (from session)
        assert all_file_ids == ["pdf-123"]
        # No new files
        assert new_file_ids == []
        # Session remains unchanged
        assert session_file_ids == ["pdf-123"]

    def test_third_message_adds_new_file(self):
        """
        Scenario: User uploads second document mid-conversation
        Expected: Both files in context
        """
        # Request: Third message with new file
        request_file_ids = ["pdf-456"]  # New file
        session_file_ids = ["pdf-123"]  # First file from earlier

        # Merge logic
        all_file_ids = list(dict.fromkeys(request_file_ids + session_file_ids))
        new_file_ids = [fid for fid in request_file_ids if fid not in session_file_ids]

        # Should have both files
        assert len(all_file_ids) == 2
        assert "pdf-123" in all_file_ids
        assert "pdf-456" in all_file_ids
        # New file detected
        assert new_file_ids == ["pdf-456"]
        # Session should be updated with both
        updated_session_files = all_file_ids
        assert len(updated_session_files) == 2

    def test_multiple_turns_maintain_context(self):
        """
        Scenario: Simulate 5 messages, file sent in first, none in others
        Expected: All 5 messages should have file in context
        """
        session_file_ids = []

        # Message 1: Upload file
        request_file_ids = ["pdf-123"]
        all_file_ids = list(dict.fromkeys(request_file_ids + session_file_ids))
        session_file_ids = all_file_ids  # Update session
        assert all_file_ids == ["pdf-123"]

        # Messages 2-5: No files uploaded
        for i in range(2, 6):
            request_file_ids = []  # No files
            all_file_ids = list(dict.fromkeys(request_file_ids + session_file_ids))

            # File should still be in context
            assert all_file_ids == ["pdf-123"]
            assert len(all_file_ids) == 1

        # After 5 messages, context still has file
        assert session_file_ids == ["pdf-123"]
