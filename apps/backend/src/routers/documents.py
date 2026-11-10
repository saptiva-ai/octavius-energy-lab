"""
Document ingestion router - handles PDF/IMG upload and processing.

V1 Simplified: Uses filesystem temp storage + Redis cache
V2 (Future): Uncomment MinIO code for persistent storage
"""

import uuid
from pathlib import Path
from typing import Optional

import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse, Response

from ..core.auth import get_current_user
from ..core.redis_cache import get_redis_cache
from ..models.document import Document
from ..models.user import User
from ..schemas.document import DocumentMetadata, IngestResponse, PageContentResponse
from ..services.file_ingest import file_ingest_service
from ..services.mcp_cache import invalidate_document_tool_cache
from ..services.thumbnail_service import thumbnail_service

# V2 Future: MinIO persistent storage
# from ..services.minio_service import minio_service

logger = structlog.get_logger(__name__)

# V1: Redis TTL for document text cache (1 hour)
REDIS_DOCUMENT_TTL = 3600

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", deprecated=True, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
    ocr: str = Form("auto"),
    dpi: int = Form(350),
    language: str = Form("spa"),
    current_user: User = Depends(get_current_user),
):
    """
    **DEPRECATED**: Use `/api/files/upload` instead.

    This endpoint redirects (307) to the unified files endpoint.
    Legacy params (ocr, dpi, language) are ignored.

    Redirect: POST /api/files/upload
    """
    # Redirect 307: Client re-sends POST with same body to new URL
    return RedirectResponse(
        url="/api/files/upload", status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )


@router.post(
    "/upload-legacy", response_model=IngestResponse, status_code=status.HTTP_201_CREATED
)
async def upload_document_legacy(
    request: Request,
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
    ocr: str = Form("auto"),
    dpi: int = Form(350),
    language: str = Form("spa"),
    current_user: User = Depends(get_current_user),
):
    """
    **LEGACY FALLBACK**: Direct upload without redirect (for old clients).

    Prefer using `/api/files/upload` for new integrations.
    """
    trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
    request.state.trace_id = trace_id
    idempotency_key = request.headers.get("Idempotency-Key")

    logger.info(
        "Document upload started",
        filename=file.filename,
        content_type=file.content_type,
        user_id=str(current_user.id),
        trace_id=trace_id,
    )

    # Validate file type
    allowed_types = ["application/pdf", "image/png", "image/jpeg", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Allowed: {allowed_types}",
        )

    try:
        ingest_response = await file_ingest_service.ingest_file(
            user_id=str(current_user.id),
            upload=file,
            trace_id=trace_id,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
        )

        document = await Document.get(ingest_response.file_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Document not found after ingestion",
            )

        return IngestResponse(
            doc_id=str(document.id),
            filename=document.filename,
            size_bytes=document.size_bytes,
            total_pages=document.total_pages,
            pages=[
                PageContentResponse(
                    page=p.page,
                    text_md=(
                        p.text_md[:200] + "..." if len(p.text_md) > 200 else p.text_md
                    ),
                    has_table=p.has_table,
                    table_csv_key=p.table_csv_key,
                )
                for p in document.pages
            ],
            status=document.status.value,
            ocr_applied=document.ocr_applied,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Document upload failed", error=str(exc), filename=file.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document processing failed",
        ) from exc


@router.get("", response_model=list[DocumentMetadata])
async def list_documents(
    conversation_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
):
    """
    List documents for the current user.

    Args:
        conversation_id: Optional filter by conversation/chat session
        limit: Maximum number of documents to return (default: 50)
        offset: Number of documents to skip (default: 0)
    """
    from ..models.chat import ChatSession

    # If conversation_id provided, get documents attached to that session
    if conversation_id:
        session = await ChatSession.get(conversation_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        # Check ownership
        if session.user_id != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this conversation",
            )

        # ISSUE-012: Apply pagination to session documents
        # Get documents by IDs from session with pagination
        file_ids_page = session.attached_file_ids[offset : offset + limit]
        documents = []
        for doc_id in file_ids_page:
            doc = await Document.get(doc_id)
            if doc and doc.user_id == str(current_user.id):
                documents.append(doc)
    else:
        # ISSUE-012: List user's documents with pagination
        documents = (
            await Document.find(Document.user_id == str(current_user.id))
            .skip(offset)
            .limit(limit)
            .to_list()
        )

    # Convert to response format
    return [
        DocumentMetadata(
            doc_id=str(doc.id),
            filename=doc.filename,
            content_type=doc.content_type,
            size_bytes=doc.size_bytes,
            total_pages=doc.total_pages,
            status=doc.status.value,
            created_at=doc.created_at.isoformat(),
            minio_url=None,  # V1: Always None for temp storage
        )
        for doc in documents
    ]


@router.get("/{doc_id}", response_model=DocumentMetadata)
async def get_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get document metadata"""
    doc = await Document.get(doc_id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Check ownership
    if doc.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this document",
        )

    # V1: No presigned URLs for temp files (they're server-side only)
    # V2 Future: Generate presigned URL for MinIO
    # minio_url = None
    # if doc.status == DocumentStatus.READY:
    #     minio_url = minio_service.get_presigned_url(doc.minio_bucket, doc.minio_key)

    return DocumentMetadata(
        doc_id=str(doc.id),
        filename=doc.filename,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        total_pages=doc.total_pages,
        status=doc.status.value,
        created_at=doc.created_at.isoformat(),
        minio_url=None,  # V1: Always None for temp storage
    )


@router.get(
    "/{doc_id}/thumbnail",
    responses={
        200: {
            "content": {"image/jpeg": {}},
            "description": "JPEG thumbnail (256x384px portrait, quality 85%)",
        },
        404: {"description": "Document not found or thumbnail generation failed"},
    },
)
async def get_document_thumbnail(
    doc_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get high-quality portrait thumbnail for document preview

    - **PDFs**: First page rasterized to 256x384px JPEG (portrait, 2x DPI)
    - **Images**: Resized to max 256x384px JPEG (portrait)
    - **Other files**: Returns 404

    Thumbnails are generated on-the-fly (not cached).
    Used by frontend PreviewAttachment component.
    """
    doc = await Document.get(doc_id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Check ownership
    if doc.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this document",
        )

    # V2: Get or generate thumbnail with MinIO caching
    # This handles both new documents (MinIO) and legacy documents (filesystem)

    # Check if this is a legacy document (filesystem path)
    is_legacy = (
        doc.minio_bucket == "temp"
        and doc.minio_key
        and doc.minio_key.startswith("/tmp/")
    )

    if is_legacy:
        # Try to migrate legacy file from /tmp/ to MinIO
        legacy_path = Path(doc.minio_key) if doc.minio_key else None
        if legacy_path and legacy_path.exists():
            try:
                from ..services.minio_service import minio_service as _minio

                new_key = f"documents/{doc_id}/{doc.filename}"
                with legacy_path.open("rb") as f:
                    await _minio.upload_file(
                        _minio.documents_bucket,
                        new_key,
                        f,
                        legacy_path.stat().st_size,
                        content_type=doc.content_type,
                    )
                doc.minio_bucket = _minio.documents_bucket
                doc.minio_key = new_key
                await doc.save()
                logger.info(
                    "Migrated legacy document to MinIO",
                    doc_id=doc_id,
                    new_key=new_key,
                )
                # Now generate thumbnail from the migrated file
                thumbnail_bytes = await thumbnail_service.get_or_generate_thumbnail(
                    doc_id=doc_id,
                    minio_bucket=doc.minio_bucket,
                    minio_key=doc.minio_key,
                    mimetype=doc.content_type,
                )
            except Exception as mig_err:
                logger.warning(
                    "Legacy migration failed, serving without thumbnail",
                    doc_id=doc_id,
                    error=str(mig_err),
                )
                thumbnail_bytes = None
        else:
            # File gone from /tmp/ — tell frontend to re-upload
            logger.warning(
                "Legacy document file not found on disk",
                doc_id=doc_id,
                minio_key=doc.minio_key,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thumbnail not available for this document. Please re-upload the file.",
                headers={"X-Reupload-Required": "true"},
            )
    else:
        # V2: Use MinIO-cached thumbnail generation
        thumbnail_bytes = await thumbnail_service.get_or_generate_thumbnail(
            doc_id=doc_id,
            minio_bucket=doc.minio_bucket,
            minio_key=doc.minio_key,
            mimetype=doc.content_type,
        )

    if not thumbnail_bytes:
        logger.warning(
            "Failed to generate thumbnail", doc_id=doc_id, mimetype=doc.content_type
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail generation not supported for this file type",
        )

    logger.info(
        "Serving thumbnail",
        doc_id=doc_id,
        filename=doc.filename,
        bytes=len(thumbnail_bytes),
    )

    # Encode filename for HTTP header (RFC 5987) to handle Unicode characters
    from urllib.parse import quote

    safe_filename = quote(f"thumbnail_{doc.filename}.jpg")

    return Response(
        content=thumbnail_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            "Content-Disposition": f"inline; filename*=UTF-8''{safe_filename}",
        },
    )


@router.get("/{doc_id}/thumbnail-url")
async def get_document_thumbnail_url(
    doc_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get presigned URL for document thumbnail.

    Returns a direct MinIO URL that the browser can use to load the thumbnail
    without proxying through the backend. Only works when MINIO_PUBLIC_ENDPOINT
    is configured (MinIO accessible from browser).

    Falls back to 501 if MinIO is not publicly accessible.
    """
    import os

    public_endpoint = os.getenv("MINIO_PUBLIC_ENDPOINT")
    if not public_endpoint:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Presigned URLs not available — MINIO_PUBLIC_ENDPOINT not configured",
        )

    doc = await Document.get(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if doc.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this document",
        )

    from ..services.minio_service import minio_service as _minio

    thumbnail_key = f"{doc_id}.jpg"

    # Ensure thumbnail exists (generate if needed)
    try:
        thumbnail_bytes = await thumbnail_service.get_or_generate_thumbnail(
            doc_id=doc_id,
            minio_bucket=doc.minio_bucket,
            minio_key=doc.minio_key,
            mimetype=doc.content_type,
        )
        if not thumbnail_bytes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thumbnail generation not supported for this file type",
            )
    except HTTPException:
        raise
    except Exception as gen_err:
        logger.error(
            "Thumbnail generation failed for presigned URL",
            doc_id=doc_id,
            error=str(gen_err),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate thumbnail",
        ) from gen_err

    try:
        url = _minio.get_presigned_url(_minio.thumbnails_bucket, thumbnail_key)
        # Replace internal endpoint with public endpoint
        internal_endpoint = _minio.endpoint
        url = url.replace(internal_endpoint, public_endpoint, 1)

        return {"url": url, "expires_in": 3600}
    except Exception as url_err:
        logger.error(
            "Failed to generate presigned URL",
            doc_id=doc_id,
            error=str(url_err),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate presigned URL",
        ) from url_err


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete document"""
    doc = await Document.get(doc_id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Check ownership
    if doc.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this document",
        )

    # V1: Delete from filesystem and Redis
    try:
        # Delete temp file
        temp_path = Path(doc.minio_key)  # V1: minio_key stores filesystem path
        if temp_path.exists():
            temp_path.unlink()
            logger.info("Deleted temp file", path=str(temp_path))

        # Delete from Redis cache (document text)
        redis_cache = await get_redis_cache()
        redis_client = redis_cache.client
        await redis_client.delete(f"doc:text:{doc_id}")
        logger.info("Deleted from Redis cache", doc_id=doc_id)

        # Invalidate MCP tool caches (Excel analysis, audit results, etc.)
        invalidated_count = await invalidate_document_tool_cache(doc_id)
        if invalidated_count > 0:
            logger.info(
                "Invalidated MCP tool caches",
                doc_id=doc_id,
                invalidated_count=invalidated_count,
            )

    except Exception as e:
        logger.error("Failed to delete temp files/caches", error=str(e), doc_id=doc_id)

    # V2 Future: Delete from MinIO
    # try:
    #     await minio_service.delete_file(doc.minio_bucket, doc.minio_key)
    # except Exception as e:
    #     logger.error("Failed to delete from MinIO", error=str(e), doc_id=doc_id)

    # Delete document record
    await doc.delete()

    logger.info("Document deleted", doc_id=doc_id)
