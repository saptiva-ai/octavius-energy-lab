"""
Tests for schema version migration in history service (ISSUE-007).

Verifies on-the-fly migration of legacy messages with file metadata.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.services.history_service import HistoryService
from src.models.chat import FileMetadata


@pytest.fixture
def mock_legacy_message():
    """Create mock legacy message (schema_version < 2) with metadata.file_ids."""
    msg = MagicMock()
    msg.id = "msg_123"
    msg.chat_id = "chat_123"
    msg.role = "user"
    msg.content = "Test message"
    msg.status = "delivered"
    msg.created_at = datetime.utcnow()
    msg.updated_at = datetime.utcnow()
    msg.model = "SAPTIVA_TURBO"
    msg.tokens = None
    msg.latency_ms = None
    msg.task_id = None

    # Legacy: no explicit file_ids/files, but has metadata
    msg.file_ids = []
    msg.files = []
    msg.schema_version = 1

    # Legacy metadata with file info
    msg.metadata = {
        "file_ids": ["file_001", "file_002"],
        "files": [
            {
                "file_id": "file_001",
                "filename": "doc1.pdf",
                "bytes": 1024,
                "pages": 5,
                "mimetype": "application/pdf"
            },
            {
                "file_id": "file_002",
                "filename": "doc2.pdf",
                "bytes": 2048,
                "pages": 10,
                "mimetype": "application/pdf"
            }
        ]
    }

    return msg


@pytest.fixture
def mock_new_message():
    """Create mock new message (schema_version = 2) with explicit fields."""
    msg = MagicMock()
    msg.id = "msg_456"
    msg.chat_id = "chat_123"
    msg.role = "assistant"
    msg.content = "Response"
    msg.status = "delivered"
    msg.created_at = datetime.utcnow()
    msg.updated_at = datetime.utcnow()
    msg.model = "SAPTIVA_TURBO"
    msg.tokens = 100
    msg.latency_ms = 500
    msg.task_id = None

    # New schema: explicit typed fields
    msg.file_ids = ["file_003"]
    msg.files = [
        FileMetadata(
            file_id="file_003",
            filename="doc3.pdf",
            bytes=3072,
            pages=15,
            mimetype="application/pdf"
        )
    ]
    msg.schema_version = 2
    msg.metadata = {"source": "api"}

    return msg


@pytest.mark.asyncio
async def test_legacy_message_migration(mock_legacy_message):
    """
    Test that legacy messages (schema < 2) are migrated on-the-fly.

    Scenario: Message with schema_version=1 and metadata.file_ids.
    Expected: file_ids and files are extracted from metadata.
    """
    # Mock ChatMessageModel.find().find().sort().skip().limit().to_list()
    query_mock = MagicMock()
    query_mock.find.return_value = query_mock  # Support chaining .find().find()
    query_mock.sort.return_value = query_mock
    query_mock.skip.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.to_list = AsyncMock(return_value=[mock_legacy_message])
    query_mock.count = AsyncMock(return_value=1)

    with patch('src.models.chat.ChatMessage.find', return_value=query_mock):
        result = await HistoryService.get_chat_messages(
            chat_id="chat_123",
            limit=50,
            offset=0
        )

        messages = result["messages"]
        assert len(messages) == 1

        msg = messages[0]

        # Verify migration: file_ids extracted from metadata
        assert msg.file_ids == ["file_001", "file_002"]

        # Verify migration: files extracted and validated
        assert len(msg.files) == 2
        assert msg.files[0].file_id == "file_001"
        assert msg.files[0].filename == "doc1.pdf"
        assert msg.files[1].file_id == "file_002"


@pytest.mark.asyncio
async def test_new_message_no_migration(mock_new_message):
    """
    Test that new messages (schema = 2) are not migrated.

    Scenario: Message already has schema_version=2 with explicit fields.
    Expected: No migration, fields used as-is.
    """
    query_mock = MagicMock()
    query_mock.find.return_value = query_mock  # Support chaining .find().find()
    query_mock.sort.return_value = query_mock
    query_mock.skip.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.to_list = AsyncMock(return_value=[mock_new_message])
    query_mock.count = AsyncMock(return_value=1)

    with patch('src.models.chat.ChatMessage.find', return_value=query_mock):
        result = await HistoryService.get_chat_messages(
            chat_id="chat_123",
            limit=50,
            offset=0
        )

        messages = result["messages"]
        assert len(messages) == 1

        msg = messages[0]

        # No migration: fields used directly
        assert msg.file_ids == ["file_003"]
        assert len(msg.files) == 1
        assert msg.files[0].file_id == "file_003"
        assert msg.schema_version == 2


@pytest.mark.asyncio
async def test_migration_handles_invalid_file_metadata(mock_legacy_message):
    """
    Test that migration gracefully handles invalid file metadata.

    Scenario: Legacy metadata has malformed files data.
    Expected: Migration skips invalid files, logs warning.
    """
    # Corrupt file metadata
    mock_legacy_message.metadata["files"] = [
        {"file_id": "file_001"},  # Missing required fields
        "invalid_string"  # Not even a dict
    ]

    query_mock = MagicMock()
    query_mock.find.return_value = query_mock  # Support chaining .find().find()
    query_mock.sort.return_value = query_mock
    query_mock.skip.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.to_list = AsyncMock(return_value=[mock_legacy_message])
    query_mock.count = AsyncMock(return_value=1)

    with patch('src.models.chat.ChatMessage.find', return_value=query_mock):
        # Should not raise, but log warning
        result = await HistoryService.get_chat_messages(
            chat_id="chat_123",
            limit=50,
            offset=0
        )

        messages = result["messages"]
        assert len(messages) == 1

        # Migration failed gracefully, files should be empty
        msg = messages[0]
        assert msg.files == []


@pytest.mark.asyncio
async def test_mixed_schema_versions_in_history(mock_legacy_message, mock_new_message):
    """
    Test that history with mixed schema versions is handled correctly.

    Scenario: Chat has both legacy and new messages.
    Expected: Legacy messages migrated, new messages unchanged.
    """
    query_mock = MagicMock()
    query_mock.find.return_value = query_mock  # Support chaining .find().find()
    query_mock.sort.return_value = query_mock
    query_mock.skip.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.to_list = AsyncMock(return_value=[mock_legacy_message, mock_new_message])
    query_mock.count = AsyncMock(return_value=2)

    with patch('src.models.chat.ChatMessage.find', return_value=query_mock):
        result = await HistoryService.get_chat_messages(
            chat_id="chat_123",
            limit=50,
            offset=0
        )

        messages = result["messages"]
        assert len(messages) == 2

        # Messages are reversed in the response (chronological order for display)
        # First message: new (no migration)
        assert messages[0].file_ids == ["file_003"]
        assert len(messages[0].files) == 1

        # Second message: legacy (migrated)
        assert messages[1].file_ids == ["file_001", "file_002"]
        assert len(messages[1].files) == 2


@pytest.mark.asyncio
async def test_migration_only_when_needed():
    """
    Test that migration only runs when schema < 2 AND metadata has files.

    Scenario: Legacy message without file metadata.
    Expected: No migration attempted.
    """
    msg = MagicMock()
    msg.id = "msg_789"
    msg.chat_id = "chat_123"
    msg.role = "user"
    msg.content = "No files"
    msg.status = "delivered"
    msg.created_at = datetime.utcnow()
    msg.updated_at = datetime.utcnow()

    # Legacy schema but no file metadata
    msg.file_ids = []
    msg.files = []
    msg.schema_version = 1
    msg.metadata = {"source": "api"}  # No file_ids or files
    msg.model = None
    msg.tokens = None
    msg.latency_ms = None
    msg.task_id = None

    query_mock = MagicMock()
    query_mock.find.return_value = query_mock  # Support chaining .find().find()
    query_mock.sort.return_value = query_mock
    query_mock.skip.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.to_list = AsyncMock(return_value=[msg])
    query_mock.count = AsyncMock(return_value=1)

    with patch('src.models.chat.ChatMessage.find', return_value=query_mock):
        result = await HistoryService.get_chat_messages(
            chat_id="chat_123",
            limit=50,
            offset=0
        )

        messages = result["messages"]
        assert len(messages) == 1

        # No migration, fields remain empty
        assert messages[0].file_ids == []
        assert messages[0].files == []
