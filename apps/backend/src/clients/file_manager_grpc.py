"""
gRPC client for the file-manager plugin.

Provides high-performance file operations via gRPC (HTTP/2).
Falls back to HTTP client if gRPC is unavailable.

Usage:
    client = await get_file_manager_grpc_client()
    result = await client.extract(file_path)
    thumbnail = await client.generate_thumbnail(file_path)
"""

import os
import time
from dataclasses import dataclass
from typing import AsyncIterator, List, Optional, Tuple

import grpc
import structlog

logger = structlog.get_logger(__name__)

# Try to import generated proto modules
try:
    # These would be copied from the file-manager plugin or generated locally
    from ..proto_stubs.generated import file_manager_pb2, file_manager_pb2_grpc

    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    file_manager_pb2 = None
    file_manager_pb2_grpc = None
    logger.warning(
        "gRPC modules not available, falling back to HTTP",
        hint="Copy proto generated files from plugins/public/file-manager/src/grpc/generated/",
    )


@dataclass
class ExtractionResult:
    """Result of text extraction."""

    file_id: str
    pages: List["PageContent"]
    total_pages: int
    ocr_applied: bool
    source: str
    processing_time_ms: int
    rust_version: Optional[str] = None


@dataclass
class PageContent:
    """Content from a single page."""

    page: int
    text: str
    has_table: bool = False
    has_images: bool = False
    quality_ratio: float = 0.0
    ocr_applied: bool = False


@dataclass
class ThumbnailResult:
    """Result of thumbnail generation."""

    data: bytes
    content_type: str
    width: int
    height: int
    original_width: int = 0
    original_height: int = 0
    processing_time_ms: int = 0


@dataclass
class FileMetadata:
    """File metadata from gRPC."""

    file_id: str
    filename: str
    size: int
    content_type: str
    minio_key: str
    sha256: str = ""
    last_modified: str = ""


class FileManagerGrpcClient:
    """
    gRPC client for the file-manager plugin.

    Provides high-performance file operations via gRPC.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        max_message_size: int = 100 * 1024 * 1024,  # 100MB
    ):
        """
        Initialize the gRPC client.

        Args:
            host: gRPC server host. Defaults to FILE_MANAGER_GRPC_HOST or "file-manager"
            port: gRPC server port. Defaults to FILE_MANAGER_GRPC_PORT or 50052
            max_message_size: Maximum message size in bytes
        """
        self.host = host or os.getenv("FILE_MANAGER_GRPC_HOST", "file-manager")
        self.port = port or int(os.getenv("FILE_MANAGER_GRPC_PORT", "50052"))
        self.max_message_size = max_message_size

        self._channel: Optional[grpc.aio.Channel] = None
        self._stub = None

        logger.info(
            "FileManagerGrpcClient initialized",
            host=self.host,
            port=self.port,
            grpc_available=GRPC_AVAILABLE,
        )

    async def _get_channel(self) -> grpc.aio.Channel:
        """Get or create the gRPC channel."""
        if self._channel is None:
            target = f"{self.host}:{self.port}"
            self._channel = grpc.aio.insecure_channel(
                target,
                options=[
                    ("grpc.max_send_message_length", self.max_message_size),
                    ("grpc.max_receive_message_length", self.max_message_size),
                    ("grpc.keepalive_time_ms", 30000),
                    ("grpc.keepalive_timeout_ms", 10000),
                ],
            )
            logger.debug("gRPC channel created", target=target)
        return self._channel

    async def _get_stub(self) -> "file_manager_pb2_grpc.FileManagerServiceStub":
        """Get the gRPC stub."""
        if not GRPC_AVAILABLE:
            raise RuntimeError("gRPC modules not available")

        if self._stub is None:
            channel = await self._get_channel()
            self._stub = file_manager_pb2_grpc.FileManagerServiceStub(channel)
        return self._stub

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self) -> dict:
        """
        Check file-manager health status via gRPC.

        Returns:
            Dict with status, dependencies, rust info
        """
        stub = await self._get_stub()

        request = file_manager_pb2.HealthRequest()
        response = await stub.Health(request)

        return {
            "status": response.status,
            "dependencies": dict(response.dependencies),
            "rust_available": response.rust_available,
            "rust_module_version": response.rust_module_version,
            "capabilities": dict(response.capabilities),
        }

    # =========================================================================
    # Upload Operations
    # =========================================================================

    async def upload(
        self,
        file_data: bytes,
        user_id: str,
        filename: str,
        content_type: str = "application/octet-stream",
        session_id: Optional[str] = None,
        auto_extract: bool = True,
    ) -> Tuple[FileMetadata, Optional[ExtractionResult]]:
        """
        Upload a file via gRPC.

        Args:
            file_data: File bytes
            user_id: Owner user ID
            filename: Original filename
            content_type: MIME type
            session_id: Optional chat session ID
            auto_extract: Automatically extract text

        Returns:
            Tuple of (FileMetadata, ExtractionResult or None)
        """
        stub = await self._get_stub()

        metadata = file_manager_pb2.UploadRequest(
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            session_id=session_id or "",
            auto_extract=auto_extract,
        )

        request = file_manager_pb2.UploadSimpleRequest(
            metadata=metadata,
            file_data=file_data,
        )

        logger.info(
            "Uploading file via gRPC",
            filename=filename,
            user_id=user_id,
            size=len(file_data),
        )

        response = await stub.UploadSimple(request)

        file_meta = FileMetadata(
            file_id=response.file_id,
            filename=response.metadata.filename,
            size=response.metadata.size,
            content_type=response.metadata.content_type,
            minio_key=response.metadata.minio_key,
            sha256=response.metadata.sha256,
        )

        extraction = None
        if response.HasField("extraction"):
            extraction = self._convert_extraction_result(response.extraction)

        logger.info(
            "File uploaded via gRPC",
            file_id=file_meta.file_id,
            minio_key=file_meta.minio_key,
            has_extraction=extraction is not None,
        )

        return file_meta, extraction

    # =========================================================================
    # Download Operations
    # =========================================================================

    async def download(self, file_path: str, bucket: Optional[str] = None) -> bytes:
        """
        Download a file via gRPC streaming.

        Args:
            file_path: MinIO object path
            bucket: Optional bucket name

        Returns:
            File content as bytes
        """
        stub = await self._get_stub()

        request = file_manager_pb2.DownloadRequest(
            file_path=file_path,
            bucket=bucket or "",
        )

        chunks = []
        async for response in stub.Download(request):
            if response.HasField("chunk"):
                chunks.append(response.chunk.data)

        content = b"".join(chunks)
        logger.debug("File downloaded via gRPC", file_path=file_path, size=len(content))
        return content

    async def download_stream(
        self, file_path: str, bucket: Optional[str] = None
    ) -> AsyncIterator[bytes]:
        """
        Download a file as async stream.

        Args:
            file_path: MinIO object path
            bucket: Optional bucket name

        Yields:
            File chunks
        """
        stub = await self._get_stub()

        request = file_manager_pb2.DownloadRequest(
            file_path=file_path,
            bucket=bucket or "",
        )

        async for response in stub.Download(request):
            if response.HasField("chunk"):
                yield response.chunk.data

    # =========================================================================
    # Text Extraction
    # =========================================================================

    async def extract(
        self,
        file_path: str,
        force: bool = False,
        provider: str = "auto",
    ) -> ExtractionResult:
        """
        Extract text from a file via gRPC.

        Args:
            file_path: MinIO object path
            force: Force re-extraction even if cached
            provider: "rust", "python", or "auto"

        Returns:
            ExtractionResult with pages and metadata
        """
        stub = await self._get_stub()
        start_time = time.time()

        request = file_manager_pb2.ExtractRequest(
            file_path=file_path,
            force=force,
            provider=provider,
        )

        response = await stub.Extract(request)

        result = self._convert_extraction_result(response.result)

        logger.info(
            "Text extracted via gRPC",
            file_path=file_path,
            pages=result.total_pages,
            processing_time_ms=result.processing_time_ms,
            source=result.source,
        )

        return result

    async def batch_extract(
        self,
        file_paths: List[str],
        force: bool = False,
        provider: str = "auto",
    ) -> Tuple[List[ExtractionResult], List[str]]:
        """
        Extract text from multiple files via gRPC.

        Args:
            file_paths: List of MinIO object paths
            force: Force re-extraction
            provider: Extraction provider

        Returns:
            Tuple of (successful results, failed paths)
        """
        stub = await self._get_stub()

        request = file_manager_pb2.BatchExtractRequest(
            file_paths=file_paths,
            force=force,
            provider=provider,
        )

        response = await stub.BatchExtract(request)

        results = [self._convert_extraction_result(r) for r in response.results]
        failed = list(response.failed_paths)

        logger.info(
            "Batch extraction via gRPC",
            total=len(file_paths),
            success=len(results),
            failed=len(failed),
            total_time_ms=response.total_processing_time_ms,
        )

        return results, failed

    # =========================================================================
    # Thumbnail Generation
    # =========================================================================

    async def generate_thumbnail(
        self,
        file_path: str,
        width: int = 200,
        height: int = 200,
        bucket: str = "",
    ) -> ThumbnailResult:
        """
        Generate thumbnail for a file via gRPC.

        Args:
            file_path: MinIO object path
            width: Target width
            height: Target height
            bucket: MinIO bucket (empty = file-manager default)

        Returns:
            ThumbnailResult with image data
        """
        stub = await self._get_stub()

        request = file_manager_pb2.ThumbnailRequest(
            file_path=file_path,
            width=width,
            height=height,
            bucket=bucket,
        )

        response = await stub.GenerateThumbnail(request)

        result = ThumbnailResult(
            data=response.thumbnail,
            content_type=response.content_type,
            width=response.width,
            height=response.height,
            original_width=response.original_width,
            original_height=response.original_height,
            processing_time_ms=response.processing_time_ms,
        )

        logger.debug(
            "Thumbnail generated via gRPC",
            file_path=file_path,
            size=len(result.data),
            dimensions=f"{result.width}x{result.height}",
        )

        return result

    # =========================================================================
    # Metadata Operations
    # =========================================================================

    async def get_metadata(
        self, file_path: str, include_text: bool = False
    ) -> Tuple[FileMetadata, Optional[ExtractionResult]]:
        """
        Get file metadata via gRPC.

        Args:
            file_path: MinIO object path
            include_text: Include extracted text

        Returns:
            Tuple of (FileMetadata, ExtractionResult or None)
        """
        stub = await self._get_stub()

        request = file_manager_pb2.MetadataRequest(
            file_path=file_path,
            include_text=include_text,
        )

        response = await stub.GetMetadata(request)

        metadata = FileMetadata(
            file_id=response.metadata.file_id,
            filename=response.metadata.filename,
            size=response.metadata.size,
            content_type=response.metadata.content_type,
            minio_key=response.metadata.minio_key,
            sha256=response.metadata.sha256,
            last_modified=response.metadata.last_modified,
        )

        extraction = None
        if response.HasField("extraction"):
            extraction = self._convert_extraction_result(response.extraction)

        return metadata, extraction

    async def delete(
        self,
        file_path: str,
        delete_thumbnails: bool = True,
        delete_extraction: bool = True,
    ) -> bool:
        """
        Delete a file via gRPC.

        Args:
            file_path: MinIO object path
            delete_thumbnails: Also delete thumbnails
            delete_extraction: Also delete cached extraction

        Returns:
            True if successful
        """
        stub = await self._get_stub()

        request = file_manager_pb2.DeleteRequest(
            file_path=file_path,
            delete_thumbnails=delete_thumbnails,
            delete_extraction=delete_extraction,
        )

        response = await stub.Delete(request)

        logger.info(
            "File deleted via gRPC",
            file_path=file_path,
            success=response.success,
            deleted=list(response.deleted_keys),
        )

        return response.success

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _convert_extraction_result(
        self, proto_result: "file_manager_pb2.ExtractionResult"
    ) -> ExtractionResult:
        """Convert protobuf ExtractionResult to dataclass."""
        pages = []
        for p in proto_result.pages:
            pages.append(
                PageContent(
                    page=p.page,
                    text=p.text_md,
                    has_table=p.has_table,
                    has_images=p.has_images,
                    quality_ratio=p.quality_ratio,
                    ocr_applied=p.ocr_applied,
                )
            )

        return ExtractionResult(
            file_id=proto_result.file_id,
            pages=pages,
            total_pages=proto_result.total_pages,
            ocr_applied=proto_result.ocr_applied,
            source=proto_result.source,
            processing_time_ms=proto_result.processing_time_ms,
            rust_version=proto_result.rust_version or None,
        )

    async def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
            logger.debug("gRPC channel closed")


# =============================================================================
# Singleton and Factory
# =============================================================================

_grpc_client: Optional[FileManagerGrpcClient] = None


async def get_file_manager_grpc_client() -> FileManagerGrpcClient:
    """
    Get the global FileManagerGrpcClient instance.

    Returns:
        FileManagerGrpcClient instance

    Raises:
        RuntimeError: If gRPC is not available
    """
    global _grpc_client

    if not GRPC_AVAILABLE:
        raise RuntimeError(
            "gRPC modules not available. Install grpcio and copy proto generated files."
        )

    if _grpc_client is None:
        _grpc_client = FileManagerGrpcClient()

    return _grpc_client


async def close_file_manager_grpc_client() -> None:
    """Close the global gRPC client."""
    global _grpc_client

    if _grpc_client:
        await _grpc_client.close()
        _grpc_client = None


def is_grpc_available() -> bool:
    """Check if gRPC client is available."""
    return GRPC_AVAILABLE
