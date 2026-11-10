"""
File download endpoint.
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response, StreamingResponse
import structlog
import io

from ..services.minio_client import get_minio_client

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/download/{file_path:path}")
async def download_file(file_path: str):
    """
    Download a file from storage.

    Args:
        file_path: Full MinIO object path (user_id/session_id/file_id.ext)

    Returns:
        File content as binary stream
    """
    minio = get_minio_client()

    # Check if file exists
    if not minio.file_exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {file_path}",
        )

    try:
        # Get file info for headers
        info = minio.get_file_info(file_path)

        # Download file
        content = minio.download_file(file_path)

        # Extract filename from path
        filename = file_path.split("/")[-1]

        logger.info(
            "File downloaded",
            file_path=file_path,
            size=len(content),
        )

        return Response(
            content=content,
            media_type=info.get("content_type", "application/octet-stream"),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(content)),
                "X-File-Size": str(info.get("size", 0)),
                "X-Filename": filename,
            },
        )

    except Exception as e:
        logger.error("Failed to download file", file_path=file_path, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download file: {str(e)}",
        )


@router.get("/download/{file_path:path}/stream")
async def stream_file(file_path: str):
    """
    Stream a file from storage (for large files).

    Args:
        file_path: Full MinIO object path

    Returns:
        Streaming response
    """
    minio = get_minio_client()

    if not minio.file_exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {file_path}",
        )

    try:
        info = minio.get_file_info(file_path)
        content = minio.download_file(file_path)
        filename = file_path.split("/")[-1]

        def iter_content():
            chunk_size = 1024 * 1024  # 1MB chunks
            for i in range(0, len(content), chunk_size):
                yield content[i:i + chunk_size]

        return StreamingResponse(
            iter_content(),
            media_type=info.get("content_type", "application/octet-stream"),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(content)),
            },
        )

    except Exception as e:
        logger.error("Failed to stream file", file_path=file_path, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stream file: {str(e)}",
        )


@router.get("/presigned/{file_path:path}")
async def get_presigned_url(file_path: str, expires_hours: int = 1):
    """
    Generate a presigned URL for direct download.

    Args:
        file_path: Full MinIO object path
        expires_hours: URL expiration time in hours (default: 1)

    Returns:
        Presigned URL
    """
    minio = get_minio_client()

    if not minio.file_exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {file_path}",
        )

    try:
        from datetime import timedelta
        url = minio.get_presigned_url(
            object_name=file_path,
            expires=timedelta(hours=expires_hours),
        )

        return {"url": url, "expires_in_hours": expires_hours}

    except Exception as e:
        logger.error("Failed to generate presigned URL", file_path=file_path, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate URL: {str(e)}",
        )
