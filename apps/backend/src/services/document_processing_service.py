"""
Document Processing Service - SOLID refactored version.

Architecture:
- Service Layer: DocumentProcessingService (orchestration)
- Strategy Pattern: ITextSegmenter implementations
- Single Responsibility: Each class has one job
- Open/Closed: Easy to add new segmentation strategies
- Dependency Inversion: Depends on abstractions (ITextSegmenter)

Patterns:
- Service Layer (orchestration)
- Strategy Pattern (segmentation strategies)
- Template Method (processing flow)
"""

import tempfile
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from ..models.chat import ChatSession
from ..models.document import Document, PageContent
from ..models.document_state import ProcessingStatus
from ..services.document_extraction import extract_text_from_file
from ..services.embedding_service import get_embedding_service
from ..services.minio_service import minio_service
from ..services.weaviate_service import get_weaviate_service

logger = structlog.get_logger(__name__)


# ============================================================================
# STRATEGY PATTERN: Text Segmentation
# ============================================================================


class ITextSegmenter(ABC):
    """
    Interface for text segmentation strategies.

    Follows Open/Closed Principle: New strategies can be added without modifying existing code.
    """

    @abstractmethod
    def segment(self, text: str) -> List[Dict[str, Any]]:
        """
        Segment text into retrievable chunks.

        Args:
            text: Full document text

        Returns:
            List of segments with metadata
        """
        pass


class WordBasedSegmenter(ITextSegmenter):
    """
    Word-based segmentation with overlap.

    Single Responsibility: Only handles word-based chunking.
    """

    def __init__(self, chunk_size: int = 1000, overlap_ratio: float = 0.25):
        """
        Initialize segmenter.

        Args:
            chunk_size: Target words per chunk
            overlap_ratio: Overlap between chunks (0.0 to 0.5)
        """
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if not 0.0 <= overlap_ratio <= 0.5:
            raise ValueError("overlap_ratio must be between 0.0 and 0.5")

        self.chunk_size = chunk_size
        self.overlap_ratio = overlap_ratio
        self.overlap_words = int(chunk_size * overlap_ratio)

    def segment(self, text: str) -> List[Dict[str, Any]]:
        """Segment text using word-based chunking."""
        words = text.split()

        if not words:
            return []

        segments = []
        i = 0

        while i < len(words):
            # Extract chunk
            chunk_words = words[i : i + self.chunk_size]
            chunk_text = " ".join(chunk_words)

            segments.append(
                {
                    "index": len(segments),
                    "text": chunk_text,
                    "word_count": len(chunk_words),
                    "start_word": i,
                    "end_word": i + len(chunk_words),
                }
            )

            # Move forward with overlap
            i += self.chunk_size - self.overlap_words

        logger.debug(
            "Text segmented",
            total_words=len(words),
            segments_count=len(segments),
            chunk_size=self.chunk_size,
            overlap=self.overlap_words,
        )

        return segments


class SentenceBasedSegmenter(ITextSegmenter):
    """
    Sentence-based segmentation (future implementation).

    Uses sentence boundaries for more coherent chunks.
    """

    def __init__(self, sentences_per_chunk: int = 10):
        self.sentences_per_chunk = sentences_per_chunk

    def segment(self, text: str) -> List[Dict[str, Any]]:
        """Segment text using sentence boundaries."""
        # TODO: Implement with nltk.sent_tokenize or spacy
        # For now, fallback to word-based
        fallback = WordBasedSegmenter(chunk_size=400)
        return fallback.segment(text)


# ============================================================================
# SERVICE LAYER: Document Processing Orchestration
# ============================================================================


class DocumentProcessingService:
    """
    Service for document processing operations.

    Responsibilities:
    - Orchestrate document processing flow
    - Manage DocumentState lifecycle
    - Coordinate extraction, segmentation, caching

    Follows:
    - Single Responsibility: Only orchestrates processing
    - Dependency Inversion: Depends on ITextSegmenter abstraction
    - Open/Closed: Can use different segmenters without modification
    """

    def __init__(self, segmenter: Optional[ITextSegmenter] = None):
        """
        Initialize service.

        Args:
            segmenter: Text segmentation strategy (defaults to WordBasedSegmenter)
        """
        self.segmenter = segmenter or WordBasedSegmenter(
            chunk_size=400, overlap_ratio=0.25
        )

    async def process_document(self, conversation_id: str, doc_id: str) -> None:
        """
        Process document: extract → segment → cache.

        Template Method Pattern: Defines processing flow skeleton.

        Args:
            conversation_id: Chat session ID
            doc_id: Document ID to process

        Raises:
            ValueError: If session/document not found
            Exception: On processing errors (marks doc as FAILED)
        """

        logger.info(
            "[RAG] Starting document processing",
            conversation_id=conversation_id,
            doc_id=doc_id,
            timestamp=datetime.utcnow().isoformat(),
        )

        try:
            # Step 1: Validate session has the document
            session = await self._get_session(conversation_id)
            document = await self._validate_document_in_session(session, doc_id)

            # Step 2: Mark as processing (update Document model directly)
            document.status = "processing"
            await document.save()

            logger.info(
                "⏳ [RAG DEBUG] Document marked as PROCESSING",
                doc_id=str(document.id),
                status=document.status,
                timestamp=datetime.utcnow().isoformat(),
            )

            # Step 3: Extract pages (preserves page numbers)
            pages = await self._extract_pages(document)
            extracted_text = "\n\n".join(p.text_md for p in pages if p.text_md)

            if not extracted_text or not extracted_text.strip():
                raise ValueError("Text extraction returned empty result")

            # Step 4: Chunk by paragraphs per page and embed
            chunks_with_embeddings = await self._chunk_and_embed(
                extracted_text,
                document.filename or "unknown.pdf",
                pages=pages,
            )

            # Step 5: Store in Weaviate
            await self._store_in_weaviate(
                conversation_id=conversation_id,
                doc_id=doc_id,
                chunks=chunks_with_embeddings,
            )

            # Step 6: Mark as ready (update Document model directly)
            document.status = "ready"
            await document.save()

            logger.info(
                "[RAG] Document marked as READY",
                doc_id=str(document.id),
                status=document.status,
                chunks=len(chunks_with_embeddings),
                timestamp=datetime.utcnow().isoformat(),
            )

            logger.info(
                "✅ [RAG DEBUG] Document processing complete",
                doc_id=doc_id,
                chunks=len(chunks_with_embeddings),
                timestamp=datetime.utcnow().isoformat(),
            )

        except Exception as e:
            logger.error(
                "Document processing failed",
                conversation_id=conversation_id,
                doc_id=doc_id,
                error=str(e),
                exc_type=type(e).__name__,
                exc_info=True,
            )

            await self._mark_failed(conversation_id, doc_id, str(e))
            raise

    async def process_document_standalone(self, doc_id: str) -> None:
        """
        Process document without requiring a session (for upload-time processing).

        Chunks and embeds the document, storing in Weaviate with doc_id only.
        Session association happens later when document is used in chat.

        Args:
            doc_id: Document ID to process

        Raises:
            ValueError: If document not found
            Exception: On processing errors
        """
        logger.info(
            "[RAG] Starting standalone document processing",
            doc_id=doc_id,
            timestamp=datetime.utcnow().isoformat(),
        )

        try:
            # Step 1: Get document
            from ..models.document import Document

            document = await Document.get(doc_id)
            if not document:
                raise ValueError(f"Document {doc_id} not found")

            # Step 2: Get pages (from cache or re-extract)
            if document.pages and len(document.pages) > 0:
                pages = document.pages
                logger.info(
                    "Using cached document pages",
                    doc_id=doc_id,
                    pages=len(pages),
                )
            else:
                logger.info("No pages found, extracting text...", doc_id=doc_id)
                pages = await self._extract_pages(document)

            extracted_text = "\n\n".join(p.text_md for p in pages if p.text_md)

            # Step 3: Chunk by paragraphs per page and embed
            chunks_with_embeddings = await self._chunk_and_embed(
                extracted_text,
                document.filename or "unknown.pdf",
                pages=pages,
            )

            # Step 4: Store in Weaviate (use doc_id as session_id for standalone processing)
            await self._store_in_weaviate(
                conversation_id=f"upload_{doc_id}",  # Temporary session ID
                doc_id=doc_id,
                chunks=chunks_with_embeddings,
            )

            logger.info(
                "✅ [RAG DEBUG] Standalone document processing complete",
                doc_id=doc_id,
                chunks=len(chunks_with_embeddings),
                timestamp=datetime.utcnow().isoformat(),
            )

        except Exception as e:
            logger.error(
                "Standalone document processing failed",
                doc_id=doc_id,
                error=str(e),
                exc_type=type(e).__name__,
                exc_info=True,
            )
            raise

    async def reprocess_document(self, conversation_id: str, doc_id: str) -> None:
        """
        Reprocess a document (useful for failed/stale documents).

        Args:
            conversation_id: Chat session ID
            doc_id: Document ID to reprocess
        """
        logger.info(
            "Reprocessing document", conversation_id=conversation_id, doc_id=doc_id
        )

        session = await self._get_session(conversation_id)
        doc_state = await self._validate_document_in_session(session, doc_id)

        # Reset to UPLOADING
        doc_state.status = ProcessingStatus.UPLOADING
        doc_state.error = None
        doc_state.updated_at = datetime.utcnow()
        await session.save()

        # Trigger processing
        await self.process_document(conversation_id, doc_id)

    # ========================================================================
    # PRIVATE METHODS: Processing Steps (Template Method Pattern)
    # ========================================================================

    async def _get_session(self, conversation_id: str) -> ChatSession:
        """Get and validate chat session."""
        session = await ChatSession.get(conversation_id)
        if not session:
            raise ValueError(f"Session {conversation_id} not found")
        return session

    async def _validate_document_in_session(
        self, session: ChatSession, doc_id: str
    ) -> Any:  # DocumentState
        """Validate document exists in session's attached_file_ids."""
        # NEW: Check attached_file_ids instead of documents field
        if doc_id not in session.attached_file_ids:
            raise ValueError(f"Document {doc_id} not in session {session.id}")

        # Fetch the actual Document from the database
        from ..models.document import Document

        doc = await Document.get(doc_id)
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database")

        return doc

    async def _mark_processing(self, session: ChatSession, doc_state: Any) -> None:
        """Update DocumentState to PROCESSING."""
        doc_state.mark_processing()
        await session.save()

        logger.info(
            "⏳ [RAG DEBUG] Document marked as PROCESSING",
            doc_id=doc_state.doc_id,
            status=doc_state.status.value,
            timestamp=datetime.utcnow().isoformat(),
        )

    async def _get_document_from_storage(self, doc_id: str) -> Document:
        """Fetch document from MongoDB storage."""
        document = await Document.get(doc_id)
        if not document:
            raise ValueError(f"Document {doc_id} not found in storage")
        return document

    async def _extract_text(self, document: Document) -> str:
        """
        Extract text from document using multi-tier strategy.

        Post-MinIO Migration:
        - Downloads file from MinIO to temp location
        - Extracts text from temp file
        - Cleans up temp file after extraction
        """
        pages = await self._extract_pages(document)
        extracted_text = "\n\n".join(page.text_md for page in pages if page.text_md)

        if not extracted_text or not extracted_text.strip():
            raise ValueError("Text extraction returned empty result")

        return extracted_text

    async def _extract_pages(self, document: Document) -> List[PageContent]:
        """
        Extract pages from document preserving per-page structure.

        Returns list of PageContent objects, each with page number and text.
        """
        suffix = Path(document.filename).suffix if document.filename else ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = Path(tmp.name)

        try:
            logger.info(
                "📥 Downloading file from MinIO for text extraction",
                doc_id=str(document.id),
                minio_bucket=document.minio_bucket,
                minio_key=document.minio_key,
                filename=document.filename,
                temp_path=str(tmp_path),
            )

            await minio_service.download_to_path(
                document.minio_bucket, document.minio_key, str(tmp_path)
            )

            pages: List[PageContent] = await extract_text_from_file(
                file_path=tmp_path, content_type=document.content_type
            )

            logger.info(
                "📄 [RAG DEBUG] Text extraction complete",
                doc_id=str(document.id),
                text_length=sum(len(p.text_md) for p in pages if p.text_md),
                pages=len(pages),
                filename=document.filename,
                timestamp=datetime.utcnow().isoformat(),
            )

            return pages

        finally:
            tmp_path.unlink(missing_ok=True)
            logger.debug(
                "🗑️ Cleaned up temp file after extraction",
                temp_path=str(tmp_path),
                doc_id=str(document.id),
            )

    async def _chunk_and_embed(
        self,
        text: str,
        filename: str,
        pages: Optional[List[PageContent]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Chunk text and generate embeddings using EmbeddingService.

        When *pages* are provided, uses paragraph-aware chunking per page
        so that each chunk preserves its source page number. Falls back to
        the legacy flat chunking when pages are unavailable.

        Args:
            text: Extracted document text (used as fallback).
            filename: Document filename (for metadata).
            pages: Optional list of PageContent objects with per-page text.

        Returns:
            List of chunks with embeddings, ready for Weaviate storage.
        """
        embedding_service = get_embedding_service()

        if pages:
            # Page-aware paragraph chunking — preserves page numbers
            page_dicts = [
                {"page": p.page, "text": p.text_md}
                for p in pages
                if p.text_md and p.text_md.strip()
            ]
            chunks_with_embeddings = embedding_service.chunk_pages_and_embed(
                pages=page_dicts,
                metadata={"filename": filename},
                batch_size=32,
            )
        else:
            # Legacy flat chunking (no page info available)
            chunks_with_embeddings = embedding_service.chunk_and_embed(
                text=text,
                page=0,
                metadata={"filename": filename},
                batch_size=32,
            )

        logger.info(
            "🧩 [RAG DEBUG] Text chunked and embedded",
            chunks_count=len(chunks_with_embeddings),
            embedding_dim=(
                len(chunks_with_embeddings[0]["embedding"])
                if chunks_with_embeddings
                else 0
            ),
            filename=filename,
            text_length=len(text),
            chunking_strategy="paragraph_per_page" if pages else "sliding_window",
            timestamp=datetime.utcnow().isoformat(),
        )

        return chunks_with_embeddings

    async def _store_in_weaviate(
        self, conversation_id: str, doc_id: str, chunks: List[Dict[str, Any]]
    ) -> None:
        """
        Store chunks with embeddings in Weaviate vector database.

        NEW: Replaces Redis cache with Weaviate for semantic search.

        TTL Strategy:
        - 24-hour session lifetime (configured in Weaviate cleanup job)
        - Automatic cleanup via weaviate_service.cleanup_expired_sessions()
        - Session isolation via mandatory session_id filter

        Args:
            conversation_id: Session ID (for isolation)
            doc_id: Document ID
            chunks: Chunks with embeddings from EmbeddingService
        """
        weaviate_service = get_weaviate_service()

        # Upsert chunks to Weaviate
        points_count = weaviate_service.upsert_chunks(
            session_id=conversation_id, document_id=doc_id, chunks=chunks
        )

        logger.info(
            "💾 [RAG DEBUG] Chunks stored in Weaviate",
            doc_id=doc_id,
            session_id=conversation_id,
            points_upserted=points_count,
            chunks=len(chunks),
            timestamp=datetime.utcnow().isoformat(),
        )

    async def _mark_ready(
        self, session: ChatSession, doc_state: Any, segments_count: int
    ) -> None:
        """Update DocumentState to READY."""
        doc_state.mark_ready(segments_count=segments_count)
        await session.save()

        logger.info(
            "[RAG] Document marked as READY",
            doc_id=doc_state.doc_id,
            status=doc_state.status.value,
            segments=segments_count,
            timestamp=datetime.utcnow().isoformat(),
        )

    async def _mark_failed(self, conversation_id: str, doc_id: str, error: str) -> None:
        """Mark document as FAILED with error message."""
        try:
            # NEW: Update Document model directly instead of DocumentState
            from ..models.document import Document

            document = await Document.get(doc_id)
            if document:
                document.status = "failed"
                document.error_message = error[:500]
                await document.save()

                logger.info(
                    "Document marked as failed", doc_id=doc_id, error=error[:100]
                )
        except Exception as save_error:
            logger.error(
                "Failed to mark document as failed",
                doc_id=doc_id,
                error=str(save_error),
                exc_info=True,
            )


# ============================================================================
# FACTORY: Create service instances
# ============================================================================


def create_document_processing_service(
    segmentation_strategy: str = "word_based",
) -> DocumentProcessingService:
    """
    Factory function to create DocumentProcessingService with specific strategy.

    Args:
        segmentation_strategy: "word_based" | "sentence_based"

    Returns:
        Configured DocumentProcessingService instance
    """
    if segmentation_strategy == "word_based":
        segmenter = WordBasedSegmenter(chunk_size=400, overlap_ratio=0.25)
    elif segmentation_strategy == "sentence_based":
        segmenter = SentenceBasedSegmenter(sentences_per_chunk=10)
    else:
        raise ValueError(f"Unknown segmentation strategy: {segmentation_strategy}")

    return DocumentProcessingService(segmenter=segmenter)
