"""
MinIO Storage Service - S3-compatible object storage for documents and audit reports.

Bucket Structure:
  - documents/{user_id}/{chat_id}/{file_id}.{ext}
  - audit-reports/{user_id}/{chat_id}/{report_id}.md

Features:
  - Automatic bucket creation and initialization
  - Organized file paths by user and conversation
  - Presigned URL generation for secure access
  - Metadata tagging for searchability
"""

import io
import os
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional, Tuple
from urllib.parse import urlparse

import structlog
from minio import Minio
from minio.error import S3Error
from urllib3.exceptions import MaxRetryError

logger = structlog.get_logger(__name__)


class MinioStorageService:
    """
    Service for interacting with MinIO object storage.

    Implements S3-compatible storage with automatic bucket management
    and organized file paths.
    """

    def __init__(self):
        """Initialize MinIO client from environment variables."""
        self.endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")

        # Support both MINIO_ROOT_USER (standard) and MINIO_ACCESS_KEY (legacy)
        self.access_key = os.getenv("MINIO_ROOT_USER") or os.getenv(
            "MINIO_ACCESS_KEY", "minioadmin"
        )
        self.secret_key = os.getenv("MINIO_ROOT_PASSWORD") or os.getenv(
            "MINIO_SECRET_KEY", "minioadmin123"
        )

        self.use_ssl = os.getenv("MINIO_USE_SSL", "false").lower() == "true"

        # Bucket names & region
        self.bucket_documents = os.getenv("MINIO_BUCKET_DOCUMENTS", "documents")
        self.bucket_reports = os.getenv("MINIO_BUCKET_REPORTS", "audit-reports")
        self.region = os.getenv("MINIO_REGION", "us-east-1")

        self.public_client = None
        self.public_endpoint = None
        self.public_use_ssl = False

        # Initialize client
        try:
            self.client = Minio(
                endpoint=self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.use_ssl,
                region=self.region,
            )

            logger.info(
                "MinIO client initialized",
                endpoint=self.endpoint,
                use_ssl=self.use_ssl,
                buckets=[self.bucket_documents, self.bucket_reports],
            )

            # Ensure buckets exist
            self._ensure_buckets()

            self._initialize_public_client()

        except Exception as e:
            logger.error(
                "Failed to initialize MinIO client",
                error=str(e),
                endpoint=self.endpoint,
            )
            raise

    def _initialize_public_client(self) -> None:
        """
        Optionally initialize a secondary MinIO client used only for generating
        presigned URLs with an externally accessible endpoint.
        """
        # Prefer full endpoint (with scheme) for clarity
        public_endpoint = os.getenv("MINIO_PUBLIC_ENDPOINT")
        external_host = os.getenv("MINIO_EXTERNAL_HOST")

        endpoint_host = None
        secure = False

        if public_endpoint:
            parsed = urlparse(
                public_endpoint
                if "://" in public_endpoint
                else f"http://{public_endpoint}"
            )
            endpoint_host = parsed.netloc
            secure = parsed.scheme == "https"
        elif external_host:
            if "://" in external_host:
                parsed = urlparse(external_host)
                endpoint_host = parsed.netloc
                secure = parsed.scheme == "https"
            else:
                endpoint_host = external_host
                secure = os.getenv("MINIO_EXTERNAL_USE_SSL", "false").lower() == "true"
        elif self.endpoint == "minio:9000" and not self.use_ssl:
            # Local development fallback - match published Docker port
            endpoint_host = os.getenv("MINIO_DEFAULT_PUBLIC_HOST", "localhost:9000")
            secure = (
                os.getenv("MINIO_DEFAULT_PUBLIC_USE_SSL", "false").lower() == "true"
            )

        if endpoint_host:
            try:
                self.public_client = Minio(
                    endpoint=endpoint_host,
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    secure=secure,
                    region=self.region,
                )
                self.public_endpoint = endpoint_host
                self.public_use_ssl = secure
                logger.info(
                    "Initialized MinIO public presign client",
                    endpoint=self.public_endpoint,
                    use_ssl=self.public_use_ssl,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to initialize MinIO public client, falling back to internal endpoint",
                    error=str(exc),
                    endpoint=endpoint_host,
                )
                self.public_client = None

    def _ensure_buckets(self) -> None:
        """Create buckets if they don't exist."""
        for bucket_name in [self.bucket_documents, self.bucket_reports]:
            try:
                # MinIO 7.2.x API: bucket_exists() and make_bucket() require named parameters
                if not self.client.bucket_exists(bucket_name=bucket_name):
                    self.client.make_bucket(bucket_name=bucket_name)
                    logger.info("Created MinIO bucket", bucket=bucket_name)
                else:
                    logger.debug("MinIO bucket exists", bucket=bucket_name)
            except S3Error as e:
                logger.error(
                    "Failed to create bucket", bucket=bucket_name, error=str(e)
                )
                raise

    def upload_document(
        self,
        user_id: str,
        file_id: str,
        file_data: BinaryIO,
        filename: str,
        content_type: str,
        chat_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Upload a document to MinIO.

        Args:
            user_id: Owner user ID
            file_id: Unique file identifier (UUID)
            file_data: File binary data stream
            filename: Original filename
            content_type: MIME type
            chat_id: Optional chat/conversation ID
            metadata: Optional custom metadata tags

        Returns:
            Object path in MinIO
        """
        # Build object path: documents/{user_id}/{chat_id}/{file_id}.{ext}
        file_extension = Path(filename).suffix or ".bin"
        if chat_id:
            object_name = f"{user_id}/{chat_id}/{file_id}{file_extension}"
        else:
            object_name = f"{user_id}/{file_id}{file_extension}"

        # Prepare metadata
        meta = {
            "filename": filename,
            "user_id": user_id,
            "file_id": file_id,
        }
        if chat_id:
            meta["chat_id"] = chat_id
        if metadata:
            meta.update(metadata)

        try:
            # Get file size
            file_data.seek(0, io.SEEK_END)
            file_size = file_data.tell()
            file_data.seek(0)

            # Upload to MinIO
            self.client.put_object(
                bucket_name=self.bucket_documents,
                object_name=object_name,
                data=file_data,
                length=file_size,
                content_type=content_type,
                metadata=meta,
            )

            logger.info(
                "Document uploaded to MinIO",
                object_name=object_name,
                file_size=file_size,
                user_id=user_id,
                file_id=file_id,
            )

            return object_name

        except S3Error as e:
            logger.error(
                "Failed to upload document to MinIO",
                object_name=object_name,
                error=str(e),
                error_code=e.code,
            )
            raise

    def upload_audit_report(
        self,
        user_id: str,
        report_id: str,
        report_content: str,
        chat_id: str,
        document_id: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Upload an audit report (markdown) to MinIO.

        Args:
            user_id: Owner user ID
            report_id: Unique report identifier (UUID)
            report_content: Markdown content of the audit report
            chat_id: Chat/conversation ID
            document_id: ID of audited document
            metadata: Optional custom metadata

        Returns:
            Object path in MinIO
        """
        # Build object path: audit-reports/{user_id}/{chat_id}/{report_id}.md
        object_name = f"{user_id}/{chat_id}/{report_id}.md"

        # Prepare metadata
        meta = {
            "report_id": report_id,
            "user_id": user_id,
            "chat_id": chat_id,
            "document_id": document_id,
            "content_type": "text/markdown",
        }
        if metadata:
            meta.update(metadata)

        try:
            # Convert string to bytes
            report_bytes = report_content.encode("utf-8")
            report_stream = io.BytesIO(report_bytes)

            # Upload to MinIO
            self.client.put_object(
                bucket_name=self.bucket_reports,
                object_name=object_name,
                data=report_stream,
                length=len(report_bytes),
                content_type="text/markdown; charset=utf-8",
                metadata=meta,
            )

            logger.info(
                "Audit report uploaded to MinIO",
                object_name=object_name,
                report_size=len(report_bytes),
                user_id=user_id,
                report_id=report_id,
            )

            return object_name

        except S3Error as e:
            logger.error(
                "Failed to upload audit report to MinIO",
                object_name=object_name,
                error=str(e),
            )
            raise

    def get_document(self, object_name: str, bucket: Optional[str] = None) -> bytes:
        """
        Download a document from MinIO.

        Args:
            object_name: Full object path in MinIO
            bucket: Bucket name (defaults to documents bucket)

        Returns:
            File data as bytes
        """
        bucket_name = bucket or self.bucket_documents

        try:
            response = self.client.get_object(
                bucket_name=bucket_name,
                object_name=object_name,
            )

            data = response.read()
            response.close()
            response.release_conn()

            logger.debug(
                "Document retrieved from MinIO",
                bucket=bucket_name,
                object_name=object_name,
                size=len(data),
            )

            return data

        except S3Error as e:
            logger.error(
                "Failed to retrieve document from MinIO",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e),
            )
            raise

    def materialize_document(
        self,
        object_name: str,
        *,
        filename: Optional[str] = None,
        bucket: Optional[str] = None,
    ) -> Tuple[Path, bool]:
        """
        Ensure the requested document is available on the local filesystem.

        Args:
            object_name: MinIO object path or filesystem path
            filename: Optional original filename (used for temp file suffix)
            bucket: Bucket name (defaults to documents bucket)

        Returns:
            Tuple of (path_to_file, is_temporary)
        """
        candidate_path = Path(object_name)
        if candidate_path.exists():
            return candidate_path, False

        # Support relative paths that might live under the local storage root
        if not candidate_path.is_absolute():
            try:
                from .storage import DEFAULT_STORAGE_CONFIG  # type: ignore
            except Exception:
                DEFAULT_STORAGE_CONFIG = None  # type: ignore
            if DEFAULT_STORAGE_CONFIG:
                storage_path = DEFAULT_STORAGE_CONFIG.root / object_name
                if storage_path.exists():
                    return storage_path, False

        data = self.get_document(object_name, bucket=bucket)

        suffix_source = filename or Path(object_name).name
        suffix = Path(suffix_source).suffix or ".bin"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(data)
            temp_path = Path(temp_file.name)

        return temp_path, True

    def get_audit_report(self, object_name: str) -> str:
        """
        Download an audit report from MinIO.

        Args:
            object_name: Full object path in MinIO

        Returns:
            Report content as string (markdown)
        """
        try:
            response = self.client.get_object(
                bucket_name=self.bucket_reports,
                object_name=object_name,
            )

            data = response.read()
            response.close()
            response.release_conn()

            content = data.decode("utf-8")

            logger.debug(
                "Audit report retrieved from MinIO",
                object_name=object_name,
                size=len(content),
            )

            return content

        except S3Error as e:
            logger.error(
                "Failed to retrieve audit report from MinIO",
                object_name=object_name,
                error=str(e),
            )
            raise

    def delete_document(self, object_name: str) -> None:
        """
        Delete a document from MinIO.

        Args:
            object_name: Full object path in MinIO
        """
        try:
            self.client.remove_object(
                bucket_name=self.bucket_documents,
                object_name=object_name,
            )

            logger.info("Document deleted from MinIO", object_name=object_name)

        except S3Error as e:
            logger.error(
                "Failed to delete document from MinIO",
                object_name=object_name,
                error=str(e),
            )
            raise

    def get_presigned_url(
        self,
        object_name: str,
        bucket: str = "documents",
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """
        Generate a presigned URL for temporary access to an object.

        Args:
            object_name: Full object path in MinIO
            bucket: Bucket name ("documents", "audit-reports", or "artifacts")
            expires: URL expiration time (default: 1 hour)

        Returns:
            Presigned URL string
        """
        try:
            # Map bucket aliases to actual bucket names
            bucket_name_map = {
                "documents": self.bucket_documents,
                "audit-reports": self.bucket_reports,
                "artifacts": "artifacts",  # Generic bucket for PDFs, exports, etc.
            }

            bucket_name = bucket_name_map.get(bucket, bucket)

            client = self.public_client or self.client

            url = client.presigned_get_object(
                bucket_name=bucket_name,
                object_name=object_name,
                expires=expires,
            )

            logger.debug(
                "Generated presigned URL",
                object_name=object_name,
                bucket=bucket_name,
                expires_seconds=expires.total_seconds(),
            )

            return url

        except S3Error as e:
            logger.error(
                "Failed to generate presigned URL",
                object_name=object_name,
                bucket=bucket,
                error=str(e),
            )
            raise

    def get_object_metadata(
        self, object_name: str, bucket: str = "documents"
    ) -> Dict[str, Any]:
        """
        Get metadata for an object.

        Args:
            object_name: Full object path in MinIO
            bucket: Bucket name ("documents" or "audit-reports")

        Returns:
            Object metadata dictionary
        """
        try:
            bucket_name = (
                self.bucket_documents if bucket == "documents" else self.bucket_reports
            )

            stat = self.client.stat_object(
                bucket_name=bucket_name,
                object_name=object_name,
            )

            return {
                "size": stat.size,
                "etag": stat.etag,
                "last_modified": stat.last_modified,
                "content_type": stat.content_type,
                "metadata": stat.metadata,
            }

        except S3Error as e:
            logger.error(
                "Failed to get object metadata", object_name=object_name, error=str(e)
            )
            raise

    async def upload_file(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Generic file upload to any bucket.

        Args:
            bucket_name: Target bucket (e.g., "artifacts", "documents")
            object_name: Full object path in bucket
            data: File binary data stream
            length: Data length in bytes
            content_type: MIME type
            metadata: Optional custom metadata tags
        """
        try:
            # Ensure bucket exists
            # MinIO 7.2.x API: bucket_exists() and make_bucket() require named parameters
            if not self.client.bucket_exists(bucket_name=bucket_name):
                self.client.make_bucket(bucket_name=bucket_name)
                logger.info("Created MinIO bucket", bucket=bucket_name)

            # Upload to MinIO
            self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=data,
                length=length,
                content_type=content_type,
                metadata=metadata or {},
            )

            logger.info(
                "File uploaded to MinIO",
                bucket=bucket_name,
                object_name=object_name,
                size_bytes=length,
                content_type=content_type,
            )

        except S3Error as e:
            logger.error(
                "Failed to upload file to MinIO",
                bucket=bucket_name,
                object_name=object_name,
                error=str(e),
            )
            raise

    def health_check(self) -> bool:
        """
        Check MinIO connection health.

        Returns:
            True if MinIO is accessible, False otherwise
        """
        try:
            # Try to list buckets as a health check
            buckets = self.client.list_buckets()
            return len(buckets) > 0
        except (S3Error, MaxRetryError) as e:
            logger.error("MinIO health check failed", error=str(e))
            return False


# Singleton instance
_minio_storage_service: Optional[MinioStorageService] = None


def get_minio_storage() -> Optional[MinioStorageService]:
    """
    Get or create MinioStorageService singleton instance.

    Returns:
        MinioStorageService instance if MINIO_STORAGE_ENABLED=true, None otherwise
    """
    global _minio_storage_service

    # Check if MinIO is enabled
    minio_enabled = os.getenv("MINIO_STORAGE_ENABLED", "false").lower() == "true"

    if not minio_enabled:
        logger.info("MinIO storage is disabled (MINIO_STORAGE_ENABLED=false)")
        return None

    if _minio_storage_service is None:
        _minio_storage_service = MinioStorageService()

    return _minio_storage_service
