"""
Unit tests for file_storage module.

Tests:
- FileStorage class initialization
- minio property (lazy initialization)
- delete_file method
- file_exists method
- get_file_storage singleton
"""

from unittest.mock import MagicMock, patch

import pytest

from src.services.file_storage import FileStorage, get_file_storage

pytestmark = [pytest.mark.unit]


class TestFileStorageInit:
    """Test FileStorage initialization."""

    def test_init_without_minio_service(self):
        """Test initialization without MinIO service."""
        storage = FileStorage()
        assert storage._minio is None

    def test_init_with_minio_service(self):
        """Test initialization with MinIO service."""
        mock_minio = MagicMock()
        storage = FileStorage(minio_service=mock_minio)
        assert storage._minio is mock_minio


class TestMinioProperty:
    """Test minio property lazy initialization."""

    def test_returns_none_when_get_minio_returns_none(self):
        """Test returns None when get_minio_storage returns None."""
        storage = FileStorage()

        with patch(
            "src.services.file_storage.get_minio_storage", return_value=None
        ):
            result = storage.minio
            assert result is None

    def test_returns_minio_service_when_available(self):
        """Test returns MinIO service when available."""
        mock_minio = MagicMock()
        storage = FileStorage()

        with patch(
            "src.services.file_storage.get_minio_storage", return_value=mock_minio
        ):
            result = storage.minio
            assert result is mock_minio

    def test_caches_minio_service(self):
        """Test MinIO service is cached after first access."""
        mock_minio = MagicMock()
        storage = FileStorage()

        with patch(
            "src.services.file_storage.get_minio_storage", return_value=mock_minio
        ) as mock_get:
            # First access
            result1 = storage.minio
            # Second access
            result2 = storage.minio

            assert result1 is result2
            # get_minio_storage should only be called once
            mock_get.assert_called_once()

    def test_returns_injected_minio_service(self):
        """Test returns injected MinIO service without calling get_minio_storage."""
        mock_minio = MagicMock()
        storage = FileStorage(minio_service=mock_minio)

        with patch(
            "src.services.file_storage.get_minio_storage"
        ) as mock_get:
            result = storage.minio

            assert result is mock_minio
            mock_get.assert_not_called()


class TestDeleteFile:
    """Test delete_file method."""

    @pytest.mark.asyncio
    async def test_delete_file_success(self):
        """Test successful file deletion."""
        mock_minio = MagicMock()
        mock_minio.delete_document = MagicMock()
        storage = FileStorage(minio_service=mock_minio)

        result = await storage.delete_file("path/to/file.pdf")

        assert result is True
        mock_minio.delete_document.assert_called_once_with("path/to/file.pdf")

    @pytest.mark.asyncio
    async def test_delete_file_returns_false_when_minio_not_available(self):
        """Test returns False when MinIO not available."""
        storage = FileStorage()

        with patch(
            "src.services.file_storage.get_minio_storage", return_value=None
        ):
            result = await storage.delete_file("path/to/file.pdf")

            assert result is False

    @pytest.mark.asyncio
    async def test_delete_file_returns_false_on_error(self):
        """Test returns False on deletion error."""
        mock_minio = MagicMock()
        mock_minio.delete_document = MagicMock(
            side_effect=Exception("Delete failed")
        )
        storage = FileStorage(minio_service=mock_minio)

        result = await storage.delete_file("path/to/file.pdf")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_file_logs_success(self):
        """Test logs success on successful deletion."""
        mock_minio = MagicMock()
        mock_minio.delete_document = MagicMock()
        storage = FileStorage(minio_service=mock_minio)

        with patch("src.services.file_storage.logger") as mock_logger:
            await storage.delete_file("path/to/file.pdf")

            mock_logger.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_file_logs_error_on_failure(self):
        """Test logs error on deletion failure."""
        mock_minio = MagicMock()
        mock_minio.delete_document = MagicMock(
            side_effect=Exception("Delete failed")
        )
        storage = FileStorage(minio_service=mock_minio)

        with patch("src.services.file_storage.logger") as mock_logger:
            await storage.delete_file("path/to/file.pdf")

            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_file_logs_warning_when_minio_unavailable(self):
        """Test logs warning when MinIO unavailable."""
        storage = FileStorage()

        with patch(
            "src.services.file_storage.get_minio_storage", return_value=None
        ), patch("src.services.file_storage.logger") as mock_logger:
            await storage.delete_file("path/to/file.pdf")

            mock_logger.warning.assert_called_once()


class TestFileExists:
    """Test file_exists method."""

    @pytest.mark.asyncio
    async def test_file_exists_returns_true(self):
        """Test returns True when file exists."""
        mock_minio = MagicMock()
        mock_minio.get_object_metadata = MagicMock(return_value={"size": 1024})
        storage = FileStorage(minio_service=mock_minio)

        result = await storage.file_exists("path/to/file.pdf")

        assert result is True
        mock_minio.get_object_metadata.assert_called_once_with("path/to/file.pdf")

    @pytest.mark.asyncio
    async def test_file_exists_returns_false_when_not_found(self):
        """Test returns False when file not found."""
        mock_minio = MagicMock()
        mock_minio.get_object_metadata = MagicMock(
            side_effect=Exception("Not found")
        )
        storage = FileStorage(minio_service=mock_minio)

        result = await storage.file_exists("path/to/file.pdf")

        assert result is False

    @pytest.mark.asyncio
    async def test_file_exists_returns_false_when_minio_unavailable(self):
        """Test returns False when MinIO unavailable."""
        storage = FileStorage()

        with patch(
            "src.services.file_storage.get_minio_storage", return_value=None
        ):
            result = await storage.file_exists("path/to/file.pdf")

            assert result is False


class TestGetFileStorage:
    """Test get_file_storage singleton."""

    def test_returns_file_storage(self):
        """Test returns FileStorage instance."""
        import src.services.file_storage as module

        # Reset singleton
        module._file_storage = None

        storage = get_file_storage()
        assert isinstance(storage, FileStorage)

    def test_returns_same_instance(self):
        """Test returns same singleton instance."""
        import src.services.file_storage as module

        # Reset singleton
        module._file_storage = None

        storage1 = get_file_storage()
        storage2 = get_file_storage()
        assert storage1 is storage2
