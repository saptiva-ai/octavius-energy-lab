"""
Unit tests for gRPC servicer.

Tests the FileManagerServicer with mocked dependencies.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
from pathlib import Path


# ============================================================================
# Servicer Import Tests
# ============================================================================


@pytest.mark.grpc
class TestServicerImport:
    """Test servicer module imports."""

    def test_servicer_imports(self):
        """Test servicer can be imported."""
        try:
            from src.grpc.servicer import FileManagerServicer

            assert FileManagerServicer is not None
        except ImportError as e:
            if "generated" in str(e):
                pytest.skip("gRPC generated modules not available")
            raise

    def test_server_imports(self):
        """Test server can be imported."""
        try:
            from src.grpc.server import create_grpc_server, start_grpc_server

            assert create_grpc_server is not None
            assert start_grpc_server is not None
        except ImportError as e:
            if "generated" in str(e):
                pytest.skip("gRPC generated modules not available")
            raise


# ============================================================================
# Health Check Tests
# ============================================================================


@pytest.mark.grpc
@pytest.mark.asyncio
class TestServicerHealth:
    """Test servicer health check."""

    @pytest.fixture
    def servicer(self, mock_minio_client, mock_redis_client):
        """Create servicer with mocked clients."""
        try:
            from src.grpc.servicer import FileManagerServicer
        except ImportError:
            pytest.skip("gRPC modules not available")

        servicer = FileManagerServicer()
        servicer.minio = mock_minio_client
        servicer.redis = mock_redis_client
        return servicer

    async def test_health_check_healthy(self, servicer):
        """Test health check returns healthy."""
        context = AsyncMock()

        try:
            from src.grpc.generated import file_manager_pb2
        except ImportError:
            pytest.skip("gRPC generated modules not available")

        request = file_manager_pb2.HealthRequest()

        response = await servicer.Health(request, context)

        assert response.status == "healthy"
        assert response.dependencies["minio"] is True
        assert response.dependencies["redis"] is True

    async def test_health_check_degraded(self, servicer):
        """Test health check returns degraded when service down."""
        context = AsyncMock()

        # Make minio fail
        servicer.minio.list_buckets.side_effect = Exception("Connection failed")

        try:
            from src.grpc.generated import file_manager_pb2
        except ImportError:
            pytest.skip("gRPC generated modules not available")

        request = file_manager_pb2.HealthRequest()

        response = await servicer.Health(request, context)

        assert response.status == "degraded"
        assert response.dependencies["minio"] is False


# ============================================================================
# Upload Tests
# ============================================================================


@pytest.mark.grpc
@pytest.mark.asyncio
class TestServicerUpload:
    """Test servicer upload operations."""

    @pytest.fixture
    def servicer(self, mock_minio_client, mock_redis_client):
        """Create servicer with mocked clients."""
        try:
            from src.grpc.servicer import FileManagerServicer
        except ImportError:
            pytest.skip("gRPC modules not available")

        servicer = FileManagerServicer()
        servicer.minio = mock_minio_client
        servicer.redis = mock_redis_client
        return servicer

    async def test_upload_simple_success(self, servicer, sample_pdf_bytes):
        """Test simple upload success."""
        context = AsyncMock()

        try:
            from src.grpc.generated import file_manager_pb2
        except ImportError:
            pytest.skip("gRPC generated modules not available")

        metadata = file_manager_pb2.UploadMetadata(
            user_id="user123",
            filename="test.pdf",
            content_type="application/pdf",
            auto_extract=False,
        )

        request = file_manager_pb2.UploadSimpleRequest(
            metadata=metadata,
            file_data=sample_pdf_bytes,
        )

        response = await servicer.UploadSimple(request, context)

        assert response.file_id is not None
        assert response.metadata.filename == "test.pdf"
        assert response.metadata.size_bytes == len(sample_pdf_bytes)
        assert "user123" in response.metadata.minio_key

    async def test_upload_empty_data_fails(self, servicer):
        """Test upload fails with empty data."""
        context = AsyncMock()

        try:
            from src.grpc.generated import file_manager_pb2
        except ImportError:
            pytest.skip("gRPC generated modules not available")

        metadata = file_manager_pb2.UploadMetadata(
            user_id="user123",
            filename="test.pdf",
            content_type="application/pdf",
        )

        request = file_manager_pb2.UploadSimpleRequest(
            metadata=metadata,
            file_data=b"",
        )

        # Should abort with INVALID_ARGUMENT
        await servicer.UploadSimple(request, context)
        context.abort.assert_called()


# ============================================================================
# Extract Tests
# ============================================================================


@pytest.mark.grpc
@pytest.mark.asyncio
class TestServicerExtract:
    """Test servicer extraction operations."""

    @pytest.fixture
    def servicer(self, mock_minio_client, mock_redis_client, sample_pdf_bytes):
        """Create servicer with mocked clients."""
        try:
            from src.grpc.servicer import FileManagerServicer
        except ImportError:
            pytest.skip("gRPC modules not available")

        # Configure minio to return sample PDF
        mock_response = MagicMock()
        mock_response.read.return_value = sample_pdf_bytes
        mock_response.close = MagicMock()
        mock_minio_client.get_object.return_value = mock_response
        mock_minio_client.download_file.return_value = sample_pdf_bytes

        servicer = FileManagerServicer()
        servicer.minio = mock_minio_client
        servicer.redis = mock_redis_client
        return servicer

    async def test_extract_success(self, servicer):
        """Test text extraction success."""
        context = AsyncMock()

        try:
            from src.grpc.generated import file_manager_pb2
        except ImportError:
            pytest.skip("gRPC generated modules not available")

        request = file_manager_pb2.ExtractRequest(
            file_path="user123/doc123/test.pdf",
            force=False,
        )

        response = await servicer.Extract(request, context)

        assert response is not None
        assert response.result.total_pages >= 1
        assert response.result.extraction_source in ("rust", "python")

    async def test_extract_with_force(self, servicer):
        """Test extraction with force flag."""
        context = AsyncMock()

        try:
            from src.grpc.generated import file_manager_pb2
        except ImportError:
            pytest.skip("gRPC generated modules not available")

        request = file_manager_pb2.ExtractRequest(
            file_path="user123/doc123/test.pdf",
            force=True,
        )

        response = await servicer.Extract(request, context)

        # Should not use cache
        assert response.result is not None


# ============================================================================
# Thumbnail Tests
# ============================================================================


@pytest.mark.grpc
@pytest.mark.asyncio
class TestServicerThumbnail:
    """Test servicer thumbnail operations."""

    @pytest.fixture
    def servicer(self, mock_minio_client, mock_redis_client, sample_image_bytes):
        """Create servicer with mocked clients."""
        try:
            from src.grpc.servicer import FileManagerServicer
        except ImportError:
            pytest.skip("gRPC modules not available")

        # Configure minio to return sample image
        mock_response = MagicMock()
        mock_response.read.return_value = sample_image_bytes
        mock_response.close = MagicMock()
        mock_minio_client.get_object.return_value = mock_response
        mock_minio_client.download_file.return_value = sample_image_bytes
        mock_minio_client.bucket = "documents"

        servicer = FileManagerServicer()
        servicer.minio = mock_minio_client
        servicer.redis = mock_redis_client
        return servicer

    async def test_generate_thumbnail_success(self, servicer):
        """Test thumbnail generation success."""
        context = AsyncMock()

        try:
            from src.grpc.generated import file_manager_pb2
        except ImportError:
            pytest.skip("gRPC generated modules not available")

        request = file_manager_pb2.ThumbnailRequest(
            file_path="user123/doc123/image.png",
            width=200,
            height=200,
        )

        response = await servicer.GenerateThumbnail(request, context)

        assert response.thumbnail is not None
        assert len(response.thumbnail) > 0
        assert response.content_type in ("image/jpeg", "image/png")

    async def test_generate_thumbnail_custom_size(self, servicer):
        """Test thumbnail with custom dimensions."""
        context = AsyncMock()

        try:
            from src.grpc.generated import file_manager_pb2
        except ImportError:
            pytest.skip("gRPC generated modules not available")

        request = file_manager_pb2.ThumbnailRequest(
            file_path="user123/doc123/image.png",
            width=100,
            height=100,
        )

        response = await servicer.GenerateThumbnail(request, context)

        assert response.thumbnail is not None


# ============================================================================
# Metadata Tests
# ============================================================================


@pytest.mark.grpc
@pytest.mark.asyncio
class TestServicerMetadata:
    """Test servicer metadata operations."""

    @pytest.fixture
    def servicer(self, mock_minio_client, mock_redis_client):
        """Create servicer with mocked clients."""
        try:
            from src.grpc.servicer import FileManagerServicer
        except ImportError:
            pytest.skip("gRPC modules not available")

        servicer = FileManagerServicer()
        servicer.minio = mock_minio_client
        servicer.redis = mock_redis_client
        return servicer

    async def test_get_metadata_success(self, servicer):
        """Test metadata retrieval."""
        context = AsyncMock()

        try:
            from src.grpc.generated import file_manager_pb2
        except ImportError:
            pytest.skip("gRPC generated modules not available")

        request = file_manager_pb2.MetadataRequest(
            file_path="user123/doc123/test.pdf",
            include_extraction=False,
        )

        response = await servicer.GetMetadata(request, context)

        assert response.metadata is not None
        assert response.metadata.size_bytes == 1024
        assert response.metadata.content_type == "application/pdf"


# ============================================================================
# Delete Tests
# ============================================================================


@pytest.mark.grpc
@pytest.mark.asyncio
class TestServicerDelete:
    """Test servicer delete operations."""

    @pytest.fixture
    def servicer(self, mock_minio_client, mock_redis_client):
        """Create servicer with mocked clients."""
        try:
            from src.grpc.servicer import FileManagerServicer
        except ImportError:
            pytest.skip("gRPC modules not available")

        servicer = FileManagerServicer()
        servicer.minio = mock_minio_client
        servicer.redis = mock_redis_client
        return servicer

    async def test_delete_success(self, servicer):
        """Test file deletion."""
        context = AsyncMock()

        try:
            from src.grpc.generated import file_manager_pb2
        except ImportError:
            pytest.skip("gRPC generated modules not available")

        request = file_manager_pb2.DeleteRequest(
            file_path="user123/doc123/test.pdf",
        )

        response = await servicer.Delete(request, context)

        assert response.success is True
        assert "Deleted" in response.message

    async def test_delete_with_cache_cleanup(self, servicer):
        """Test deletion cleans up cache."""
        context = AsyncMock()

        try:
            from src.grpc.generated import file_manager_pb2
        except ImportError:
            pytest.skip("gRPC generated modules not available")

        request = file_manager_pb2.DeleteRequest(
            file_path="user123/doc123/test.pdf",
        )

        await servicer.Delete(request, context)

        # Redis delete should be called for extraction cache
        servicer.redis.delete.assert_called()
