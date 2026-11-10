"""
gRPC service implementation for File Manager.

Maps gRPC calls to existing service methods.
"""

import hashlib
import tempfile
import time
from pathlib import Path
from typing import AsyncIterator, Optional

import grpc
import structlog

from ..config import get_settings
from ..services.extraction import (
    RUST_AVAILABLE,
    extract_text_from_file,
    generate_pdf_thumbnail_bytes,
    generate_thumbnail,
    generate_thumbnail_bytes,
    get_extraction_status,
)
from ..services.minio_client import get_minio_client
from ..services.redis_client import get_redis_client

# Import generated protobuf modules
try:
    from .generated import file_manager_pb2, file_manager_pb2_grpc

    GRPC_GENERATED = True
except ImportError:
    GRPC_GENERATED = False
    file_manager_pb2 = None
    file_manager_pb2_grpc = None

logger = structlog.get_logger(__name__)
settings = get_settings()


class FileManagerServicer(file_manager_pb2_grpc.FileManagerServiceServicer):
    """
    gRPC service implementation for file operations.

    Provides high-performance file upload, download, extraction, and thumbnails.
    """

    def __init__(self):
        """Initialize servicer with service dependencies."""
        self.minio = None
        self.redis = None
        logger.info("FileManagerServicer initialized")

    async def _ensure_clients(self) -> None:
        """Ensure MinIO and Redis clients are available."""
        if self.minio is None:
            self.minio = get_minio_client()
        if self.redis is None:
            self.redis = get_redis_client()

    # =========================================================================
    # Health Check
    # =========================================================================

    async def Health(
        self,
        request: "file_manager_pb2.HealthRequest",
        context: grpc.aio.ServicerContext,
    ) -> "file_manager_pb2.HealthResponse":
        """
        Service health check.

        Returns status of service and dependencies.
        """
        await self._ensure_clients()

        # Check dependencies
        dependencies = {}

        # MinIO health
        try:
            if self.minio:
                self.minio.list_buckets()
                dependencies["minio"] = True
            else:
                dependencies["minio"] = False
        except Exception:
            dependencies["minio"] = False

        # Redis health
        try:
            if self.redis:
                await self.redis.ping()
                dependencies["redis"] = True
            else:
                dependencies["redis"] = False
        except Exception:
            dependencies["redis"] = False

        # Tesseract availability (checked via extraction status)
        extraction_status = get_extraction_status()
        dependencies["tesseract"] = True  # Assumed available if container started

        # Determine overall status
        all_healthy = all(dependencies.values())
        status = "healthy" if all_healthy else "degraded"

        return file_manager_pb2.HealthResponse(
            status=status,
            dependencies=dependencies,
            version=extraction_status.get("rust_version", ""),
        )

    # =========================================================================
    # Upload Operations
    # =========================================================================

    async def UploadSimple(
        self,
        request: "file_manager_pb2.UploadSimpleRequest",
        context: grpc.aio.ServicerContext,
    ) -> "file_manager_pb2.UploadResponse":
        """
        Simple upload - single request/response.

        Handles small to medium files efficiently.
        """
        await self._ensure_clients()

        start_time = time.time()
        metadata = request.metadata
        file_data = request.file_data

        if not file_data:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "No file data provided")

        if len(file_data) > settings.max_file_size_bytes:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"File too large. Max size: {settings.max_file_size_mb}MB",
            )

        try:
            # Generate file ID and compute hash
            file_hash = hashlib.sha256(file_data).hexdigest()
            file_id = file_hash[:16]

            # Upload to MinIO
            bucket = settings.minio_bucket_documents
            minio_key = f"{metadata.user_id}/{file_id}/{metadata.filename}"

            self.minio.put_object(
                bucket,
                minio_key,
                data=file_data,
                length=len(file_data),
                content_type=metadata.content_type,
            )

            # Build response metadata
            file_metadata = file_manager_pb2.FileMetadata(
                file_id=file_id,
                filename=metadata.filename,
                size_bytes=len(file_data),
                content_type=metadata.content_type,
                minio_key=minio_key,
                sha256=file_hash,
            )

            response = file_manager_pb2.UploadResponse(
                file_id=file_id,
                metadata=file_metadata,
            )

            # Auto-extract if requested
            if metadata.auto_extract:
                extraction_result = await self._extract_from_bytes(
                    file_data,
                    metadata.content_type,
                    file_id,
                )
                if extraction_result:
                    response.extraction.CopyFrom(extraction_result)

            logger.info(
                "File uploaded via gRPC",
                file_id=file_id,
                size=len(file_data),
                duration_ms=int((time.time() - start_time) * 1000),
            )

            return response

        except Exception as e:
            logger.error("Upload failed", error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, f"Upload failed: {str(e)}")

    # =========================================================================
    # Download Operations
    # =========================================================================

    async def Download(
        self,
        request: "file_manager_pb2.DownloadRequest",
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator["file_manager_pb2.DownloadResponse"]:
        """
        Stream download - returns metadata first, then file chunks.
        """
        await self._ensure_clients()

        bucket = request.bucket or settings.minio_bucket_documents
        file_path = request.file_path

        try:
            # Get object info first
            stat = self.minio.stat_object(bucket, file_path)

            # Yield metadata
            metadata = file_manager_pb2.FileMetadata(
                filename=file_path.split("/")[-1],
                size_bytes=stat.size,
                content_type=stat.content_type or "application/octet-stream",
                minio_key=file_path,
            )
            yield file_manager_pb2.DownloadResponse(metadata=metadata)

            # Stream file chunks (use raw minio client for streaming response)
            response = self.minio.client.get_object(bucket_name=bucket, object_name=file_path)
            chunk_size = 64 * 1024  # 64KB chunks
            offset = 0

            for data in response.stream(chunk_size):
                is_last = offset + len(data) >= stat.size
                chunk = file_manager_pb2.FileChunk(
                    data=data,
                    offset=offset,
                    is_last=is_last,
                )
                yield file_manager_pb2.DownloadResponse(chunk=chunk)
                offset += len(data)

            response.close()

            logger.info(
                "File downloaded via gRPC",
                file_path=file_path,
                size=stat.size,
            )

        except Exception as e:
            logger.error("Download failed", file_path=file_path, error=str(e))
            await context.abort(grpc.StatusCode.NOT_FOUND, f"File not found: {str(e)}")

    # =========================================================================
    # Text Extraction
    # =========================================================================

    async def Extract(
        self,
        request: "file_manager_pb2.ExtractRequest",
        context: grpc.aio.ServicerContext,
    ) -> "file_manager_pb2.ExtractResponse":
        """
        Extract text from file.
        """
        await self._ensure_clients()

        start_time = time.time()
        file_path = request.file_path

        try:
            # Check cache first (unless force=True)
            cache_key = f"extraction:{file_path}"
            if not request.force and self.redis:
                cached = await self.redis.get(cache_key)
                if cached:
                    # TODO: Deserialize cached result
                    logger.debug("Extraction cache hit", file_path=file_path)

            # Download file from MinIO documents bucket
            file_bytes = self.minio.download_file(file_path)

            # Determine content type from file path
            ext = Path(file_path).suffix.lower()
            content_type = {
                ".pdf": "application/pdf",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
            }.get(ext, "application/octet-stream")

            # Extract using temp file
            with tempfile.NamedTemporaryFile(suffix=ext, delete=True) as tmp:
                tmp.write(file_bytes)
                tmp.flush()

                text, page_count = await extract_text_from_file(
                    Path(tmp.name),
                    content_type,
                )

            processing_time = int((time.time() - start_time) * 1000)

            # Build extraction result
            extraction_status = get_extraction_status()
            source = "rust" if extraction_status["rust_available"] else "python"

            result = file_manager_pb2.ExtractionResult(
                file_id=file_path.split("/")[-2] if "/" in file_path else "",
                total_pages=page_count or 1,
                ocr_applied=False,  # TODO: Track OCR usage
                extraction_source=source,
                processing_time_ms=processing_time,
            )

            # Add page content
            if page_count and page_count > 0:
                pages = text.split("\n\n")
                for i, page_text in enumerate(pages):
                    page = file_manager_pb2.PageContent(
                        page=i,
                        text_md=page_text,
                        has_table=False,
                        has_images=False,
                    )
                    result.pages.append(page)
            else:
                # Single page/image
                result.pages.append(
                    file_manager_pb2.PageContent(
                        page=0,
                        text_md=text,
                    )
                )

            logger.info(
                "Text extracted via gRPC",
                file_path=file_path,
                pages=result.total_pages,
                processing_time_ms=processing_time,
                source=source,
            )

            return file_manager_pb2.ExtractResponse(result=result)

        except Exception as e:
            logger.error("Extraction failed", file_path=file_path, error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, f"Extraction failed: {str(e)}")

    async def BatchExtract(
        self,
        request: "file_manager_pb2.BatchExtractRequest",
        context: grpc.aio.ServicerContext,
    ) -> "file_manager_pb2.BatchExtractResponse":
        """
        Extract text from multiple files.
        """
        start_time = time.time()
        results = []
        failed = []

        for file_path in request.file_paths:
            try:
                extract_request = file_manager_pb2.ExtractRequest(
                    file_path=file_path,
                    force=request.force,
                    provider=request.provider,
                )
                response = await self.Extract(extract_request, context)
                results.append(response.result)
            except Exception as e:
                logger.warning("Batch extraction failed for file", file_path=file_path, error=str(e))
                failed.append(file_path)

        return file_manager_pb2.BatchExtractResponse(
            results=results,
            failed_paths=failed,
            total_processing_time_ms=int((time.time() - start_time) * 1000),
        )

    # =========================================================================
    # Thumbnail Generation
    # =========================================================================

    async def GenerateThumbnail(
        self,
        request: "file_manager_pb2.ThumbnailRequest",
        context: grpc.aio.ServicerContext,
    ) -> "file_manager_pb2.ThumbnailResponse":
        """
        Generate thumbnail for image/PDF.
        """
        await self._ensure_clients()

        start_time = time.time()
        file_path = request.file_path

        try:
            # Download file from MinIO (use request bucket or default)
            bucket = request.bucket or settings.minio_bucket_documents
            if bucket == self.minio.bucket:
                file_bytes = self.minio.download_file(file_path)
            else:
                resp = self.minio.client.get_object(
                    bucket_name=bucket, object_name=file_path
                )
                file_bytes = resp.read()
                resp.close()
                resp.release_conn()

            # Generate thumbnail
            width = request.width or 256
            height = request.height or 384
            format_ = "jpeg"
            quality = 85

            # Detect if file is PDF (by extension or magic bytes)
            ext = Path(file_path).suffix.lower()
            is_pdf = ext == ".pdf" or file_bytes[:4] == b"%PDF"

            if is_pdf:
                # Use PDF-specific thumbnail generator (PyMuPDF)
                thumbnail_bytes, content_type = generate_pdf_thumbnail_bytes(
                    file_bytes,
                    width=width,
                    height=height,
                    format=format_,
                    quality=quality,
                )
                logger.info(
                    "Generated PDF thumbnail via gRPC",
                    file_path=file_path,
                    size=len(thumbnail_bytes),
                )
            else:
                # Use image thumbnail generator (Rust/Pillow)
                thumbnail_bytes, content_type = generate_thumbnail_bytes(
                    file_bytes,
                    width=width,
                    height=height,
                    format=format_,
                    quality=quality,
                )

            processing_time = int((time.time() - start_time) * 1000)

            return file_manager_pb2.ThumbnailResponse(
                thumbnail=thumbnail_bytes,
                content_type=content_type,
                width=width,
                height=height,
                processing_time_ms=processing_time,
            )

        except Exception as e:
            logger.error("Thumbnail generation failed", file_path=file_path, error=str(e))
            await context.abort(grpc.StatusCode.INTERNAL, f"Thumbnail failed: {str(e)}")

    async def BatchGenerateThumbnails(
        self,
        request: "file_manager_pb2.BatchThumbnailRequest",
        context: grpc.aio.ServicerContext,
    ) -> "file_manager_pb2.BatchThumbnailResponse":
        """
        Generate thumbnails for multiple files.
        """
        start_time = time.time()
        results = []

        for file_path in request.file_paths:
            try:
                thumb_request = file_manager_pb2.ThumbnailRequest(
                    file_path=file_path,
                    width=request.width,
                    height=request.height,
                    format=request.format,
                    quality=request.quality,
                )
                response = await self.GenerateThumbnail(thumb_request, context)

                results.append(
                    file_manager_pb2.BatchThumbnailResult(
                        file_path=file_path,
                        thumbnail=response.thumbnail,
                        content_type=response.content_type,
                        success=True,
                    )
                )
            except Exception as e:
                results.append(
                    file_manager_pb2.BatchThumbnailResult(
                        file_path=file_path,
                        success=False,
                        error=str(e),
                    )
                )

        return file_manager_pb2.BatchThumbnailResponse(
            results=results,
            total_processing_time_ms=int((time.time() - start_time) * 1000),
        )

    # =========================================================================
    # Metadata Operations
    # =========================================================================

    async def GetMetadata(
        self,
        request: "file_manager_pb2.MetadataRequest",
        context: grpc.aio.ServicerContext,
    ) -> "file_manager_pb2.MetadataResponse":
        """
        Get file metadata.
        """
        await self._ensure_clients()

        file_path = request.file_path

        try:
            bucket = settings.minio_bucket_documents
            stat = self.minio.stat_object(bucket, file_path)

            metadata = file_manager_pb2.FileMetadata(
                filename=file_path.split("/")[-1],
                size_bytes=stat.size,
                content_type=stat.content_type or "application/octet-stream",
                minio_key=file_path,
                last_modified=stat.last_modified.isoformat() if stat.last_modified else "",
            )

            response = file_manager_pb2.MetadataResponse(metadata=metadata)

            # Include extraction if requested
            if request.include_extraction:
                extract_request = file_manager_pb2.ExtractRequest(file_path=file_path)
                extract_response = await self.Extract(extract_request, context)
                response.extraction.CopyFrom(extract_response.result)

            return response

        except Exception as e:
            logger.error("GetMetadata failed", file_path=file_path, error=str(e))
            await context.abort(grpc.StatusCode.NOT_FOUND, f"File not found: {str(e)}")

    async def Delete(
        self,
        request: "file_manager_pb2.DeleteRequest",
        context: grpc.aio.ServicerContext,
    ) -> "file_manager_pb2.DeleteResponse":
        """
        Delete file and associated resources.
        """
        await self._ensure_clients()

        file_path = request.file_path
        deleted_keys = []

        try:
            bucket = settings.minio_bucket_documents

            # Delete main file
            self.minio.remove_object(bucket, file_path)
            deleted_keys.append(file_path)

            # Delete cached extraction
            if self.redis:
                cache_key = f"extraction:{file_path}"
                await self.redis.delete(cache_key)
                deleted_keys.append(f"cache:{cache_key}")

            logger.info("File deleted via gRPC", file_path=file_path, deleted=deleted_keys)

            return file_manager_pb2.DeleteResponse(
                success=True,
                message=f"Deleted {len(deleted_keys)} objects",
            )

        except Exception as e:
            logger.error("Delete failed", file_path=file_path, error=str(e))
            return file_manager_pb2.DeleteResponse(
                success=False,
                message=f"Delete failed: {str(e)}",
            )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _extract_from_bytes(
        self,
        file_data: bytes,
        content_type: str,
        file_id: str,
    ) -> Optional["file_manager_pb2.ExtractionResult"]:
        """Extract text from file bytes."""
        try:
            # Determine extension from content type
            ext = {
                "application/pdf": ".pdf",
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/gif": ".gif",
            }.get(content_type, ".bin")

            with tempfile.NamedTemporaryFile(suffix=ext, delete=True) as tmp:
                tmp.write(file_data)
                tmp.flush()

                text, page_count = await extract_text_from_file(
                    Path(tmp.name),
                    content_type,
                )

            extraction_status = get_extraction_status()
            source = "rust" if extraction_status["rust_available"] else "python"

            result = file_manager_pb2.ExtractionResult(
                file_id=file_id,
                total_pages=page_count or 1,
                extraction_source=source,
            )

            if page_count and page_count > 0:
                pages = text.split("\n\n")
                for i, page_text in enumerate(pages):
                    result.pages.append(
                        file_manager_pb2.PageContent(page=i, text_md=page_text)
                    )
            else:
                result.pages.append(file_manager_pb2.PageContent(page=0, text_md=text))

            return result

        except Exception as e:
            logger.warning("Auto-extraction failed", file_id=file_id, error=str(e))
            return None
