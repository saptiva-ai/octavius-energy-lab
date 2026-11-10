"""
File metadata endpoint.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, status
from minio.error import S3Error
from pydantic import BaseModel
import structlog

from ..services.minio_client import get_minio_client
from ..services.redis_client import get_extraction_cache

logger = structlog.get_logger(__name__)
router = APIRouter()


class FileMetadata(BaseModel):
    """File metadata response model."""

    file_id: str
    filename: str
    size: int
    content_type: str
    minio_key: str
    extracted_text: Optional[str] = None
    pages: Optional[int] = None
    last_modified: Optional[str] = None


@router.get("/metadata/{file_path:path}", response_model=FileMetadata)
async def get_file_metadata(file_path: str, include_text: bool = True):
    """
    Get file metadata and optionally extracted text.

    Args:
        file_path: Full MinIO object path (user_id/session_id/file_id.ext)
        include_text: Whether to include extracted text (default: True)

    Returns:
        File metadata including extracted text if available
    """
    minio = get_minio_client()

    # Check if file exists
    if not minio.file_exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {file_path}",
        )

    try:
        # Get file info from MinIO
        info = minio.get_file_info(file_path)

        # Extract file_id from path (last segment without extension)
        filename = file_path.split("/")[-1]
        file_id = filename.rsplit(".", 1)[0] if "." in filename else filename

        # Get extracted text from cache if requested
        extracted_text = None
        pages = None

        if include_text:
            cache = get_extraction_cache()
            cached = await cache.get(file_id)

            if cached:
                extracted_text = cached.get("text")
                pages = cached.get("pages")

        logger.debug(
            "File metadata retrieved",
            file_path=file_path,
            has_text=extracted_text is not None,
        )

        return FileMetadata(
            file_id=file_id,
            filename=filename,
            size=info.get("size", 0),
            content_type=info.get("content_type", "application/octet-stream"),
            minio_key=file_path,
            extracted_text=extracted_text,
            pages=pages,
            last_modified=info.get("last_modified"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get file metadata", file_path=file_path, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get metadata: {str(e)}",
        )


@router.delete("/files/{file_path:path}")
async def delete_file(file_path: str):
    """
    Delete a file from storage.

    Args:
        file_path: Full MinIO object path

    Returns:
        Confirmation message
    """
    minio = get_minio_client()

    if not minio.file_exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {file_path}",
        )

    try:
        # Delete from MinIO
        minio.delete_file(file_path)

        # Delete from cache
        filename = file_path.split("/")[-1]
        file_id = filename.rsplit(".", 1)[0] if "." in filename else filename

        cache = get_extraction_cache()
        await cache.delete(file_id)

        logger.info("File deleted", file_path=file_path)

        return {"message": "File deleted successfully", "file_path": file_path}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete file", file_path=file_path, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file: {str(e)}",
        )


@router.post("/extract/{file_path:path}")
async def extract_text(file_path: str, force: bool = False):
    """
    Extract text from a file (re-extract if force=True).

    Args:
        file_path: Full MinIO object path
        force: Force re-extraction even if cached

    Returns:
        Extracted text and metadata
    """
    from ..services.extraction import extract_text_from_file
    import tempfile
    from pathlib import Path

    minio = get_minio_client()

    if not minio.file_exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {file_path}",
        )

    # Check cache first
    filename = file_path.split("/")[-1]
    file_id = filename.rsplit(".", 1)[0] if "." in filename else filename

    if not force:
        cache = get_extraction_cache()
        cached = await cache.get(file_id)
        if cached:
            return {
                "file_id": file_id,
                "text": cached.get("text", ""),
                "pages": cached.get("pages"),
                "source": "cache",
            }

    # Variable for cleanup
    tmp_path = None

    try:
        # Download file from MinIO
        logger.debug(
            "Downloading file from MinIO",
            file_path=file_path,
            bucket=minio.bucket
        )
        content = minio.download_file(file_path)

        # Get file metadata
        info = minio.get_file_info(file_path)
        content_type = info.get("content_type", "application/octet-stream")

        logger.debug(
            "File downloaded successfully",
            file_path=file_path,
            size=len(content),
            content_type=content_type
        )

        # Write to temp file
        extension = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        logger.debug(
            "Temp file created",
            tmp_path=str(tmp_path),
            size=len(content)
        )

        # Extract text
        text, pages = await extract_text_from_file(tmp_path, content_type)

        logger.info(
            "Text extraction completed",
            file_path=file_path,
            text_length=len(text),
            pages=pages
        )

        # Cache result
        cache = get_extraction_cache()
        await cache.set(
            file_id=file_id,
            text=text,
            pages=pages,
            metadata={
                "filename": filename,
                "content_type": content_type,
            },
        )

        logger.info(
            "Text extracted and cached",
            file_path=file_path,
            text_length=len(text),
            pages=pages,
        )

        return {
            "file_id": file_id,
            "text": text,
            "pages": pages,
            "source": "extraction",
        }

    except S3Error as e:
        # MinIO-specific error
        logger.error(
            "MinIO S3 error during extraction",
            file_path=file_path,
            error=str(e),
            error_code=getattr(e, 'code', None),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MinIO error: {str(e)}",
        )
    except ImportError as e:
        # Missing OCR dependencies
        logger.error(
            "Missing extraction dependencies",
            file_path=file_path,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Missing OCR dependencies: {str(e)}. Install pytesseract/fitz if needed.",
        )
    except Exception as e:
        # Generic error with full traceback
        logger.error(
            "Failed to extract text",
            file_path=file_path,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract text: {type(e).__name__}: {str(e)}",
        )
    finally:
        # Cleanup temp file
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink(missing_ok=True)
                logger.debug("Temp file cleaned up", tmp_path=str(tmp_path))
            except Exception as cleanup_err:
                logger.warning(
                    "Failed to cleanup temp file",
                    tmp_path=str(tmp_path),
                    error=str(cleanup_err)
                )
