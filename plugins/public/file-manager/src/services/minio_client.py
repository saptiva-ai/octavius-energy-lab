"""
MinIO client service for S3-compatible object storage.
"""

from typing import Optional, BinaryIO
from datetime import timedelta
import io

import structlog
from minio import Minio
from minio.error import S3Error

from ..config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# Global client instance
_client: Optional["MinioClient"] = None


class MinioClient:
    """MinIO client wrapper with bucket management."""

    def __init__(self):
        self.endpoint = settings.minio_endpoint
        self.access_key = settings.minio_access_key
        self.secret_key = settings.minio_secret_key
        self.use_ssl = settings.minio_use_ssl
        self.bucket = settings.minio_bucket_documents
        self.region = settings.minio_region

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
            bucket=self.bucket,
        )

    def ensure_bucket(self) -> None:
        """Ensure the documents bucket exists."""
        try:
            # MinIO 7.2.x API: bucket_exists() is now a method with bucket parameter
            found = self.client.bucket_exists(bucket_name=self.bucket)
            if not found:
                self.client.make_bucket(bucket_name=self.bucket, location=self.region)
                logger.info("Created bucket", bucket=self.bucket)
            else:
                logger.debug("Bucket exists", bucket=self.bucket)
        except S3Error as e:
            logger.error("Failed to ensure bucket", error=str(e))
            raise

    def upload_file(
        self,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Upload a file to MinIO.

        Args:
            object_name: Path in bucket (e.g., "user_id/session_id/file_id.pdf")
            data: File-like object to upload
            length: Size in bytes
            content_type: MIME type
            metadata: Optional metadata tags

        Returns:
            Object name (key) in bucket
        """
        try:
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=data,
                length=length,
                content_type=content_type,
                user_metadata=metadata or {},
            )

            logger.info(
                "File uploaded to MinIO",
                bucket=self.bucket,
                object_name=object_name,
                size=length,
            )

            return object_name

        except S3Error as e:
            logger.error(
                "Failed to upload file",
                object_name=object_name,
                error=str(e),
            )
            raise

    def download_file(self, object_name: str) -> bytes:
        """
        Download a file from MinIO.

        Args:
            object_name: Path in bucket

        Returns:
            File contents as bytes
        """
        try:
            response = self.client.get_object(bucket_name=self.bucket, object_name=object_name)
            data = response.read()
            response.close()
            response.release_conn()

            logger.debug(
                "File downloaded from MinIO",
                object_name=object_name,
                size=len(data),
            )

            return data

        except S3Error as e:
            logger.error(
                "Failed to download file",
                object_name=object_name,
                error=str(e),
            )
            raise

    def get_presigned_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """
        Generate a presigned URL for direct download.

        Args:
            object_name: Path in bucket
            expires: URL expiration time

        Returns:
            Presigned URL string
        """
        try:
            url = self.client.presigned_get_object(
                bucket_name=self.bucket,
                object_name=object_name,
                expires=expires,
            )
            return url

        except S3Error as e:
            logger.error(
                "Failed to generate presigned URL",
                object_name=object_name,
                error=str(e),
            )
            raise

    def delete_file(self, object_name: str) -> None:
        """Delete a file from MinIO."""
        try:
            self.client.remove_object(bucket_name=self.bucket, object_name=object_name)
            logger.info("File deleted from MinIO", object_name=object_name)

        except S3Error as e:
            logger.error(
                "Failed to delete file",
                object_name=object_name,
                error=str(e),
            )
            raise

    def file_exists(self, object_name: str) -> bool:
        """Check if a file exists in MinIO."""
        try:
            self.client.stat_object(bucket_name=self.bucket, object_name=object_name)
            return True
        except S3Error:
            return False

    def get_file_info(self, object_name: str) -> dict:
        """Get file metadata from MinIO."""
        try:
            stat = self.client.stat_object(bucket_name=self.bucket, object_name=object_name)
            return {
                "size": stat.size,
                "content_type": stat.content_type,
                "etag": stat.etag,
                "last_modified": stat.last_modified.isoformat() if stat.last_modified else None,
                "metadata": dict(stat.metadata) if stat.metadata else {},
            }
        except S3Error as e:
            logger.error(
                "Failed to get file info",
                object_name=object_name,
                error=str(e),
            )
            raise


async def init_minio_client() -> None:
    """Initialize the global MinIO client."""
    global _client
    _client = MinioClient()
    _client.ensure_bucket()


async def close_minio_client() -> None:
    """Close the MinIO client (no-op for sync client)."""
    global _client
    _client = None


def get_minio_client() -> MinioClient:
    """Get the global MinIO client instance."""
    if _client is None:
        raise RuntimeError("MinIO client not initialized. Call init_minio_client() first.")
    return _client
