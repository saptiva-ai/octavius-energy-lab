"""
File upload endpoint.
"""

import hashlib
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import filetype
import structlog
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from ..config import get_settings
from ..services.minio_client import get_minio_client
from ..services.extraction import extract_text_from_file
from ..services.redis_client import get_extraction_cache

logger = structlog.get_logger(__name__)
router = APIRouter()
settings = get_settings()


class UploadResponse(BaseModel):
    """Response model for file upload."""

    file_id: str
    filename: str
    size: int
    mime_type: str
    minio_key: str
    sha256: str
    extracted_text: Optional[str] = None
    pages: Optional[int] = None


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    session_id: Optional[str] = Form(None),
):
    """
    Upload a file to storage.

    Accepts PDF and image files. Extracts text and caches it.

    Args:
        file: The file to upload
        user_id: Owner user ID
        session_id: Optional chat session ID

    Returns:
        File metadata including extracted text
    """
    # Validate content type
    if file.content_type not in settings.supported_types_list:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}. Supported: {settings.supported_types_list}",
        )

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Validate file size
    if file_size > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {settings.max_file_size_mb}MB",
        )

    # Validate magic bytes
    detected = filetype.guess(content)
    if detected is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Could not detect file type from content",
        )

    # Calculate hash
    sha256 = hashlib.sha256(content).hexdigest()

    # Generate file ID and path
    file_id = uuid.uuid4().hex
    filename = file.filename or f"file_{file_id}"
    extension = Path(filename).suffix or f".{detected.extension}"

    # Build MinIO object path
    session_part = session_id or "general"
    minio_key = f"{user_id}/{session_part}/{file_id}{extension}"

    logger.info(
        "Uploading file",
        file_id=file_id,
        filename=filename,
        size=file_size,
        content_type=file.content_type,
        user_id=user_id,
    )

    # Upload to MinIO
    minio = get_minio_client()
    import io
    minio.upload_file(
        object_name=minio_key,
        data=io.BytesIO(content),
        length=file_size,
        content_type=file.content_type,
        metadata={
            "user_id": user_id,
            "session_id": session_id or "",
            "original_filename": filename,
            "sha256": sha256,
        },
    )

    # Extract text
    extracted_text = None
    pages = None

    try:
        # Write to temp file for extraction
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        text, page_count = await extract_text_from_file(tmp_path, file.content_type)
        extracted_text = text
        pages = page_count

        # Cache extraction
        cache = get_extraction_cache()
        await cache.set(
            file_id=file_id,
            text=text,
            pages=page_count,
            metadata={
                "filename": filename,
                "content_type": file.content_type,
                "size": file_size,
            },
        )

        # Cleanup temp file
        tmp_path.unlink(missing_ok=True)

    except Exception as e:
        logger.warning("Text extraction failed", file_id=file_id, error=str(e))
        # Don't fail upload if extraction fails

    logger.info(
        "File uploaded successfully",
        file_id=file_id,
        minio_key=minio_key,
        text_length=len(extracted_text) if extracted_text else 0,
    )

    return UploadResponse(
        file_id=file_id,
        filename=filename,
        size=file_size,
        mime_type=file.content_type,
        minio_key=minio_key,
        sha256=sha256,
        extracted_text=extracted_text,
        pages=pages,
    )
