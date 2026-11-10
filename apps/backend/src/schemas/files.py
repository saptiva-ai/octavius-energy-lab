"""
Schemas for unified file ingestion/tooling.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FileStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class FileError(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    detail: Optional[str] = Field(None, description="Human-readable detail")


class FileIngestResponse(BaseModel):
    file_id: str = Field(..., description="Unique ID of the uploaded file")
    doc_id: Optional[str] = Field(None, description="Alias for backward compatibility")
    status: FileStatus = Field(..., description="Current processing status")
    mimetype: Optional[str] = Field(None, description="Original MIME type")
    bytes: int = Field(..., description="Number of bytes received")
    pages: Optional[int] = Field(
        None, description="Extracted page count when applicable"
    )
    name: Optional[str] = Field(None, description="Original filename")
    filename: Optional[str] = Field(None, description="Alias for original filename")
    error: Optional[FileError] = Field(
        None, description="Error information when status=FAILED"
    )


class FileIngestBulkResponse(BaseModel):
    files: list[FileIngestResponse] = Field(
        default_factory=list, description="Uploaded files"
    )


class FileEventPhase(str, Enum):
    UPLOAD = "upload"
    EXTRACT = "extract"
    CACHE = "cache"
    COMPLETE = "complete"


class FileEventPayload(BaseModel):
    file_id: str
    phase: FileEventPhase
    pct: float = Field(..., ge=0.0, le=100.0)
    trace_id: Optional[str] = None
    status: Optional[FileStatus] = None
    error: Optional[FileError] = None
    # Additional metadata for READY events
    mimetype: Optional[str] = None
    pages: Optional[int] = None
