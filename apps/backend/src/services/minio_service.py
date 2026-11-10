"""
MinIO service for document storage and retrieval.
"""

import os
from datetime import timedelta
from typing import BinaryIO, Optional

import structlog
from minio import Minio
from minio.error import S3Error

logger = structlog.get_logger(__name__)


class MinIOService:
    """MinIO client for document storage"""

    def __init__(self, connect: bool = True):
        self.endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.secure = os.getenv("MINIO_SECURE", "false").lower() == "true"

        # Default buckets
        self.documents_bucket = "documents"
        self.artifacts_bucket = "artifacts"
        self.temp_files_bucket = "temp-files"  # 1-day TTL for uploaded files
        self.thumbnails_bucket = "thumbnails"  # 1-day TTL for generated thumbnails

        if connect:
            # MinIO 7.2.x API: Constructor now requires named 'endpoint' parameter
            self.client = Minio(
                endpoint=self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )

            # Ensure buckets exist
            self._ensure_buckets()
        else:
            self.client = None
            logger.info(
                "MinIOService initialized in disconnected mode (likely for testing)"
            )

    def _ensure_buckets(self):
        """Ensure required buckets exist"""
        if not self.client:
            return

        for bucket in [
            self.documents_bucket,
            self.artifacts_bucket,
            self.temp_files_bucket,
            self.thumbnails_bucket,
        ]:
            try:
                # MinIO 7.2.x API: bucket_exists() and make_bucket() require named parameters
                if not self.client.bucket_exists(bucket_name=bucket):
                    self.client.make_bucket(bucket_name=bucket)
                    logger.info(f"Created MinIO bucket: {bucket}")

                    # Configure lifecycle policy for temporary buckets (1 day TTL)
                    if bucket in [self.temp_files_bucket, self.thumbnails_bucket]:
                        self._set_temp_bucket_lifecycle(bucket)
            except S3Error as e:
                logger.error(f"Error ensuring bucket {bucket}", error=str(e))

    def _set_temp_bucket_lifecycle(self, bucket: str):
        """Set 1-hour lifecycle policy for temporary files bucket"""
        if not self.client:
            return

        try:
            from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule

            # Lifecycle rule: Delete objects after 1 hour
            config = LifecycleConfig(
                [
                    Rule(
                        rule_id="temp-files-1h-expiry",
                        status="Enabled",
                        expiration=Expiration(days=1),  # MinIO minimum is 1 day
                    )
                ]
            )

            self.client.set_bucket_lifecycle(bucket, config)
            logger.info(f"Set lifecycle policy for {bucket}: 1 day expiration")
        except Exception as e:
            # Lifecycle policies are optional, log warning but don't fail
            logger.warning(f"Could not set lifecycle policy for {bucket}", error=str(e))

    async def upload_file(
        self,
        bucket: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload file to MinIO.

        Args:
            bucket: Bucket name
            object_name: Object key
            data: File data stream
            length: Data length in bytes
            content_type: MIME type

        Returns:
            Object key
        """
        if not self.client:
            raise RuntimeError("MinIOService not connected")

        try:
            self.client.put_object(
                bucket_name=bucket,
                object_name=object_name,
                data=data,
                length=length,
                content_type=content_type,
            )
            logger.info(
                "Uploaded to MinIO", bucket=bucket, key=object_name, size=length
            )
            return object_name
        except S3Error as e:
            logger.error(
                "MinIO upload failed", error=str(e), bucket=bucket, key=object_name
            )
            raise

    async def download_file(self, bucket: str, object_name: str) -> bytes:
        """
        Download file from MinIO.

        Args:
            bucket: Bucket name
            object_name: Object key

        Returns:
            File bytes
        """
        if not self.client:
            raise RuntimeError("MinIOService not connected")

        try:
            response = self.client.get_object(
                bucket_name=bucket, object_name=object_name
            )
            data = response.read()
            response.close()
            response.release_conn()
            logger.info("Downloaded from MinIO", bucket=bucket, key=object_name)
            return data
        except S3Error as e:
            logger.error(
                "MinIO download failed", error=str(e), bucket=bucket, key=object_name
            )
            raise

    async def download_to_path(
        self, bucket: str, object_name: str, file_path: str
    ) -> None:
        """
        Download file from MinIO to local path.

        Args:
            bucket: Bucket name
            object_name: Object key
            file_path: Destination file path
        """
        if not self.client:
            raise RuntimeError("MinIOService not connected")

        try:
            self.client.fget_object(
                bucket_name=bucket, object_name=object_name, file_path=file_path
            )
            logger.info(
                "Downloaded from MinIO to path",
                bucket=bucket,
                key=object_name,
                path=file_path,
            )
        except S3Error as e:
            logger.error(
                "MinIO download to path failed",
                error=str(e),
                bucket=bucket,
                key=object_name,
            )
            raise

    def materialize_document(
        self, object_name: str, filename: Optional[str] = None
    ) -> tuple[str, bool]:
        """
        Download document to a temporary file path.

        Args:
            object_name: MinIO object key
            filename: Original filename (optional)

        Returns:
            Tuple of (file_path, is_temp)
            - file_path: Path to the materialized file
            - is_temp: True if file should be deleted after use
        """
        if not self.client:
            raise RuntimeError("MinIOService not connected")

        import tempfile
        from pathlib import Path

        suffix = Path(filename).suffix if filename else ""
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_path = tmp_file.name

        try:
            # Try downloading from temp-files bucket first (most common for new uploads)
            try:
                self.client.fget_object(
                    bucket_name=self.temp_files_bucket,
                    object_name=object_name,
                    file_path=tmp_path,
                )
                logger.info(
                    f"Materialized document from {self.temp_files_bucket}",
                    key=object_name,
                    path=tmp_path,
                )
                return Path(tmp_path), True
            except S3Error:
                # Fallback to documents bucket
                self.client.fget_object(
                    bucket_name=self.documents_bucket,
                    object_name=object_name,
                    file_path=tmp_path,
                )
                logger.info(
                    f"Materialized document from {self.documents_bucket}",
                    key=object_name,
                    path=tmp_path,
                )
                return Path(tmp_path), True

        except Exception as e:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            logger.error(
                "Failed to materialize document", error=str(e), key=object_name
            )
            raise

    def get_presigned_url(
        self,
        bucket: str,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """
        Get presigned URL for object.

        Args:
            bucket: Bucket name
            object_name: Object key
            expires: Expiration time

        Returns:
            Presigned URL
        """
        if not self.client:
            raise RuntimeError("MinIOService not connected")

        try:
            url = self.client.presigned_get_object(
                bucket_name=bucket, object_name=object_name, expires=expires
            )
            logger.info("Generated presigned URL", bucket=bucket, key=object_name)
            return url
        except S3Error as e:
            logger.error("Failed to generate presigned URL", error=str(e))
            raise

    async def delete_file(self, bucket: str, object_name: str) -> None:
        """
        Delete file from MinIO.

        Args:
            bucket: Bucket name
            object_name: Object key
        """
        if not self.client:
            raise RuntimeError("MinIOService not connected")

        try:
            self.client.remove_object(bucket_name=bucket, object_name=object_name)
            logger.info("Deleted from MinIO", bucket=bucket, key=object_name)
        except S3Error as e:
            logger.error(
                "MinIO delete failed", error=str(e), bucket=bucket, key=object_name
            )
            raise

    def object_exists(self, bucket: str, object_name: str) -> bool:
        """Check if object exists"""
        if not self.client:
            return False

        try:
            self.client.stat_object(bucket_name=bucket, object_name=object_name)
            return True
        except S3Error:
            return False


# Singleton instance
# Check for TEST_MODE environment variable to skip connection during tests
is_test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
minio_service = MinIOService(connect=not is_test_mode)
