"""
Document model for PDF/IMG storage and metadata.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Union

from beanie import Document as BeanieDocument
from beanie import PydanticObjectId
from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    """Document processing status"""

    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class PageContent(BaseModel):
    """Page content extracted from document (embedded in Document)"""

    page: int = Field(..., description="Page number (1-indexed)")
    text_md: str = Field(..., description="Markdown content")
    has_table: bool = Field(default=False, description="Contains tables")
    table_csv_key: Optional[str] = Field(None, description="S3 key for CSV table")
    has_images: bool = Field(default=False, description="Contains images")
    image_keys: List[str] = Field(
        default_factory=list, description="S3 keys for images"
    )


class PageFragment(BaseModel):
    """
    Page fragment for validation/auditing (simplified from PageContent).
    Used by compliance auditors to analyze document fragments.
    """

    fragment_id: str = Field(..., description="Unique fragment identifier")
    page: int = Field(..., description="Page number (1-indexed)")
    kind: Optional[str] = Field(
        None, description="Fragment type: footer, paragraph, header, etc."
    )
    text: str = Field(..., description="Plain text content")
    bbox: Optional[List[float]] = Field(
        None, description="Bounding box [x0, y0, x1, y1]"
    )
    font_name: Optional[str] = Field(None, description="Font family name if available")
    font_size: Optional[float] = Field(None, description="Font size in points")
    line_height: Optional[float] = Field(
        None, description="Line height or spacing metric"
    )

    @classmethod
    def from_page_content(cls, page_content: "PageContent") -> "PageFragment":
        """Create PageFragment from PageContent."""
        from uuid import uuid4

        return cls(
            fragment_id=f"page-{page_content.page}-{uuid4().hex[:8]}",
            page=page_content.page,
            text=page_content.text_md,
        )


class Document(BeanieDocument):
    """Document model for PDF/IMG files"""

    # Metadata
    filename: str = Field(..., description="Original filename")
    content_type: str = Field(..., description="MIME type")
    size_bytes: int = Field(..., description="File size in bytes")

    # Storage
    minio_key: str = Field(..., description="MinIO object key")
    minio_bucket: str = Field(default="documents", description="MinIO bucket")

    # Processing
    status: DocumentStatus = Field(
        default=DocumentStatus.UPLOADING, description="Processing status"
    )
    error_message: Optional[str] = Field(None, description="Error message if failed")

    # Content
    pages: List[PageContent] = Field(
        default_factory=list, description="Extracted pages"
    )
    total_pages: int = Field(default=0, description="Total number of pages")

    # OCR
    ocr_applied: bool = Field(default=False, description="OCR was applied")
    ocr_language: str = Field(default="spa", description="OCR language")

    # Ownership
    # Allow UUID strings and ObjectId for backward compatibility with mixed storage
    user_id: Union[str, PydanticObjectId] = Field(..., description="Owner user ID")
    conversation_id: Optional[str] = Field(None, description="Associated chat ID")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = Field(
        None, description="When processing completed"
    )

    class Settings:
        name = "documents"
        indexes = [
            "user_id",
            "conversation_id",
            "created_at",
            "status",
            [("user_id", 1), ("created_at", -1)],  # User's recent documents
            [("user_id", 1), ("status", 1)],  # User documents by status (filtering)
        ]
