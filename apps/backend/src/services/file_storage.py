"""
File Storage Service - Abstraction layer for file storage operations.

This module provides a unified interface for file storage operations,
delegating to the underlying MinIO storage service.

Used by ResourceLifecycleManager for cleanup operations.
"""

from typing import Optional

import structlog

from .minio_storage import MinioStorageService, get_minio_storage

logger = structlog.get_logger(__name__)


class FileStorage:
    """
    File storage abstraction layer.

    Wraps MinIO storage to provide a simple interface for file operations.
    """

    def __init__(self, minio_service: Optional[MinioStorageService] = None):
        """
        Initialize file storage.

        Args:
            minio_service: Optional MinIO service instance (for testing)
        """
        self._minio = minio_service

    @property
    def minio(self) -> Optional[MinioStorageService]:
        """Get MinIO service, initializing lazily if needed."""
        if self._minio is None:
            self._minio = get_minio_storage()
        return self._minio

    async def delete_file(self, file_path: str) -> bool:
        """
        Delete a file from storage.

        Args:
            file_path: Path to the file in storage (MinIO object name)

        Returns:
            True if deleted successfully, False otherwise
        """
        if not self.minio:
            logger.warning(
                "MinIO storage not available, cannot delete file",
                file_path=file_path,
            )
            return False

        try:
            self.minio.delete_document(file_path)
            logger.info("File deleted from storage", file_path=file_path)
            return True
        except Exception as e:
            logger.error(
                "Failed to delete file from storage",
                file_path=file_path,
                error=str(e),
            )
            return False

    async def file_exists(self, file_path: str) -> bool:
        """
        Check if a file exists in storage.

        Args:
            file_path: Path to the file in storage

        Returns:
            True if file exists, False otherwise
        """
        if not self.minio:
            return False

        try:
            self.minio.get_object_metadata(file_path)
            return True
        except Exception:
            return False


# Singleton instance
_file_storage: Optional[FileStorage] = None


def get_file_storage() -> FileStorage:
    """
    Get or create FileStorage singleton instance.

    Returns:
        FileStorage instance
    """
    global _file_storage

    if _file_storage is None:
        _file_storage = FileStorage()

    return _file_storage
