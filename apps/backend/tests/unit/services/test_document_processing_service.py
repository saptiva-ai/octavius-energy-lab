"""
Unit tests for DocumentProcessingService.

Tests:
- WordBasedSegmenter chunking logic
- SentenceBasedSegmenter (fallback behavior)
- DocumentProcessingService initialization
- Validation and error handling
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

from src.services.document_processing_service import (
    WordBasedSegmenter,
    SentenceBasedSegmenter,
    DocumentProcessingService,
    ITextSegmenter,
)


# ============================================================================
# WORD-BASED SEGMENTER TESTS
# ============================================================================

class TestWordBasedSegmenter:
    """Tests for WordBasedSegmenter class."""

    def test_init_default_values(self):
        """Should initialize with default chunk size and overlap."""
        segmenter = WordBasedSegmenter()

        assert segmenter.chunk_size == 1000
        assert segmenter.overlap_ratio == 0.25
        assert segmenter.overlap_words == 250

    def test_init_custom_values(self):
        """Should accept custom chunk size and overlap."""
        segmenter = WordBasedSegmenter(chunk_size=500, overlap_ratio=0.1)

        assert segmenter.chunk_size == 500
        assert segmenter.overlap_ratio == 0.1
        assert segmenter.overlap_words == 50

    def test_init_invalid_chunk_size(self):
        """Should raise error for invalid chunk size."""
        with pytest.raises(ValueError, match="chunk_size must be >= 1"):
            WordBasedSegmenter(chunk_size=0)

        with pytest.raises(ValueError, match="chunk_size must be >= 1"):
            WordBasedSegmenter(chunk_size=-10)

    def test_init_invalid_overlap_ratio(self):
        """Should raise error for invalid overlap ratio."""
        with pytest.raises(ValueError, match="overlap_ratio must be between"):
            WordBasedSegmenter(overlap_ratio=-0.1)

        with pytest.raises(ValueError, match="overlap_ratio must be between"):
            WordBasedSegmenter(overlap_ratio=0.6)

    def test_segment_empty_text(self):
        """Should return empty list for empty text."""
        segmenter = WordBasedSegmenter(chunk_size=100)
        result = segmenter.segment("")

        assert result == []

    def test_segment_whitespace_only(self):
        """Should return empty list for whitespace-only text."""
        segmenter = WordBasedSegmenter(chunk_size=100)
        result = segmenter.segment("   \n\t  ")

        assert result == []

    def test_segment_short_text(self):
        """Should return single segment for short text."""
        segmenter = WordBasedSegmenter(chunk_size=100, overlap_ratio=0.25)
        text = "This is a short text with only ten words here."

        result = segmenter.segment(text)

        assert len(result) == 1
        assert result[0]["index"] == 0
        assert result[0]["word_count"] == 10

    def test_segment_creates_overlapping_chunks(self):
        """Should create overlapping segments for longer text."""
        # Create text with exactly 30 words
        words = [f"word{i}" for i in range(30)]
        text = " ".join(words)

        segmenter = WordBasedSegmenter(chunk_size=10, overlap_ratio=0.2)
        # overlap_words = 2

        result = segmenter.segment(text)

        # With 30 words, chunk_size=10, overlap=2:
        # Chunk 0: words 0-9 (10 words)
        # Chunk 1: words 8-17 (10 words, starts at 10-2=8)
        # Chunk 2: words 16-25 (10 words)
        # Chunk 3: words 24-29 (6 words)
        assert len(result) >= 3

        # Verify overlap exists
        if len(result) >= 2:
            # Second chunk should start before first chunk ends
            assert result[1]["start_word"] < result[0]["end_word"]

    def test_segment_metadata_structure(self):
        """Should include correct metadata in each segment."""
        segmenter = WordBasedSegmenter(chunk_size=5, overlap_ratio=0.0)
        text = "one two three four five six seven eight"

        result = segmenter.segment(text)

        # Check first segment structure
        assert "index" in result[0]
        assert "text" in result[0]
        assert "word_count" in result[0]
        assert "start_word" in result[0]
        assert "end_word" in result[0]

        assert result[0]["index"] == 0
        assert result[0]["start_word"] == 0

    def test_segment_preserves_text_content(self):
        """Should preserve text content in segments."""
        segmenter = WordBasedSegmenter(chunk_size=3, overlap_ratio=0.0)
        text = "apple banana cherry date elderberry fig"

        result = segmenter.segment(text)

        assert result[0]["text"] == "apple banana cherry"
        assert result[1]["text"] == "date elderberry fig"

    def test_segment_zero_overlap(self):
        """Should work correctly with zero overlap."""
        segmenter = WordBasedSegmenter(chunk_size=5, overlap_ratio=0.0)
        text = " ".join([f"w{i}" for i in range(15)])

        result = segmenter.segment(text)

        # Should have 3 segments with no overlap
        assert len(result) == 3
        assert result[0]["start_word"] == 0
        assert result[1]["start_word"] == 5
        assert result[2]["start_word"] == 10


# ============================================================================
# SENTENCE-BASED SEGMENTER TESTS
# ============================================================================

class TestSentenceBasedSegmenter:
    """Tests for SentenceBasedSegmenter class."""

    def test_init_default_values(self):
        """Should initialize with default sentences per chunk."""
        segmenter = SentenceBasedSegmenter()
        assert segmenter.sentences_per_chunk == 10

    def test_init_custom_values(self):
        """Should accept custom sentences per chunk."""
        segmenter = SentenceBasedSegmenter(sentences_per_chunk=5)
        assert segmenter.sentences_per_chunk == 5

    def test_segment_falls_back_to_word_based(self):
        """Should fallback to word-based segmentation (current impl)."""
        segmenter = SentenceBasedSegmenter()
        text = "This is sentence one. This is sentence two. This is sentence three."

        result = segmenter.segment(text)

        # Should return segments (using fallback)
        assert isinstance(result, list)
        # Current implementation uses WordBasedSegmenter fallback


# ============================================================================
# DOCUMENT PROCESSING SERVICE TESTS
# ============================================================================

class TestDocumentProcessingServiceInit:
    """Tests for DocumentProcessingService initialization."""

    def test_init_with_default_segmenter(self):
        """Should use WordBasedSegmenter by default."""
        service = DocumentProcessingService()

        assert service.segmenter is not None
        assert isinstance(service.segmenter, WordBasedSegmenter)
        assert service.segmenter.chunk_size == 400
        assert service.segmenter.overlap_ratio == 0.25

    def test_init_with_custom_segmenter(self):
        """Should accept custom segmenter."""
        custom_segmenter = WordBasedSegmenter(chunk_size=200, overlap_ratio=0.1)
        service = DocumentProcessingService(segmenter=custom_segmenter)

        assert service.segmenter is custom_segmenter
        assert service.segmenter.chunk_size == 200

    def test_init_with_sentence_segmenter(self):
        """Should accept SentenceBasedSegmenter."""
        sentence_segmenter = SentenceBasedSegmenter(sentences_per_chunk=15)
        service = DocumentProcessingService(segmenter=sentence_segmenter)

        assert isinstance(service.segmenter, SentenceBasedSegmenter)


# ============================================================================
# INTEGRATION-LIKE TESTS (with mocks)
# ============================================================================

class TestDocumentProcessingServiceProcessing:
    """Tests for document processing operations."""

    @pytest.mark.asyncio
    async def test_process_document_not_found(self):
        """Should raise error when session not found."""
        service = DocumentProcessingService()

        with patch.object(service, '_get_session', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = ValueError("Session not found")

            with pytest.raises(ValueError, match="Session not found"):
                await service.process_document("invalid-session", "doc-123")

    @pytest.mark.asyncio
    async def test_process_document_invalid_doc(self):
        """Should raise error when document not in session."""
        service = DocumentProcessingService()

        mock_session = Mock()

        with patch.object(service, '_get_session', new_callable=AsyncMock, return_value=mock_session):
            with patch.object(service, '_validate_document_in_session', new_callable=AsyncMock) as mock_validate:
                mock_validate.side_effect = ValueError("Document not found")

                with pytest.raises(ValueError, match="Document not found"):
                    await service.process_document("session-123", "invalid-doc")


# ============================================================================
# SEGMENTATION STRATEGY PATTERN TESTS
# ============================================================================

class TestSegmentationStrategy:
    """Tests for strategy pattern compliance."""

    def test_word_segmenter_implements_interface(self):
        """WordBasedSegmenter should implement ITextSegmenter."""
        segmenter = WordBasedSegmenter()
        assert isinstance(segmenter, ITextSegmenter)
        assert hasattr(segmenter, 'segment')
        assert callable(segmenter.segment)

    def test_sentence_segmenter_implements_interface(self):
        """SentenceBasedSegmenter should implement ITextSegmenter."""
        segmenter = SentenceBasedSegmenter()
        assert isinstance(segmenter, ITextSegmenter)
        assert hasattr(segmenter, 'segment')
        assert callable(segmenter.segment)

    def test_custom_segmenter_can_be_used(self):
        """Should allow custom ITextSegmenter implementations."""
        class CustomSegmenter(ITextSegmenter):
            def segment(self, text):
                return [{"text": text, "index": 0}]

        custom = CustomSegmenter()
        service = DocumentProcessingService(segmenter=custom)

        # Should work with custom segmenter
        result = service.segmenter.segment("test text")
        assert len(result) == 1


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_segment_single_word(self):
        """Should handle single word text."""
        segmenter = WordBasedSegmenter(chunk_size=10)
        result = segmenter.segment("hello")

        assert len(result) == 1
        assert result[0]["text"] == "hello"
        assert result[0]["word_count"] == 1

    def test_segment_unicode_text(self):
        """Should handle unicode characters."""
        segmenter = WordBasedSegmenter(chunk_size=5, overlap_ratio=0.0)
        text = "hola mundo café naïve résumé"

        result = segmenter.segment(text)

        assert len(result) == 1
        assert "café" in result[0]["text"]
        assert "naïve" in result[0]["text"]

    def test_segment_special_characters(self):
        """Should handle text with special characters."""
        segmenter = WordBasedSegmenter(chunk_size=10)
        text = "Hello, world! How are you? I'm fine. Thanks..."

        result = segmenter.segment(text)

        assert len(result) >= 1
        # Should include punctuation attached to words

    def test_large_text_performance(self):
        """Should handle large texts efficiently."""
        segmenter = WordBasedSegmenter(chunk_size=500, overlap_ratio=0.1)
        # Generate large text (10000 words)
        text = " ".join([f"word{i}" for i in range(10000)])

        result = segmenter.segment(text)

        # Should create reasonable number of segments
        # With 10000 words, chunk_size=500, overlap=50: ~22 segments
        assert len(result) > 15
        assert len(result) < 30


# ============================================================================
# FACTORY FUNCTION TESTS
# ============================================================================

class TestCreateDocumentProcessingService:
    """Tests for create_document_processing_service factory."""

    def test_word_based_strategy(self):
        """Should create service with word-based segmenter."""
        from src.services.document_processing_service import create_document_processing_service

        service = create_document_processing_service("word_based")

        assert isinstance(service.segmenter, WordBasedSegmenter)
        assert service.segmenter.chunk_size == 400

    def test_sentence_based_strategy(self):
        """Should create service with sentence-based segmenter."""
        from src.services.document_processing_service import create_document_processing_service

        service = create_document_processing_service("sentence_based")

        assert isinstance(service.segmenter, SentenceBasedSegmenter)
        assert service.segmenter.sentences_per_chunk == 10

    def test_unknown_strategy_raises_error(self):
        """Should raise error for unknown strategy."""
        from src.services.document_processing_service import create_document_processing_service

        with pytest.raises(ValueError, match="Unknown segmentation strategy"):
            create_document_processing_service("invalid_strategy")


# ============================================================================
# PROCESSING METHOD TESTS
# ============================================================================

class TestDocumentProcessingMethods:
    """Tests for document processing methods."""

    @pytest.mark.asyncio
    async def test_get_session_not_found(self):
        """Should raise error when session not found."""
        service = DocumentProcessingService()

        with patch("src.services.document_processing_service.ChatSession") as mock_cls:
            mock_cls.get = AsyncMock(return_value=None)

            with pytest.raises(ValueError, match="not found"):
                await service._get_session("nonexistent-session")

    @pytest.mark.asyncio
    async def test_get_session_found(self):
        """Should return session when found."""
        service = DocumentProcessingService()
        mock_session = Mock()

        with patch("src.services.document_processing_service.ChatSession") as mock_cls:
            mock_cls.get = AsyncMock(return_value=mock_session)

            result = await service._get_session("session-123")

            assert result is mock_session

    @pytest.mark.asyncio
    async def test_validate_document_not_in_session(self):
        """Should raise error when document not in session."""
        service = DocumentProcessingService()
        mock_session = Mock()
        mock_session.attached_file_ids = ["other-doc"]

        with pytest.raises(ValueError, match="not in session"):
            await service._validate_document_in_session(mock_session, "doc-123")

    @pytest.mark.asyncio
    async def test_validate_document_not_in_db(self):
        """Should raise error when document not in database."""
        service = DocumentProcessingService()
        mock_session = Mock()
        mock_session.id = "session-123"
        mock_session.attached_file_ids = ["doc-123"]

        with patch("src.models.document.Document.get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match="not found in database"):
                await service._validate_document_in_session(mock_session, "doc-123")

    @pytest.mark.asyncio
    async def test_validate_document_success(self):
        """Should return document when valid."""
        service = DocumentProcessingService()
        mock_session = Mock()
        mock_session.id = "session-123"
        mock_session.attached_file_ids = ["doc-123"]
        mock_document = Mock()

        with patch("src.models.document.Document.get", new_callable=AsyncMock, return_value=mock_document):
            result = await service._validate_document_in_session(mock_session, "doc-123")

            assert result is mock_document

    @pytest.mark.asyncio
    async def test_get_document_from_storage_not_found(self):
        """Should raise error when document not in storage."""
        service = DocumentProcessingService()

        with patch("src.services.document_processing_service.Document") as mock_cls:
            mock_cls.get = AsyncMock(return_value=None)

            with pytest.raises(ValueError, match="not found in storage"):
                await service._get_document_from_storage("nonexistent-doc")

    @pytest.mark.asyncio
    async def test_get_document_from_storage_found(self):
        """Should return document when found."""
        service = DocumentProcessingService()
        mock_document = Mock()

        with patch("src.services.document_processing_service.Document") as mock_cls:
            mock_cls.get = AsyncMock(return_value=mock_document)

            result = await service._get_document_from_storage("doc-123")

            assert result is mock_document

    @pytest.mark.asyncio
    async def test_mark_failed_success(self):
        """Should mark document as failed."""
        service = DocumentProcessingService()
        mock_document = Mock()
        mock_document.save = AsyncMock()

        with patch("src.models.document.Document.get", new_callable=AsyncMock, return_value=mock_document):
            await service._mark_failed("session-123", "doc-123", "Test error")

            assert mock_document.status == "failed"
            assert "Test error" in mock_document.error_message
            mock_document.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_failed_document_not_found(self):
        """Should handle document not found gracefully."""
        service = DocumentProcessingService()

        with patch("src.models.document.Document.get", new_callable=AsyncMock, return_value=None):
            # Should not raise
            await service._mark_failed("session-123", "nonexistent", "Error")

    @pytest.mark.asyncio
    async def test_mark_failed_save_error(self):
        """Should handle save error gracefully."""
        service = DocumentProcessingService()
        mock_document = Mock()
        mock_document.save = AsyncMock(side_effect=Exception("DB error"))

        with patch("src.models.document.Document.get", new_callable=AsyncMock, return_value=mock_document):
            # Should not raise
            await service._mark_failed("session-123", "doc-123", "Test error")


class TestChunkAndEmbed:
    """Tests for _chunk_and_embed method."""

    @pytest.mark.asyncio
    async def test_chunk_and_embed_returns_chunks(self):
        """Should return chunks with embeddings."""
        service = DocumentProcessingService()
        mock_embedding_service = Mock()
        mock_embedding_service.chunk_and_embed.return_value = [
            {"text": "chunk1", "embedding": [0.1, 0.2]},
            {"text": "chunk2", "embedding": [0.3, 0.4]},
        ]

        with patch(
            "src.services.document_processing_service.get_embedding_service",
            return_value=mock_embedding_service,
        ):
            result = await service._chunk_and_embed(
                "Test text for chunking", "test.pdf"
            )

            assert len(result) == 2
            mock_embedding_service.chunk_and_embed.assert_called_once()


class TestStoreInWeaviate:
    """Tests for _store_in_weaviate method."""

    @pytest.mark.asyncio
    async def test_store_in_weaviate_success(self):
        """Should store chunks in Weaviate."""
        service = DocumentProcessingService()
        mock_weaviate = Mock()
        mock_weaviate.upsert_chunks.return_value = 5

        chunks = [{"text": "chunk", "embedding": [0.1]}]

        with patch(
            "src.services.document_processing_service.get_weaviate_service",
            return_value=mock_weaviate,
        ):
            await service._store_in_weaviate("session-123", "doc-456", chunks)

            mock_weaviate.upsert_chunks.assert_called_once_with(
                session_id="session-123",
                document_id="doc-456",
                chunks=chunks,
            )


class TestProcessDocumentStandalone:
    """Tests for process_document_standalone method."""

    @pytest.mark.asyncio
    async def test_standalone_document_not_found(self):
        """Should raise error when document not found."""
        service = DocumentProcessingService()

        with patch("src.models.document.Document.get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match="not found"):
                await service.process_document_standalone("nonexistent-doc")

    @pytest.mark.asyncio
    async def test_standalone_uses_existing_pages(self):
        """Should use existing pages if available."""
        service = DocumentProcessingService()

        mock_page = Mock()
        mock_page.text_md = "Page content here"

        mock_document = Mock()
        mock_document.id = "doc-123"
        mock_document.filename = "test.pdf"
        mock_document.pages = [mock_page]

        mock_embedding_service = Mock()
        mock_embedding_service.chunk_and_embed.return_value = [
            {"text": "chunk", "embedding": [0.1]}
        ]

        mock_weaviate = Mock()
        mock_weaviate.upsert_chunks.return_value = 1

        mock_embedding_service.chunk_pages_and_embed = Mock(return_value=[
            {"text": "chunk", "embedding": [0.1], "page": 1}
        ])

        with patch("src.models.document.Document.get", new_callable=AsyncMock, return_value=mock_document), \
             patch("src.services.document_processing_service.get_embedding_service", return_value=mock_embedding_service), \
             patch("src.services.document_processing_service.get_weaviate_service", return_value=mock_weaviate):

            await service.process_document_standalone("doc-123")

            # Should use pages with page-aware chunking
            mock_embedding_service.chunk_pages_and_embed.assert_called_once()

    @pytest.mark.asyncio
    async def test_standalone_extracts_when_no_pages(self):
        """Should extract text when no pages available."""
        service = DocumentProcessingService()

        mock_document = Mock()
        mock_document.id = "doc-123"
        mock_document.filename = "test.pdf"
        mock_document.pages = []

        mock_page = Mock()
        mock_page.text_md = "Extracted text"
        mock_page.page = 1

        with patch("src.models.document.Document.get", new_callable=AsyncMock, return_value=mock_document), \
             patch.object(service, "_extract_pages", new_callable=AsyncMock, return_value=[mock_page]), \
             patch.object(service, "_chunk_and_embed", new_callable=AsyncMock, return_value=[{"text": "chunk"}]), \
             patch.object(service, "_store_in_weaviate", new_callable=AsyncMock):

            await service.process_document_standalone("doc-123")

            service._extract_pages.assert_called_once()


class TestProcessDocument:
    """Tests for process_document method."""

    @pytest.mark.asyncio
    async def test_process_document_full_flow(self):
        """Should execute full processing flow."""
        service = DocumentProcessingService()

        mock_session = Mock()
        mock_session.attached_file_ids = ["doc-123"]

        mock_document = Mock()
        mock_document.id = "doc-123"
        mock_document.filename = "test.pdf"
        mock_document.save = AsyncMock()

        mock_page = Mock()
        mock_page.text_md = "Extracted"
        mock_page.page = 1

        with patch.object(service, "_get_session", new_callable=AsyncMock, return_value=mock_session), \
             patch.object(service, "_validate_document_in_session", new_callable=AsyncMock, return_value=mock_document), \
             patch.object(service, "_extract_pages", new_callable=AsyncMock, return_value=[mock_page]), \
             patch.object(service, "_chunk_and_embed", new_callable=AsyncMock, return_value=[{"text": "c"}]), \
             patch.object(service, "_store_in_weaviate", new_callable=AsyncMock):

            await service.process_document("session-123", "doc-123")

            # Should mark as ready at the end
            assert mock_document.status == "ready"
            mock_document.save.assert_called()

    @pytest.mark.asyncio
    async def test_process_document_marks_failed_on_error(self):
        """Should mark document as failed on error."""
        service = DocumentProcessingService()

        mock_session = Mock()
        mock_session.attached_file_ids = ["doc-123"]

        mock_document = Mock()
        mock_document.id = "doc-123"
        mock_document.save = AsyncMock()

        with patch.object(service, "_get_session", new_callable=AsyncMock, return_value=mock_session), \
             patch.object(service, "_validate_document_in_session", new_callable=AsyncMock, return_value=mock_document), \
             patch.object(service, "_extract_pages", new_callable=AsyncMock, side_effect=Exception("Extraction failed")), \
             patch.object(service, "_mark_failed", new_callable=AsyncMock) as mock_mark_failed:

            with pytest.raises(Exception, match="Extraction failed"):
                await service.process_document("session-123", "doc-123")

            mock_mark_failed.assert_called_once()


class TestReprocessDocument:
    """Tests for reprocess_document method."""

    @pytest.mark.asyncio
    async def test_reprocess_resets_and_processes(self):
        """Should reset status and reprocess."""
        from src.services.document_processing_service import DocumentProcessingService
        from src.models.document_state import ProcessingStatus

        service = DocumentProcessingService()

        mock_session = Mock()
        mock_session.save = AsyncMock()

        mock_doc_state = Mock()
        mock_doc_state.status = ProcessingStatus.FAILED
        mock_doc_state.error = "Previous error"

        with patch.object(service, "_get_session", new_callable=AsyncMock, return_value=mock_session), \
             patch.object(service, "_validate_document_in_session", new_callable=AsyncMock, return_value=mock_doc_state), \
             patch.object(service, "process_document", new_callable=AsyncMock) as mock_process:

            await service.reprocess_document("session-123", "doc-123")

            # Should reset status
            assert mock_doc_state.status == ProcessingStatus.UPLOADING
            assert mock_doc_state.error is None

            # Should call process_document
            mock_process.assert_called_once_with("session-123", "doc-123")
