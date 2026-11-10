"""
Document schemas for API requests and responses.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class IngestOptions(BaseModel):
    """Options for document ingestion"""

    ocr: str = Field(default="auto", description="OCR mode: auto|always|never")
    dpi: int = Field(default=350, description="DPI for OCR")
    language: str = Field(default="spa", description="OCR language code")


class IngestRequest(BaseModel):
    """Request to ingest a document"""

    filename: str = Field(..., description="Original filename")
    content_type: str = Field(..., description="MIME type")
    size_bytes: int = Field(..., description="File size")
    minio_key: str = Field(..., description="MinIO object key")
    conversation_id: Optional[str] = Field(None, description="Associated chat ID")
    options: IngestOptions = Field(default_factory=IngestOptions)


class PageContentResponse(BaseModel):
    """Page content in response"""

    page: int
    text_md: str
    has_table: bool
    table_csv_key: Optional[str] = None


class IngestResponse(BaseModel):
    """Response from document ingestion"""

    doc_id: str
    filename: str
    size_bytes: int
    total_pages: int
    pages: List[PageContentResponse]
    status: str
    ocr_applied: bool


class DocumentMetadata(BaseModel):
    """Document metadata"""

    doc_id: str
    filename: str
    content_type: str
    size_bytes: int
    total_pages: int
    status: str
    created_at: str
    minio_url: Optional[str] = None
