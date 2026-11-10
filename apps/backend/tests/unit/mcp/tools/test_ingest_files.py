"""
Unit tests for IngestFilesTool.

Tests cover:
- Input validation
- Document ingestion flow
- Error handling
- Idempotency
- Response message formatting
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.mcp_integration.tools.ingest_files import IngestFilesTool
from src.models.document_state import ProcessingStatus
from src.models.chat import ChatSession
from src.models.document import Document


class TestIngestFilesToolSpec:
    """Test tool specification."""

    def test_get_spec(self):
        """Should return valid ToolSpec."""
        tool = IngestFilesTool()
        spec = tool.get_spec()

        assert spec.name == "ingest_files"
        assert spec.version == "1.0.0"
        assert "async" in [c.value for c in spec.capabilities]
        assert "idempotent" in [c.value for c in spec.capabilities]
        assert "conversation_id" in spec.input_schema["required"]
        assert "file_refs" in spec.input_schema["required"]


class TestInputValidation:
    """Test input payload validation."""

    @pytest.mark.asyncio
    async def test_missing_conversation_id(self):
        """Should raise ValueError if conversation_id missing."""
        tool = IngestFilesTool()

        with pytest.raises(ValueError, match="Missing required field: conversation_id"):
            await tool.validate_input({"file_refs": ["doc-123"]})

    @pytest.mark.asyncio
    async def test_missing_file_refs(self):
        """Should raise ValueError if file_refs missing."""
        tool = IngestFilesTool()

        with pytest.raises(ValueError, match="Missing required field: file_refs"):
            await tool.validate_input({"conversation_id": "chat-123"})

    @pytest.mark.asyncio
    async def test_invalid_conversation_id_type(self):
        """Should raise ValueError if conversation_id not string."""
        tool = IngestFilesTool()

        with pytest.raises(ValueError, match="conversation_id must be a string"):
            await tool.validate_input({
                "conversation_id": 123,
                "file_refs": ["doc-123"]
            })

    @pytest.mark.asyncio
    async def test_invalid_file_refs_type(self):
        """Should raise ValueError if file_refs not list."""
        tool = IngestFilesTool()

        with pytest.raises(ValueError, match="file_refs must be a list"):
            await tool.validate_input({
                "conversation_id": "chat-123",
                "file_refs": "doc-123"
            })

    @pytest.mark.asyncio
    async def test_empty_file_refs(self):
        """Should raise ValueError if file_refs empty."""
        tool = IngestFilesTool()

        with pytest.raises(ValueError, match="file_refs cannot be empty"):
            await tool.validate_input({
                "conversation_id": "chat-123",
                "file_refs": []
            })

    @pytest.mark.asyncio
    async def test_valid_payload(self):
        """Should not raise error for valid payload."""
        tool = IngestFilesTool()

        # Should not raise
        await tool.validate_input({
            "conversation_id": "chat-123",
            "file_refs": ["doc-abc", "doc-def"]
        })


class TestDocumentIngestion:
    """Test document ingestion logic."""

    @pytest.mark.asyncio
    async def test_session_not_found(self):
        """Should return error if session doesn't exist."""
        tool = IngestFilesTool()

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=None):
            result = await tool.execute({
                "conversation_id": "nonexistent",
                "file_refs": ["doc-123"]
            })

            assert result["status"] == "error"
            assert "not found" in result["message"]
            assert result["ingested"] == 0
            assert result["failed_count"] == 1

    @pytest.mark.asyncio
    async def test_document_already_ingested(self):
        """Should skip document if already in session."""
        tool = IngestFilesTool()

        # Create mock existing document
        existing_doc = MagicMock()
        existing_doc.doc_id = "doc-123"
        existing_doc.name = "existing.pdf"
        existing_doc.status = ProcessingStatus.READY

        # Mock session with existing document
        mock_session = MagicMock()
        mock_session.id = "chat-123"
        mock_session.documents = [existing_doc]
        mock_session.attached_file_ids = ["doc-123"]
        mock_session.get_document = MagicMock(return_value=existing_doc)
        mock_session.save = AsyncMock()

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session):
            result = await tool.execute({
                "conversation_id": "chat-123",
                "file_refs": ["doc-123"]
            })

            assert result["status"] == "processing"
            assert result["ingested"] == 1
            # Should not call add_document for existing docs
            mock_session.add_document.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_ingestion(self):
        """Should create DocumentState for new documents."""
        tool = IngestFilesTool()

        # Mock document from storage
        mock_doc = MagicMock()
        mock_doc.filename = "test.pdf"
        mock_doc.size_bytes = 1024
        mock_doc.content_type = "application/pdf"
        mock_doc.metadata = {"pages": 5}
        mock_doc.created_at = datetime.utcnow()

        # Mock doc state returned by add_document
        mock_doc_state = MagicMock()
        mock_doc_state.doc_id = "doc-123"
        mock_doc_state.name = "test.pdf"
        mock_doc_state.status = ProcessingStatus.UPLOADING
        mock_doc_state.pages = 5

        # Mock session
        mock_session = MagicMock()
        mock_session.id = "chat-123"
        mock_session.documents = []
        mock_session.attached_file_ids = []
        mock_session.get_document = MagicMock(return_value=None)
        mock_session.add_document = MagicMock(return_value=mock_doc_state)
        mock_session.save = AsyncMock()

        # Mock processing service to avoid actual document processing
        mock_processing_service = MagicMock()
        mock_processing_service.process_document = AsyncMock()

        # Also return mock_session for verification read
        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session), \
             patch.object(Document, 'get', new_callable=AsyncMock, return_value=mock_doc), \
             patch('src.mcp_integration.tools.ingest_files.create_document_processing_service', return_value=mock_processing_service):

            result = await tool.execute({
                "conversation_id": "chat-123",
                "file_refs": ["doc-123"]
            })

            assert result["status"] == "processing"
            assert result["ingested"] == 1
            assert result["failed_count"] == 0
            assert len(result["documents"]) == 1
            assert result["documents"][0]["doc_id"] == "doc-123"

            # Verify session.save was called
            mock_session.save.assert_called()

    @pytest.mark.asyncio
    async def test_document_not_found_creates_minimal_state(self):
        """Should create minimal DocumentState if document not in storage."""
        tool = IngestFilesTool()

        # Mock doc state returned by add_document
        mock_doc_state = MagicMock()
        mock_doc_state.doc_id = "doc-missing"
        mock_doc_state.name = "document_doc-miss"
        mock_doc_state.status = ProcessingStatus.READY

        # Mock session
        mock_session = MagicMock()
        mock_session.id = "chat-123"
        mock_session.documents = []
        mock_session.attached_file_ids = []
        mock_session.get_document = MagicMock(return_value=None)
        mock_session.add_document = MagicMock(return_value=mock_doc_state)
        mock_session.save = AsyncMock()

        # Mock processing service to avoid actual document processing
        mock_processing_service = MagicMock()
        mock_processing_service.process_document = AsyncMock()

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session), \
             patch.object(Document, 'get', new_callable=AsyncMock, return_value=None), \
             patch('src.mcp_integration.tools.ingest_files.create_document_processing_service', return_value=mock_processing_service):

            result = await tool.execute({
                "conversation_id": "chat-123",
                "file_refs": ["doc-missing"]
            })

            assert result["status"] == "processing"
            assert result["ingested"] == 1
            # Should still succeed with minimal state
            assert result["failed_count"] == 0

    @pytest.mark.asyncio
    async def test_multiple_documents_mixed(self):
        """Should handle mix of existing and new documents."""
        tool = IngestFilesTool()

        # Mock existing document
        existing_doc = MagicMock()
        existing_doc.doc_id = "doc-existing"
        existing_doc.name = "existing.pdf"
        existing_doc.status = ProcessingStatus.READY

        # Mock new doc state
        new_doc_state = MagicMock()
        new_doc_state.doc_id = "doc-new"
        new_doc_state.name = "new.pdf"
        new_doc_state.status = ProcessingStatus.UPLOADING

        # Mock document from storage
        mock_doc1 = MagicMock()
        mock_doc1.filename = "new.pdf"
        mock_doc1.metadata = {"pages": 3}

        # Mock session
        mock_session = MagicMock()
        mock_session.id = "chat-123"
        mock_session.documents = []
        mock_session.attached_file_ids = []

        # First call returns existing, second returns None
        mock_session.get_document = MagicMock(side_effect=[
            existing_doc,
            None
        ])
        mock_session.add_document = MagicMock(return_value=new_doc_state)
        mock_session.save = AsyncMock()

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session), \
             patch.object(Document, 'get', new_callable=AsyncMock, return_value=mock_doc1):

            result = await tool.execute({
                "conversation_id": "chat-123",
                "file_refs": ["doc-existing", "doc-new"]
            })

            assert result["status"] == "processing"
            assert result["ingested"] == 2
            assert result["total"] == 2


class TestErrorHandling:
    """Test error scenarios."""

    @pytest.mark.asyncio
    async def test_session_get_exception(self):
        """Should handle session retrieval exceptions."""
        tool = IngestFilesTool()

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, side_effect=Exception("DB error")):
            result = await tool.execute({
                "conversation_id": "chat-123",
                "file_refs": ["doc-123"]
            })

            assert result["status"] == "error"
            assert "Failed to ingest files" in result["message"]
            assert result["ingested"] == 0

    @pytest.mark.asyncio
    async def test_document_processing_exception(self):
        """Should handle individual document processing errors gracefully."""
        tool = IngestFilesTool()

        # Mock session
        mock_session = MagicMock()
        mock_session.id = "chat-123"
        mock_session.documents = []
        mock_session.attached_file_ids = []
        mock_session.get_document = MagicMock(side_effect=Exception("Processing error"))
        mock_session.save = AsyncMock()

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session):
            result = await tool.execute({
                "conversation_id": "chat-123",
                "file_refs": ["doc-bad"]
            })

            # Should continue despite error
            assert result["status"] == "processing"
            assert result["failed_count"] == 1
            assert len(result["failed"]) == 1
            assert result["failed"][0]["doc_id"] == "doc-bad"


class TestResponseFormatting:
    """Test response message formatting."""

    def test_build_response_empty(self):
        """Should return empty message for no documents."""
        tool = IngestFilesTool()
        message = tool._build_response_message([], [])

        assert "No se recibieron documentos" in message

    def test_build_response_ingested_only(self):
        """Should format message for successfully ingested docs."""
        tool = IngestFilesTool()

        # Create mocks with explicit .name attribute
        doc1 = MagicMock()
        doc1.name = "file1.pdf"
        doc1.pages = 5

        doc2 = MagicMock()
        doc2.name = "file2.pdf"
        doc2.pages = None

        docs = [doc1, doc2]

        message = tool._build_response_message(docs, [])

        assert "**file1.pdf**" in message
        assert "5 págs" in message
        assert "**file2.pdf**" in message
        assert "procesando" in message

    def test_build_response_with_failures(self):
        """Should include failure details in message."""
        tool = IngestFilesTool()

        doc1 = MagicMock()
        doc1.name = "success.pdf"
        doc1.pages = 3

        docs = [doc1]
        failed = [
            {"doc_id": "doc-fail-1", "error": "Not found"},
            {"doc_id": "doc-fail-2", "error": "Permission denied"}
        ]

        message = tool._build_response_message(docs, failed)

        assert "success.pdf" in message
        assert "No pude procesar 2 documento(s)" in message
        assert "doc-fail-1" in message
