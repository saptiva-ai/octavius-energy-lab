"""
Document lifecycle state model for chat sessions.

Replaces simple List[str] with structured state machine.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ProcessingStatus(str, Enum):
    """Document processing lifecycle states"""

    UPLOADING = "uploading"  # File being uploaded to storage
    PROCESSING = "processing"  # OCR/extraction in progress
    SEGMENTING = "segmenting"  # Breaking into searchable chunks
    INDEXING = "indexing"  # Building embeddings (optional)
    READY = "ready"  # Available for RAG
    FAILED = "failed"  # Processing failed (with error message)
    ARCHIVED = "archived"  # Removed from active context


class DocumentState(BaseModel):
    """
    Structured state for a document within a conversation.

    Lifecycle:
    UPLOADING → PROCESSING → SEGMENTING → [INDEXING] → READY
                     ↓
                  FAILED

    Example:
        >>> doc = DocumentState(
        ...     doc_id="doc-123",
        ...     name="report.pdf",
        ...     pages=32
        ... )
        >>> doc.mark_processing()
        >>> doc.mark_ready(segments_count=15)
        >>> assert doc.is_ready()
    """

    # Core identity
    doc_id: str = Field(..., description="Document ID (from Document model)")
    name: str = Field(..., description="Original filename")

    # Processing state
    status: ProcessingStatus = Field(
        default=ProcessingStatus.UPLOADING, description="Current processing status"
    )
    error: Optional[str] = Field(None, description="Error message if status=FAILED")

    # Document metadata
    pages: Optional[int] = Field(None, description="Number of pages (PDFs)")
    size_bytes: Optional[int] = Field(None, description="File size")
    mimetype: Optional[str] = Field(None, description="MIME type")

    # Processing results
    segments_count: int = Field(
        default=0, description="Number of text segments extracted"
    )
    indexed_at: Optional[datetime] = Field(
        None, description="When indexing completed (if status=READY)"
    )

    # RAG metadata (optional, for future vector search)
    has_embeddings: bool = Field(
        default=False, description="Whether embeddings were generated"
    )
    vector_store_ref: Optional[str] = Field(
        None, description="Reference to vector store collection/index"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When document was added to conversation",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last status update"
    )

    def mark_processing(self) -> None:
        """Transition to PROCESSING state"""
        self.status = ProcessingStatus.PROCESSING
        self.updated_at = datetime.utcnow()

    def mark_segmenting(self) -> None:
        """Transition to SEGMENTING state"""
        self.status = ProcessingStatus.SEGMENTING
        self.updated_at = datetime.utcnow()

    def mark_ready(self, segments_count: int) -> None:
        """
        Transition to READY state.

        Args:
            segments_count: Number of segments extracted
        """
        self.status = ProcessingStatus.READY
        self.segments_count = segments_count
        self.indexed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def mark_failed(self, error: str) -> None:
        """
        Transition to FAILED state.

        Args:
            error: Error message (will be truncated to 500 chars)
        """
        self.status = ProcessingStatus.FAILED
        self.error = error[:500]  # Truncate long errors
        self.updated_at = datetime.utcnow()

    def is_ready(self) -> bool:
        """Check if document is ready for RAG"""
        return self.status == ProcessingStatus.READY

    def is_processing(self) -> bool:
        """Check if document is currently being processed"""
        return self.status in [
            ProcessingStatus.UPLOADING,
            ProcessingStatus.PROCESSING,
            ProcessingStatus.SEGMENTING,
            ProcessingStatus.INDEXING,
        ]

    def is_failed(self) -> bool:
        """Check if document processing failed"""
        return self.status == ProcessingStatus.FAILED

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat() if v else None}
    )
