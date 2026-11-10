"""
File ingestion service for the unified files tool.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from pathlib import Path
from typing import Optional

import filetype  # FIX ISSUE-011: Magic byte validation
import structlog
from fastapi import HTTPException, UploadFile, status

from ..core.config import get_settings
from ..core.redis_cache import get_redis_cache
from ..core.telemetry import (
    increment_pdf_ingest_error,
    increment_tool_invocation,
    record_doc_text_size,  # OBS-1: New metric
    record_pdf_ingest_phase,
)
from ..models.document import Document, DocumentStatus, PageContent
from ..schemas.files import (
    FileError,
    FileEventPayload,
    FileEventPhase,
    FileIngestResponse,
    FileStatus,
)
from .document_extraction import extract_text_from_file
from .document_processing_service import create_document_processing_service
from .file_events import file_event_bus
from .idempotency import upload_idempotency_repository
from .mcp_cache import invalidate_document_tool_cache
from .minio_service import minio_service
from .storage import FileTooLargeError, storage

logger = structlog.get_logger(__name__)

# Get max file size from settings (reads from MAX_FILE_SIZE env var)
# Fallback to 10MB for backwards compatibility
settings = get_settings()
MAX_UPLOAD_BYTES = settings.max_file_size
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/heic",
    "image/heif",
    "image/gif",
}


class FileIngestService:
    async def ingest_file(
        self,
        user_id: str,
        upload: UploadFile,
        trace_id: str,
        conversation_id: Optional[str],
        idempotency_key: Optional[str],
    ) -> FileIngestResponse:
        if upload.content_type not in SUPPORTED_MIME_TYPES:
            increment_pdf_ingest_error("unsupported_mime")
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file type: {upload.content_type}",
            )

        effective_key = idempotency_key
        if effective_key:
            effective_key = f"{effective_key}:{upload.filename or 'unnamed'}"
            cached = await upload_idempotency_repository.get(user_id, effective_key)
            if cached:
                cached_doc_id = getattr(cached, "doc_id", cached.file_id)
                logger.info(
                    "Idempotent file ingest hit",
                    user_id=user_id,
                    doc_id=cached_doc_id,
                    trace_id=trace_id,
                )
                return cached

        file_id = uuid.uuid4().hex
        await file_event_bus.publish(
            file_id,
            FileEventPayload(
                file_id=file_id,
                trace_id=trace_id,
                phase=FileEventPhase.UPLOAD,
                pct=0.0,
                status=FileStatus.RECEIVED,
            ),
        )

        increment_tool_invocation("files")

        # Persist upload to MinIO
        sha256 = hashlib.sha256()
        bytes_written = 0
        minio_bucket = None
        minio_key = None
        upload_started = time.time()
        try:
            (
                minio_bucket,
                minio_key,
                safe_name,
                bytes_written,
            ) = await storage.save_upload(file_id, upload, MAX_UPLOAD_BYTES)

            # FIX ISSUE-011: Validate magic bytes to prevent malicious files
            # Download from MinIO to temp file for validation
            import tempfile

            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)

            try:
                await minio_service.download_to_path(
                    minio_bucket, minio_key, str(tmp_path)
                )

                # Read first 8KB to detect file type (enough for most magic byte signatures)
                with tmp_path.open("rb") as file_obj:
                    header = file_obj.read(8192)
                    kind = filetype.guess(header)

                    # Validate that actual file type matches declared MIME type
                    if kind is None:
                        logger.warning(
                            "Could not detect file type from magic bytes",
                            filename=upload.filename,
                            declared_mime=upload.content_type,
                            file_id=file_id,
                        )
                        increment_pdf_ingest_error("unknown_magic_bytes")
                        raise HTTPException(
                            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="Could not verify file type. File may be corrupted or invalid.",
                        )

                    # Normalize MIME types for comparison (handle variations)
                    detected_mime = kind.mime
                    declared_mime = upload.content_type

                    # Allow image/jpg -> image/jpeg normalization
                    if declared_mime == "image/jpg":
                        declared_mime = "image/jpeg"

                    if detected_mime != declared_mime:
                        logger.error(
                            "File type mismatch - possible malicious file",
                            filename=upload.filename,
                            declared_mime=upload.content_type,
                            detected_mime=detected_mime,
                            file_id=file_id,
                        )
                        increment_pdf_ingest_error("mime_mismatch")
                        raise HTTPException(
                            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail=f"File type mismatch: declared '{upload.content_type}' but detected '{detected_mime}'",
                        )

                    logger.info(
                        "File type validated via magic bytes",
                        filename=upload.filename,
                        mime_type=detected_mime,
                        file_id=file_id,
                    )

                    # Compute hash
                    file_obj.seek(0)  # Reset to beginning
                    while True:
                        chunk = file_obj.read(1024 * 1024)
                        if not chunk:
                            break
                        sha256.update(chunk)
            finally:
                # Clean up temp file
                tmp_path.unlink(missing_ok=True)
        except FileTooLargeError as exc:
            await self._publish_failure(
                file_id,
                trace_id,
                FileError(code="UPLOAD_TOO_LARGE", detail=str(exc)),
            )
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large: {exc.size_bytes} bytes. Max: {exc.max_bytes} bytes",
            ) from exc
        record_pdf_ingest_phase("upload", time.time() - upload_started)

        digest = sha256.hexdigest()

        if not effective_key:
            effective_key = f"hash:{digest}:{conversation_id or 'no-chat'}"

        # DEDUPLICATION: Check if file with same hash already exists for this user
        from ..services.resource_lifecycle_manager import get_resource_manager

        resource_manager = get_resource_manager()

        existing_doc_id = await resource_manager.check_duplicate_file(
            file_hash=digest, user_id=user_id
        )

        if existing_doc_id:
            # File already exists - reuse it
            existing_doc = await Document.get(existing_doc_id)

            logger.info(
                "Duplicate file detected - reusing existing document",
                existing_doc_id=str(existing_doc_id),
                file_hash=digest[:16],
                filename=upload.filename,
                existing_filename=existing_doc.filename,
                user_id=user_id,
            )

            # Delete newly uploaded MinIO file (not needed)
            if minio_bucket and minio_key:
                try:
                    await minio_service.delete_file(minio_bucket, minio_key)
                    logger.info(
                        "Deleted duplicate file from MinIO", minio_key=minio_key
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to delete duplicate MinIO file", error=str(e)
                    )

            # Return existing document info
            response = FileIngestResponse(
                file_id=str(existing_doc_id),
                filename=existing_doc.filename,
                status=(
                    FileStatus.READY
                    if existing_doc.status == DocumentStatus.READY
                    else FileStatus.PROCESSING
                ),
                size_bytes=existing_doc.size_bytes,
                trace_id=trace_id,
            )

            # Cache response for idempotency
            if effective_key:
                await upload_idempotency_repository.set(
                    user_id, effective_key, response, ttl_seconds=3600
                )

            return response

        # Not a duplicate - create new document
        document = Document(
            filename=upload.filename,
            content_type=upload.content_type,
            size_bytes=bytes_written,
            minio_key=minio_key,
            minio_bucket=minio_bucket,
            status=DocumentStatus.PROCESSING,
            user_id=user_id,
            conversation_id=conversation_id,
            metadata={"file_hash": digest},  # Store hash for future deduplication
        )

        await document.insert()

        logger.info(
            "New document created with hash",
            file_id=str(document.id),
            file_hash=digest[:16],
            filename=upload.filename,
            user_id=user_id,
        )

        # Use document.id (MongoDB ObjectId) for all subsequent operations
        file_id = str(document.id)

        # ADAPTIVE PROCESSING: Small files sync, large files async
        # Threshold: 1 MB (PDFs with OCR or images process async)
        SIZE_THRESHOLD_BYTES = 1 * 1024 * 1024  # 1 MB

        if bytes_written < SIZE_THRESHOLD_BYTES:
            # SYNC PATH: Small files - process immediately and return READY
            logger.info(
                "Small file detected - processing synchronously",
                file_id=file_id,
                size_bytes=bytes_written,
                threshold_mb=SIZE_THRESHOLD_BYTES / (1024 * 1024),
            )

            extract_started = time.time()
            await file_event_bus.publish(
                file_id,
                FileEventPayload(
                    file_id=file_id,
                    trace_id=trace_id,
                    phase=FileEventPhase.EXTRACT,
                    pct=33.0,
                    status=FileStatus.PROCESSING,
                ),
            )
            try:
                # Download from MinIO to temp path for extraction
                import tempfile

                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=Path(upload.filename or "file").suffix
                ) as tmp:
                    tmp_extract_path = Path(tmp.name)

                try:
                    await minio_service.download_to_path(
                        minio_bucket, minio_key, str(tmp_extract_path)
                    )
                    pages = await extract_text_from_file(
                        tmp_extract_path, upload.content_type
                    )
                finally:
                    tmp_extract_path.unlink(missing_ok=True)
            except Exception as exc:
                await self._handle_failure(
                    document, file_id, trace_id, "EXTRACTION_FAILED", str(exc)
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Document processing failed",
                ) from exc
            record_pdf_ingest_phase("extract", time.time() - extract_started)

            cache_started = time.time()
            await self._cache_pages(file_id, pages)
            record_pdf_ingest_phase("cache", time.time() - cache_started)

            # OBS-1: Record extracted text size for observability
            total_text_size = sum(len(p.text_md) for p in pages)
            record_doc_text_size(upload.content_type, total_text_size)
            logger.info(
                "Document text extracted and cached",
                file_id=file_id,
                mimetype=upload.content_type,
                text_size_chars=total_text_size,
                total_pages=len(pages),
            )
            await file_event_bus.publish(
                file_id,
                FileEventPayload(
                    file_id=file_id,
                    trace_id=trace_id,
                    phase=FileEventPhase.CACHE,
                    pct=66.0,
                    status=FileStatus.PROCESSING,
                ),
            )

            # Eager thumbnail generation (non-fatal)
            try:
                from .thumbnail_service import thumbnail_service

                await thumbnail_service.get_or_generate_thumbnail(
                    doc_id=file_id,
                    minio_bucket=minio_bucket,
                    minio_key=minio_key,
                    mimetype=upload.content_type,
                )
                logger.info("Eager thumbnail generated", file_id=file_id)
            except Exception as thumb_err:
                logger.warning(
                    "Eager thumbnail generation failed (non-fatal)",
                    file_id=file_id,
                    error=str(thumb_err),
                )

            document.pages = pages
            document.total_pages = len(pages)
            document.status = DocumentStatus.READY
            await document.save()

            # Invalidate MCP tool caches if document was re-processed
            # This ensures stale analysis results (Excel, audit) are cleared
            try:
                invalidated = await invalidate_document_tool_cache(str(document.id))
                if invalidated > 0:
                    logger.info(
                        "Invalidated MCP tool caches on document update",
                        doc_id=str(document.id),
                        invalidated_count=invalidated,
                    )
            except Exception as cache_err:
                # Non-fatal: cache invalidation failure shouldn't block upload
                logger.warning(
                    "Failed to invalidate MCP tool caches",
                    doc_id=str(document.id),
                    error=str(cache_err),
                )

            await file_event_bus.publish(
                file_id,
                FileEventPayload(
                    file_id=file_id,
                    trace_id=trace_id,
                    phase=FileEventPhase.COMPLETE,
                    pct=100.0,
                    status=FileStatus.READY,
                ),
            )

            # RAG Integration: Process document for vector storage (sync)
            try:
                logger.info(
                    "Starting RAG processing (chunking + embeddings)",
                    file_id=file_id,
                    filename=document.filename,
                )
                processor = create_document_processing_service()
                await processor.process_document_standalone(str(document.id))
                logger.info(
                    "RAG processing completed",
                    file_id=file_id,
                    filename=document.filename,
                )
            except Exception as rag_exc:
                # Don't fail the entire upload if RAG processing fails
                logger.error(
                    "RAG processing failed (non-fatal)",
                    file_id=file_id,
                    error=str(rag_exc),
                    exc_info=True,
                )

            response = FileIngestResponse(
                file_id=str(document.id),
                doc_id=str(document.id),
                status=FileStatus.READY,
                mimetype=document.content_type,
                bytes=document.size_bytes,
                pages=document.total_pages,
                name=document.filename,
                filename=document.filename,
            )
        else:
            # ASYNC PATH: Large files - return PROCESSING immediately, process in background
            logger.info(
                "Large file detected - scheduling background processing",
                file_id=file_id,
                size_bytes=bytes_written,
                threshold_mb=SIZE_THRESHOLD_BYTES / (1024 * 1024),
            )

            # Return immediately with PROCESSING status
            response = FileIngestResponse(
                file_id=str(document.id),
                doc_id=str(document.id),
                status=FileStatus.PROCESSING,
                mimetype=document.content_type,
                bytes=document.size_bytes,
                pages=None,  # Not yet extracted
                name=document.filename,
                filename=document.filename,
            )

            # Schedule background processing
            # Note: BackgroundTasks injection happens in router
            # For now, fire-and-forget with asyncio.create_task
            asyncio.create_task(
                self._process_large_file_async(
                    document=document,
                    file_id=file_id,
                    minio_bucket=minio_bucket,
                    minio_key=minio_key,
                    content_type=upload.content_type,
                    trace_id=trace_id,
                )
            )

            logger.info(
                "Background task scheduled for large file",
                file_id=file_id,
                size_mb=round(bytes_written / (1024 * 1024), 2),
            )

        if effective_key:
            await upload_idempotency_repository.set(user_id, effective_key, response)

        return response

    async def _process_large_file_async(
        self,
        document: Document,
        file_id: str,
        minio_bucket: str,
        minio_key: str,
        content_type: str,
        trace_id: str,
    ) -> None:
        """
        Background processing for large files.

        Runs extraction + caching asynchronously to avoid blocking the upload endpoint.
        """
        try:
            logger.info(
                "Starting async extraction for large file",
                file_id=file_id,
                filename=document.filename,
            )

            # Download from MinIO to temp path
            import tempfile

            with tempfile.NamedTemporaryFile(
                delete=False, suffix=Path(document.filename or "file").suffix
            ) as tmp:
                tmp_extract_path = Path(tmp.name)

            try:
                await minio_service.download_to_path(
                    minio_bucket, minio_key, str(tmp_extract_path)
                )

                # Extract phase
                extract_started = time.time()
                await file_event_bus.publish(
                    file_id,
                    FileEventPayload(
                        file_id=file_id,
                        trace_id=trace_id,
                        phase=FileEventPhase.EXTRACT,
                        pct=33.0,
                        status=FileStatus.PROCESSING,
                    ),
                )

                pages = await extract_text_from_file(tmp_extract_path, content_type)
                record_pdf_ingest_phase("extract", time.time() - extract_started)
            finally:
                tmp_extract_path.unlink(missing_ok=True)

            # Cache phase
            cache_started = time.time()
            await self._cache_pages(file_id, pages)
            record_pdf_ingest_phase("cache", time.time() - cache_started)

            # OBS-1: Record extracted text size
            total_text_size = sum(len(p.text_md) for p in pages)
            record_doc_text_size(content_type, total_text_size)

            logger.info(
                "Large file extraction completed",
                file_id=file_id,
                mimetype=content_type,
                text_size_chars=total_text_size,
                total_pages=len(pages),
            )

            # Eager thumbnail generation (non-fatal, already in background)
            try:
                from .thumbnail_service import thumbnail_service

                await thumbnail_service.get_or_generate_thumbnail(
                    doc_id=file_id,
                    minio_bucket=minio_bucket,
                    minio_key=minio_key,
                    mimetype=content_type,
                )
                logger.info("Eager thumbnail generated (async)", file_id=file_id)
            except Exception as thumb_err:
                logger.warning(
                    "Eager thumbnail generation failed (non-fatal, async)",
                    file_id=file_id,
                    error=str(thumb_err),
                )

            await file_event_bus.publish(
                file_id,
                FileEventPayload(
                    file_id=file_id,
                    trace_id=trace_id,
                    phase=FileEventPhase.CACHE,
                    pct=66.0,
                    status=FileStatus.PROCESSING,
                ),
            )

            # Update document to READY
            document.pages = pages
            document.total_pages = len(pages)
            document.status = DocumentStatus.READY
            await document.save()

            # Invalidate MCP tool caches if document was re-processed
            try:
                invalidated = await invalidate_document_tool_cache(str(document.id))
                if invalidated > 0:
                    logger.info(
                        "Invalidated MCP tool caches on document update",
                        doc_id=str(document.id),
                        invalidated_count=invalidated,
                    )
            except Exception as cache_err:
                logger.warning(
                    "Failed to invalidate MCP tool caches",
                    doc_id=str(document.id),
                    error=str(cache_err),
                )

            await file_event_bus.publish(
                file_id,
                FileEventPayload(
                    file_id=file_id,
                    trace_id=trace_id,
                    phase=FileEventPhase.COMPLETE,
                    pct=100.0,
                    status=FileStatus.READY,
                    mimetype=content_type,
                    pages=len(pages),
                ),
            )

            logger.info(
                "Large file processing completed successfully",
                file_id=file_id,
                filename=document.filename,
            )

            # RAG Integration: Process document for vector storage
            try:
                logger.info(
                    "Starting RAG processing (chunking + embeddings)",
                    file_id=file_id,
                    filename=document.filename,
                )
                processor = create_document_processing_service()
                await processor.process_document_standalone(str(document.id))
                logger.info(
                    "RAG processing completed",
                    file_id=file_id,
                    filename=document.filename,
                )
            except Exception as rag_exc:
                # Don't fail the entire upload if RAG processing fails
                logger.error(
                    "RAG processing failed (non-fatal)",
                    file_id=file_id,
                    error=str(rag_exc),
                    exc_info=True,
                )

        except Exception as exc:
            logger.error(
                "Large file async processing failed",
                file_id=file_id,
                error=str(exc),
                exc_info=True,
            )
            await self._handle_failure(
                document, file_id, trace_id, "EXTRACTION_FAILED", str(exc)
            )

    async def _cache_pages(self, file_id: str, pages: list[PageContent]) -> None:
        redis_cache = await get_redis_cache()
        redis_client = redis_cache.client
        full_text = "\n\n---PAGE BREAK---\n\n".join([p.text_md for p in pages])
        await redis_client.setex(
            f"doc:text:{file_id}",
            3600,
            full_text,
        )

    async def _handle_failure(
        self,
        document: Document,
        file_id: str,
        trace_id: str,
        code: str,
        detail: Optional[str],
    ) -> None:
        increment_pdf_ingest_error(code.lower())
        await document.delete()
        await storage.delete_document(file_id)
        await self._publish_failure(
            file_id, trace_id, FileError(code=code, detail=detail)
        )

    async def _publish_failure(
        self, file_id: str, trace_id: str, error: FileError
    ) -> None:
        await file_event_bus.publish(
            file_id,
            FileEventPayload(
                file_id=file_id,
                trace_id=trace_id,
                phase=FileEventPhase.COMPLETE,
                pct=100.0,
                status=FileStatus.FAILED,
                error=error,
            ),
        )


file_ingest_service = FileIngestService()
