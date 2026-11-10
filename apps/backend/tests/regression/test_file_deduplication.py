"""
Regression Tests for File Deduplication

Tests que previenen regresión de bugs conocidos:
- BUG-001: Deduplication not working for same file uploaded twice
- BUG-002: Hash not being stored in metadata
- BUG-003: Duplicate detection failing across different users
- BUG-004: MinIO cleanup deleting duplicate file but not original
- BUG-005: Race condition when uploading same file concurrently

NOTE: These tests use mocking for Beanie ODM models. The key is to patch
the models at the module level where they're imported lazily, not where
they're defined.
"""

import pytest
import hashlib
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from src.services.resource_lifecycle_manager import get_resource_manager
from src.models.document import DocumentStatus


class TestFileDeduplicationRegression:
    """Regression tests for file deduplication.

    These tests verify the ResourceLifecycleManager's deduplication logic
    by mocking the Beanie Document model at the point of lazy import.
    """

    @pytest.fixture
    def sample_pdf_content(self):
        """Sample PDF content for testing."""
        return b"%PDF-1.4\n%Test PDF\nHello World"

    @pytest.fixture
    def sample_file_hash(self, sample_pdf_content):
        """Compute hash of sample file."""
        return hashlib.sha256(sample_pdf_content).hexdigest()

    @pytest.fixture
    def manager(self):
        """Get a fresh resource manager instance."""
        return get_resource_manager()

    @pytest.mark.asyncio
    async def test_bug_002_hash_stored_in_metadata(self, manager, sample_file_hash):
        """
        BUG-002: Hash not being stored in metadata.

        Regression test to ensure file hash is properly stored in
        document metadata for future deduplication.

        This test verifies that check_duplicate_file queries Document
        with the correct filter including file_hash and user_id.
        """
        # Create a mock Document class with async find_one
        mock_document_class = MagicMock()
        mock_document_class.find_one = AsyncMock(return_value=None)

        # Patch at the import location - the lazy import inside check_duplicate_file
        with patch.dict(
            "sys.modules",
            {"src.models.document": MagicMock(Document=mock_document_class)}
        ):
            # Force re-import by calling the method
            # Note: We need to patch where it's imported TO, not FROM
            with patch(
                "src.services.resource_lifecycle_manager.Document",
                mock_document_class,
                create=True
            ):
                # The method does a lazy import, so we mock at module level first
                import src.models.document as doc_module
                original_document = doc_module.Document
                doc_module.Document = mock_document_class

                try:
                    result = await manager.check_duplicate_file(sample_file_hash, "user123")
                finally:
                    doc_module.Document = original_document

        # Assert - find_one was called with correct query
        mock_document_class.find_one.assert_called_once_with({
            "metadata.file_hash": sample_file_hash,
            "user_id": "user123"
        })

        # Assert - No duplicate found
        assert result is None

    @pytest.mark.asyncio
    async def test_bug_003_duplicate_detection_respects_user_scope(
        self, manager, sample_file_hash
    ):
        """
        BUG-003: Duplicate detection failing across different users.

        Regression test to ensure deduplication is scoped per user.
        Same file uploaded by different users should NOT be deduplicated.
        """
        import src.models.document as doc_module

        # Mock document found for user1
        mock_existing_doc = MagicMock()
        mock_existing_doc.id = "doc123"

        mock_document_class = MagicMock()

        # First call (user1): document found
        # Second call (user2): no document found
        mock_document_class.find_one = AsyncMock(side_effect=[
            mock_existing_doc,  # user1 finds document
            None                # user2 doesn't find document
        ])

        original_document = doc_module.Document
        doc_module.Document = mock_document_class

        try:
            # Act - Check for user1 (should find)
            result1 = await manager.check_duplicate_file(sample_file_hash, "user1")

            # Act - Check for user2 (should NOT find - different user scope)
            result2 = await manager.check_duplicate_file(sample_file_hash, "user2")
        finally:
            doc_module.Document = original_document

        # Assert - Found for user1
        assert result1 == "doc123"

        # Assert - Not found for user2
        assert result2 is None

        # Assert - Both calls included user_id filter
        calls = mock_document_class.find_one.call_args_list
        assert len(calls) == 2

        # First call was for user1
        assert calls[0][0][0]["user_id"] == "user1"
        assert calls[0][0][0]["metadata.file_hash"] == sample_file_hash

        # Second call was for user2
        assert calls[1][0][0]["user_id"] == "user2"
        assert calls[1][0][0]["metadata.file_hash"] == sample_file_hash

    @pytest.mark.asyncio
    async def test_bug_004_cleanup_doesnt_delete_referenced_original(self, manager):
        """
        BUG-004: MinIO cleanup deleting duplicate file but not original.

        Regression test to ensure cleanup doesn't delete files that are
        still referenced by active chat sessions.
        """
        import src.models.document as doc_module
        import src.models.chat as chat_module
        from src.services import resource_lifecycle_manager as rlm_module

        # Mock old document
        mock_doc = MagicMock()
        mock_doc.id = "doc123"
        mock_doc.minio_path = "uploads/doc123.pdf"
        mock_doc.filename = "test.pdf"
        mock_doc.created_at = datetime.utcnow() - timedelta(days=10)
        mock_doc.delete = AsyncMock()

        # Mock Document class
        mock_document_class = MagicMock()
        mock_find_result = MagicMock()
        mock_find_result.to_list = AsyncMock(return_value=[mock_doc])
        mock_document_class.find = MagicMock(return_value=mock_find_result)

        # Mock ChatSession - active session exists (count > 0)
        mock_chat_session_class = MagicMock()
        mock_session_find_result = MagicMock()
        mock_session_find_result.count = AsyncMock(return_value=1)  # Active session!
        mock_chat_session_class.find = MagicMock(return_value=mock_session_find_result)

        # Mock file storage
        mock_storage = MagicMock()
        mock_storage.delete_file = AsyncMock()
        mock_get_storage = MagicMock(return_value=mock_storage)

        # Store originals
        original_document = doc_module.Document
        original_document_status = doc_module.DocumentStatus
        original_chat_session = chat_module.ChatSession

        # Apply mocks
        doc_module.Document = mock_document_class
        doc_module.DocumentStatus = DocumentStatus  # Keep real enum
        chat_module.ChatSession = mock_chat_session_class

        try:
            with patch.object(rlm_module, "get_file_storage", mock_get_storage, create=True):
                # We also need to patch the import inside the method
                with patch(
                    "src.services.resource_lifecycle_manager.get_file_storage",
                    mock_get_storage,
                    create=True
                ):
                    # Actually patch at file_storage module level
                    from src.services import file_storage as fs_module
                    original_get_storage = getattr(fs_module, "get_file_storage", None)
                    fs_module.get_file_storage = mock_get_storage

                    try:
                        deleted_count = await manager._cleanup_minio_files()
                    finally:
                        if original_get_storage:
                            fs_module.get_file_storage = original_get_storage
        finally:
            doc_module.Document = original_document
            doc_module.DocumentStatus = original_document_status
            chat_module.ChatSession = original_chat_session

        # Assert - Should NOT delete because active session exists
        assert deleted_count == 0
        mock_storage.delete_file.assert_not_called()
        mock_doc.delete.assert_not_called()


class TestDeduplicationEdgeCases:
    """Edge cases for file deduplication - pure unit tests."""

    @pytest.mark.asyncio
    async def test_different_files_same_size_not_deduplicated(self):
        """Test that files with same size but different content have different hashes."""
        manager = get_resource_manager()
        content1 = b"A" * 1000
        content2 = b"B" * 1000

        hash1 = await manager.compute_file_hash(content1)
        hash2 = await manager.compute_file_hash(content2)

        # Assert - Different hashes for different content
        assert hash1 != hash2

        # Assert - Same size
        assert len(content1) == len(content2)

    @pytest.mark.asyncio
    async def test_empty_file_deduplication(self):
        """Test deduplication works for empty files."""
        manager = get_resource_manager()
        content = b""

        hash1 = await manager.compute_file_hash(content)
        hash2 = await manager.compute_file_hash(content)

        # Assert - Same hash for empty files
        assert hash1 == hash2
        assert hash1 == hashlib.sha256(b"").hexdigest()

    @pytest.mark.asyncio
    async def test_very_large_file_deduplication(self):
        """Test deduplication works for large files."""
        manager = get_resource_manager()
        # 50 MB file
        content = b"X" * (50 * 1024 * 1024)

        hash_result = await manager.compute_file_hash(content)

        # Assert - Hash computed successfully
        assert len(hash_result) == 64
        assert hash_result == hashlib.sha256(content).hexdigest()

    @pytest.mark.asyncio
    async def test_hash_is_deterministic(self):
        """Test that hash computation is deterministic."""
        manager = get_resource_manager()
        content = b"Hello World! This is a test file."

        # Compute hash multiple times
        hashes = [await manager.compute_file_hash(content) for _ in range(5)]

        # Assert - All hashes are identical
        assert len(set(hashes)) == 1
        assert all(h == hashes[0] for h in hashes)

    @pytest.mark.asyncio
    async def test_hash_changes_with_single_byte_difference(self):
        """Test that even a single byte change produces different hash."""
        manager = get_resource_manager()
        content1 = b"Hello World!"
        content2 = b"Hello World?"  # Only last byte different

        hash1 = await manager.compute_file_hash(content1)
        hash2 = await manager.compute_file_hash(content2)

        # Assert - Hashes are completely different
        assert hash1 != hash2

        # Assert - Hashes don't share any common prefix (avalanche effect)
        assert hash1[:8] != hash2[:8]
