"""
Integration tests for document workflow (ingestion → processing → retrieval).

Tests the complete RAG pipeline:
1. IngestFilesTool creates DocumentState
2. BackgroundTask processes document (extract + segment + cache)
3. GetRelevantSegmentsTool retrieves segments
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import os

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_DOCUMENT_WORKFLOW", "false").lower() != "true",
    reason="Integration document workflow deshabilitado por defecto (requires full stack)",
)

from src.models.chat import ChatSession
from src.models.document import Document
from src.models.document_state import ProcessingStatus
from src.models.document import PageContent
from src.services.document_processing_service import (
    DocumentProcessingService,
    WordBasedSegmenter,
    create_document_processing_service
)
from src.mcp_integration.tools.ingest_files import IngestFilesTool
from src.mcp_integration.tools.get_segments import GetRelevantSegmentsTool


class TestDocumentProcessor:
    """Test document_processor service."""

    def test_segment_text_basic(self):
        """Should segment text into chunks."""
        segmenter = WordBasedSegmenter(chunk_size=20)
        text = " ".join([f"word{i}" for i in range(100)])
        segments = segmenter.segment(text)

        assert len(segments) > 0
        assert all("text" in seg for seg in segments)
        assert all("index" in seg for seg in segments)
        assert segments[0]["index"] == 0

    def test_segment_text_with_overlap(self):
        """Should create overlapping segments."""
        segmenter = WordBasedSegmenter(chunk_size=20, overlap_ratio=0.25)
        text = " ".join([f"word{i}" for i in range(100)])
        segments = segmenter.segment(text)

        # With 25% overlap, should have more segments than (100 / 20)
        assert len(segments) > 5

    def test_segment_text_empty(self):
        """Should handle empty text."""
        segmenter = WordBasedSegmenter(chunk_size=20)
        segments = segmenter.segment("")
        assert segments == []

    def test_segment_text_metadata(self):
        """Should include metadata in segments."""
        segmenter = WordBasedSegmenter(chunk_size=2)
        text = "one two three four five"
        segments = segmenter.segment(text)

        assert all("word_count" in seg for seg in segments)
        assert all("start_word" in seg for seg in segments)
        assert all("end_word" in seg for seg in segments)

    @pytest.mark.asyncio
    async def test_process_document_session_not_found(self):
        """Should raise error if session not found."""
        service = create_document_processing_service("word_based")

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match="Session .* not found"):
                await service.process_document("nonexistent", "doc-123")

    @pytest.mark.asyncio
    async def test_process_document_doc_not_in_session(self):
        """Should raise error if document not in session."""
        service = create_document_processing_service("word_based")

        mock_session = MagicMock(spec=ChatSession)
        mock_session.id = "chat-123"
        mock_session.get_document = MagicMock(return_value=None)

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session):
            with pytest.raises(ValueError, match="Document .* not in session"):
                await service.process_document("chat-123", "doc-missing")

    @pytest.mark.asyncio
    async def test_process_document_success(self):
        """Should process document successfully."""
        service = create_document_processing_service("word_based")

        # Mock DocumentState
        mock_doc_state = MagicMock()
        mock_doc_state.doc_id = "doc-123"
        mock_doc_state.name = "test.pdf"
        mock_doc_state.mark_processing = MagicMock()
        mock_doc_state.mark_ready = MagicMock()

        # Mock ChatSession
        mock_session = MagicMock(spec=ChatSession)
        mock_session.id = "chat-123"
        mock_session.get_document = MagicMock(return_value=mock_doc_state)
        mock_session.save = AsyncMock()

        # Mock Document
        mock_document = MagicMock(spec=Document)
        mock_document.file_path = "/tmp/test.pdf"
        mock_document.content_type = "application/pdf"
        mock_document.filename = "test.pdf"

        # Mock extraction
        mock_pages = [
            PageContent(page=1, text_md="This is page one content."),
            PageContent(page=2, text_md="This is page two content.")
        ]

        # Mock cache
        mock_cache = AsyncMock()
        mock_cache.set = AsyncMock()

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session), \
             patch.object(Document, 'get', new_callable=AsyncMock, return_value=mock_document), \
             patch('src.services.document_processing_service.extract_text_from_file', new_callable=AsyncMock, return_value=mock_pages), \
             patch('src.services.document_processing_service.get_redis_cache', new_callable=AsyncMock, return_value=mock_cache):

            await service.process_document("chat-123", "doc-123")

            # Verify processing flow
            mock_doc_state.mark_processing.assert_called_once()
            mock_doc_state.mark_ready.assert_called_once()
            assert mock_session.save.call_count == 2  # Once for PROCESSING, once for READY
            mock_cache.set.assert_called_once()

            # Verify cache key
            call_args = mock_cache.set.call_args
            assert call_args[0][0] == "doc_segments:doc-123"
            segments = call_args[0][1]
            assert len(segments) > 0

    @pytest.mark.asyncio
    async def test_process_document_extraction_failure(self):
        """Should mark document as FAILED on extraction error."""
        service = create_document_processing_service("word_based")

        # Mock DocumentState
        mock_doc_state = MagicMock()
        mock_doc_state.doc_id = "doc-123"
        mock_doc_state.mark_processing = MagicMock()
        mock_doc_state.mark_failed = MagicMock()

        # Mock ChatSession
        mock_session = MagicMock(spec=ChatSession)
        mock_session.id = "chat-123"
        mock_session.get_document = MagicMock(return_value=mock_doc_state)
        mock_session.save = AsyncMock()

        # Mock Document
        mock_document = MagicMock(spec=Document)
        mock_document.file_path = "/tmp/test.pdf"
        mock_document.content_type = "application/pdf"

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session), \
             patch.object(Document, 'get', new_callable=AsyncMock, return_value=mock_document), \
             patch('src.services.document_processing_service.extract_text_from_file', new_callable=AsyncMock, side_effect=Exception("Extraction failed")):

            with pytest.raises(Exception, match="Extraction failed"):
                await service.process_document("chat-123", "doc-123")

            # Verify document marked as failed
            mock_doc_state.mark_failed.assert_called_once()
            assert "Extraction failed" in str(mock_doc_state.mark_failed.call_args)


class TestEndToEndWorkflow:
    """Test complete ingestion → processing → retrieval workflow."""

    @pytest.mark.asyncio
    async def test_complete_workflow_simulation(self):
        """Simulate complete document workflow."""

        # 1. Setup: Create mock session with document
        mock_doc = MagicMock(spec=Document)
        mock_doc.id = "doc-abc"
        mock_doc.filename = "test.pdf"
        mock_doc.content_type = "application/pdf"
        mock_doc.file_path = "/tmp/test.pdf"

        mock_session = MagicMock(spec=ChatSession)
        mock_session.id = "chat-123"
        mock_session.documents = []
        mock_session.get_document = MagicMock(return_value=None)
        mock_session.add_document = MagicMock(return_value=MagicMock(
            doc_id="doc-abc",
            name="test.pdf",
            status=ProcessingStatus.UPLOADING
        ))
        mock_session.save = AsyncMock()
        mock_session.get_ready_documents = MagicMock(return_value=[])

        # 2. Ingest document (no BackgroundTasks in test)
        ingest_tool = IngestFilesTool()

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session), \
             patch.object(Document, 'get', new_callable=AsyncMock, return_value=mock_doc):

            result = await ingest_tool.execute({
                "conversation_id": "chat-123",
                "file_refs": ["doc-abc"]
            }, context={})  # No background_tasks

            assert result["status"] == "processing"
            assert result["ingested"] == 1
            mock_session.save.assert_called_once()

        # 3. Simulate processing (would happen in background)
        # (Tested separately in TestDocumentProcessor)

        # 4. Try to retrieve segments (should fail - no ready docs)
        get_segments_tool = GetRelevantSegmentsTool()

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session):
            result = await get_segments_tool.execute({
                "conversation_id": "chat-123",
                "question": "test question"
            })

            assert result["segments"] == []
            assert result["ready_docs"] == 0
            assert "no hay documentos procesados" in result["message"].lower()


class TestSegmentRetrieval:
    """Test segment retrieval after processing."""

    @pytest.mark.asyncio
    async def test_retrieve_segments_after_cache(self):
        """Should retrieve segments from cache."""

        # Mock ready document
        mock_doc_state = MagicMock()
        mock_doc_state.doc_id = "doc-123"
        mock_doc_state.name = "pricing.pdf"
        mock_doc_state.is_ready = MagicMock(return_value=True)

        mock_session = MagicMock(spec=ChatSession)
        mock_session.documents = [mock_doc_state]
        mock_session.get_ready_documents = MagicMock(return_value=[mock_doc_state])

        # Mock cached segments
        cached_segments = [
            {"index": 0, "text": "Our pricing model is subscription-based."},
            {"index": 1, "text": "The basic plan costs $99 per month."},
            {"index": 2, "text": "Enterprise plans start at $999 per month."}
        ]

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=cached_segments)

        tool = GetRelevantSegmentsTool()

        with patch.object(ChatSession, 'get', new_callable=AsyncMock, return_value=mock_session), \
             patch('src.mcp_integration.tools.get_segments.get_redis_cache', new_callable=AsyncMock, return_value=mock_cache):

            result = await tool.execute({
                "conversation_id": "chat-123",
                "question": "What is the pricing model?",
                "max_segments": 2
            })

            assert len(result["segments"]) == 2  # Respects max_segments
            assert result["ready_docs"] == 1
            assert result["total_segments"] == 3

            # Verify segments are scored and ranked
            assert all("score" in seg for seg in result["segments"])
            assert result["segments"][0]["score"] >= result["segments"][1]["score"]
