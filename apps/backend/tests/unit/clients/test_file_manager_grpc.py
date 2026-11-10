"""
Unit tests for FileManagerGrpcClient.

Tests gRPC client functionality with mocked proto modules.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os


class TestDataclasses:
    """Test dataclass definitions."""

    def test_extraction_result(self):
        """Test ExtractionResult dataclass."""
        from src.clients.file_manager_grpc import ExtractionResult, PageContent

        pages = [PageContent(page=1, text="Hello")]
        result = ExtractionResult(
            file_id="file123",
            pages=pages,
            total_pages=1,
            ocr_applied=True,
            source="rust",
            processing_time_ms=500,
            rust_version="1.0.0",
        )

        assert result.file_id == "file123"
        assert len(result.pages) == 1
        assert result.total_pages == 1
        assert result.ocr_applied is True
        assert result.source == "rust"
        assert result.processing_time_ms == 500
        assert result.rust_version == "1.0.0"

    def test_page_content(self):
        """Test PageContent dataclass."""
        from src.clients.file_manager_grpc import PageContent

        page = PageContent(
            page=1,
            text="Sample text",
            has_table=True,
            has_images=True,
            quality_ratio=0.95,
            ocr_applied=False,
        )

        assert page.page == 1
        assert page.text == "Sample text"
        assert page.has_table is True
        assert page.has_images is True
        assert page.quality_ratio == 0.95
        assert page.ocr_applied is False

    def test_page_content_defaults(self):
        """Test PageContent default values."""
        from src.clients.file_manager_grpc import PageContent

        page = PageContent(page=1, text="text")

        assert page.has_table is False
        assert page.has_images is False
        assert page.quality_ratio == 0.0
        assert page.ocr_applied is False

    def test_thumbnail_result(self):
        """Test ThumbnailResult dataclass."""
        from src.clients.file_manager_grpc import ThumbnailResult

        result = ThumbnailResult(
            data=b"image_data",
            content_type="image/jpeg",
            width=200,
            height=150,
            original_width=800,
            original_height=600,
            processing_time_ms=50,
        )

        assert result.data == b"image_data"
        assert result.content_type == "image/jpeg"
        assert result.width == 200
        assert result.height == 150
        assert result.original_width == 800
        assert result.original_height == 600
        assert result.processing_time_ms == 50

    def test_file_metadata(self):
        """Test FileMetadata dataclass."""
        from src.clients.file_manager_grpc import FileMetadata

        meta = FileMetadata(
            file_id="file123",
            filename="test.pdf",
            size=1024,
            content_type="application/pdf",
            minio_key="users/123/test.pdf",
            sha256="abc123",
            last_modified="2025-01-01T00:00:00Z",
        )

        assert meta.file_id == "file123"
        assert meta.filename == "test.pdf"
        assert meta.size == 1024
        assert meta.content_type == "application/pdf"
        assert meta.minio_key == "users/123/test.pdf"
        assert meta.sha256 == "abc123"

    def test_file_metadata_defaults(self):
        """Test FileMetadata default values."""
        from src.clients.file_manager_grpc import FileMetadata

        meta = FileMetadata(
            file_id="file123",
            filename="test.pdf",
            size=1024,
            content_type="application/pdf",
            minio_key="key",
        )

        assert meta.sha256 == ""
        assert meta.last_modified == ""


class TestFileManagerGrpcClientInit:
    """Test FileManagerGrpcClient initialization."""

    def test_init_defaults(self):
        """Test initialization with defaults."""
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        with patch.dict(os.environ, {}, clear=True):
            client = FileManagerGrpcClient()

        assert client.host == "file-manager"
        assert client.port == 50052
        assert client.max_message_size == 100 * 1024 * 1024
        assert client._channel is None
        assert client._stub is None

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        client = FileManagerGrpcClient(
            host="localhost",
            port=9999,
            max_message_size=50 * 1024 * 1024,
        )

        assert client.host == "localhost"
        assert client.port == 9999
        assert client.max_message_size == 50 * 1024 * 1024

    def test_init_from_env_vars(self):
        """Test initialization from environment variables."""
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        with patch.dict(
            os.environ,
            {
                "FILE_MANAGER_GRPC_HOST": "grpc-server",
                "FILE_MANAGER_GRPC_PORT": "8080",
            },
        ):
            client = FileManagerGrpcClient()

        assert client.host == "grpc-server"
        assert client.port == 8080


class TestFileManagerGrpcClientGetChannel:
    """Test _get_channel method."""

    @pytest.fixture
    def client(self):
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        return FileManagerGrpcClient(host="localhost", port=50052)

    @pytest.mark.asyncio
    async def test_get_channel_creates_channel(self, client):
        """Test _get_channel creates channel."""
        mock_channel = MagicMock()

        with patch("grpc.aio.insecure_channel", return_value=mock_channel) as mock_create:
            channel = await client._get_channel()

            assert channel == mock_channel
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_channel_reuses_channel(self, client):
        """Test _get_channel reuses existing channel."""
        mock_channel = MagicMock()
        client._channel = mock_channel

        with patch("grpc.aio.insecure_channel") as mock_create:
            channel = await client._get_channel()

            assert channel == mock_channel
            mock_create.assert_not_called()


class TestFileManagerGrpcClientGetStub:
    """Test _get_stub method."""

    @pytest.fixture
    def client(self):
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        return FileManagerGrpcClient()

    @pytest.mark.asyncio
    async def test_get_stub_no_grpc_raises(self, client):
        """Test _get_stub raises when gRPC not available."""
        with patch("src.clients.file_manager_grpc.GRPC_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="gRPC modules not available"):
                await client._get_stub()

    @pytest.mark.asyncio
    async def test_get_stub_creates_stub(self, client):
        """Test _get_stub creates stub."""
        mock_channel = MagicMock()
        mock_stub = MagicMock()

        with patch("src.clients.file_manager_grpc.GRPC_AVAILABLE", True):
            with patch.object(client, "_get_channel", AsyncMock(return_value=mock_channel)):
                with patch("src.clients.file_manager_grpc.file_manager_pb2_grpc") as mock_grpc:
                    mock_grpc.FileManagerServiceStub.return_value = mock_stub

                    stub = await client._get_stub()

                    assert stub == mock_stub

    @pytest.mark.asyncio
    async def test_get_stub_reuses_stub(self, client):
        """Test _get_stub reuses existing stub."""
        mock_stub = MagicMock()
        client._stub = mock_stub

        with patch("src.clients.file_manager_grpc.GRPC_AVAILABLE", True):
            stub = await client._get_stub()

            assert stub == mock_stub


class TestFileManagerGrpcClientHealthCheck:
    """Test health_check method."""

    @pytest.fixture
    def client(self):
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        return FileManagerGrpcClient()

    @pytest.mark.asyncio
    async def test_health_check_success(self, client):
        """Test successful health check."""
        mock_response = MagicMock()
        mock_response.status = "healthy"
        mock_response.dependencies = {"minio": "ok", "redis": "ok"}
        mock_response.rust_available = True
        mock_response.rust_module_version = "1.0.0"
        mock_response.capabilities = {"extract": "true", "thumbnail": "true"}

        mock_stub = MagicMock()
        mock_stub.Health = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.file_manager_grpc.file_manager_pb2") as mock_pb2:
                mock_pb2.HealthRequest.return_value = MagicMock()

                result = await client.health_check()

                assert result["status"] == "healthy"
                assert result["rust_available"] is True
                assert result["rust_module_version"] == "1.0.0"


class TestFileManagerGrpcClientUpload:
    """Test upload method."""

    @pytest.fixture
    def client(self):
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        return FileManagerGrpcClient()

    @pytest.mark.asyncio
    async def test_upload_success_no_extraction(self, client):
        """Test successful upload without extraction."""
        mock_metadata = MagicMock()
        mock_metadata.filename = "test.txt"
        mock_metadata.size = 100
        mock_metadata.content_type = "text/plain"
        mock_metadata.minio_key = "users/123/test.txt"
        mock_metadata.sha256 = "abc123"

        mock_response = MagicMock()
        mock_response.file_id = "file123"
        mock_response.metadata = mock_metadata
        mock_response.HasField.return_value = False  # No extraction

        mock_stub = MagicMock()
        mock_stub.UploadSimple = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.file_manager_grpc.file_manager_pb2") as mock_pb2:
                mock_pb2.UploadRequest.return_value = MagicMock()
                mock_pb2.UploadSimpleRequest.return_value = MagicMock()

                file_meta, extraction = await client.upload(
                    file_data=b"test data",
                    user_id="user123",
                    filename="test.txt",
                )

                assert file_meta.file_id == "file123"
                assert file_meta.filename == "test.txt"
                assert extraction is None


class TestFileManagerGrpcClientDownload:
    """Test download method."""

    @pytest.fixture
    def client(self):
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        return FileManagerGrpcClient()

    @pytest.mark.asyncio
    async def test_download_success(self, client):
        """Test successful download."""
        chunk1 = MagicMock()
        chunk1.data = b"chunk1"
        chunk2 = MagicMock()
        chunk2.data = b"chunk2"

        response1 = MagicMock()
        response1.HasField.return_value = True
        response1.chunk = chunk1

        response2 = MagicMock()
        response2.HasField.return_value = True
        response2.chunk = chunk2

        async def mock_stream(*args):
            yield response1
            yield response2

        mock_stub = MagicMock()
        mock_stub.Download = mock_stream

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.file_manager_grpc.file_manager_pb2") as mock_pb2:
                mock_pb2.DownloadRequest.return_value = MagicMock()

                content = await client.download("path/to/file.pdf")

                assert content == b"chunk1chunk2"


class TestFileManagerGrpcClientDownloadStream:
    """Test download_stream method."""

    @pytest.fixture
    def client(self):
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        return FileManagerGrpcClient()

    @pytest.mark.asyncio
    async def test_download_stream_success(self, client):
        """Test successful download stream."""
        chunk = MagicMock()
        chunk.data = b"data"

        response = MagicMock()
        response.HasField.return_value = True
        response.chunk = chunk

        async def mock_stream(*args):
            yield response

        mock_stub = MagicMock()
        mock_stub.Download = mock_stream

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.file_manager_grpc.file_manager_pb2") as mock_pb2:
                mock_pb2.DownloadRequest.return_value = MagicMock()

                chunks = []
                async for chunk_data in client.download_stream("file.pdf"):
                    chunks.append(chunk_data)

                assert chunks == [b"data"]


class TestFileManagerGrpcClientExtract:
    """Test extract method."""

    @pytest.fixture
    def client(self):
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        return FileManagerGrpcClient()

    @pytest.mark.asyncio
    async def test_extract_success(self, client):
        """Test successful extraction."""
        mock_page = MagicMock()
        mock_page.page = 1
        mock_page.text_md = "Page 1 content"
        mock_page.has_table = False
        mock_page.has_images = True
        mock_page.quality_ratio = 0.9
        mock_page.ocr_applied = False

        mock_result = MagicMock()
        mock_result.file_id = "file123"
        mock_result.pages = [mock_page]
        mock_result.total_pages = 1
        mock_result.ocr_applied = False
        mock_result.source = "rust"
        mock_result.processing_time_ms = 200
        mock_result.rust_version = "1.0.0"

        mock_response = MagicMock()
        mock_response.result = mock_result

        mock_stub = MagicMock()
        mock_stub.Extract = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.file_manager_grpc.file_manager_pb2") as mock_pb2:
                mock_pb2.ExtractRequest.return_value = MagicMock()

                result = await client.extract("path/to/file.pdf")

                assert result.file_id == "file123"
                assert result.total_pages == 1
                assert result.source == "rust"
                assert len(result.pages) == 1
                assert result.pages[0].text == "Page 1 content"


class TestFileManagerGrpcClientBatchExtract:
    """Test batch_extract method."""

    @pytest.fixture
    def client(self):
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        return FileManagerGrpcClient()

    @pytest.mark.asyncio
    async def test_batch_extract_success(self, client):
        """Test successful batch extraction."""
        mock_result = MagicMock()
        mock_result.file_id = "file123"
        mock_result.pages = []
        mock_result.total_pages = 0
        mock_result.ocr_applied = False
        mock_result.source = "python"
        mock_result.processing_time_ms = 100
        mock_result.rust_version = ""

        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_response.failed_paths = ["failed.pdf"]
        mock_response.total_processing_time_ms = 100

        mock_stub = MagicMock()
        mock_stub.BatchExtract = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.file_manager_grpc.file_manager_pb2") as mock_pb2:
                mock_pb2.BatchExtractRequest.return_value = MagicMock()

                results, failed = await client.batch_extract(
                    ["file1.pdf", "failed.pdf"]
                )

                assert len(results) == 1
                assert failed == ["failed.pdf"]


class TestFileManagerGrpcClientGenerateThumbnail:
    """Test generate_thumbnail method."""

    @pytest.fixture
    def client(self):
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        return FileManagerGrpcClient()

    @pytest.mark.asyncio
    async def test_generate_thumbnail_success(self, client):
        """Test successful thumbnail generation."""
        mock_response = MagicMock()
        mock_response.thumbnail = b"image_data"
        mock_response.content_type = "image/jpeg"
        mock_response.width = 200
        mock_response.height = 150
        mock_response.original_width = 800
        mock_response.original_height = 600
        mock_response.processing_time_ms = 50

        mock_stub = MagicMock()
        mock_stub.GenerateThumbnail = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.file_manager_grpc.file_manager_pb2") as mock_pb2:
                mock_pb2.ThumbnailRequest.return_value = MagicMock()

                result = await client.generate_thumbnail(
                    file_path="image.jpg",
                    width=200,
                    height=150,
                )

                assert result.data == b"image_data"
                assert result.content_type == "image/jpeg"
                assert result.width == 200
                assert result.height == 150


class TestFileManagerGrpcClientGetMetadata:
    """Test get_metadata method."""

    @pytest.fixture
    def client(self):
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        return FileManagerGrpcClient()

    @pytest.mark.asyncio
    async def test_get_metadata_success(self, client):
        """Test successful get_metadata."""
        mock_meta = MagicMock()
        mock_meta.file_id = "file123"
        mock_meta.filename = "test.pdf"
        mock_meta.size = 1024
        mock_meta.content_type = "application/pdf"
        mock_meta.minio_key = "key"
        mock_meta.sha256 = "hash"
        mock_meta.last_modified = "2025-01-01"

        mock_response = MagicMock()
        mock_response.metadata = mock_meta
        mock_response.HasField.return_value = False  # No extraction

        mock_stub = MagicMock()
        mock_stub.GetMetadata = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.file_manager_grpc.file_manager_pb2") as mock_pb2:
                mock_pb2.MetadataRequest.return_value = MagicMock()

                metadata, extraction = await client.get_metadata("file.pdf")

                assert metadata.file_id == "file123"
                assert metadata.filename == "test.pdf"
                assert extraction is None


class TestFileManagerGrpcClientDelete:
    """Test delete method."""

    @pytest.fixture
    def client(self):
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        return FileManagerGrpcClient()

    @pytest.mark.asyncio
    async def test_delete_success(self, client):
        """Test successful delete."""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.deleted_keys = ["file.pdf", "file.pdf.thumb"]

        mock_stub = MagicMock()
        mock_stub.Delete = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.file_manager_grpc.file_manager_pb2") as mock_pb2:
                mock_pb2.DeleteRequest.return_value = MagicMock()

                result = await client.delete("file.pdf")

                assert result is True


class TestFileManagerGrpcClientClose:
    """Test close method."""

    @pytest.fixture
    def client(self):
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        return FileManagerGrpcClient()

    @pytest.mark.asyncio
    async def test_close_with_channel(self, client):
        """Test close with existing channel."""
        mock_channel = MagicMock()
        mock_channel.close = AsyncMock()

        client._channel = mock_channel
        client._stub = MagicMock()

        await client.close()

        mock_channel.close.assert_called_once()
        assert client._channel is None
        assert client._stub is None

    @pytest.mark.asyncio
    async def test_close_without_channel(self, client):
        """Test close without channel."""
        await client.close()  # Should not raise


class TestConvertExtractionResult:
    """Test _convert_extraction_result helper."""

    @pytest.fixture
    def client(self):
        from src.clients.file_manager_grpc import FileManagerGrpcClient

        return FileManagerGrpcClient()

    def test_convert_extraction_result(self, client):
        """Test conversion of proto result to dataclass."""
        mock_page = MagicMock()
        mock_page.page = 1
        mock_page.text_md = "Text content"
        mock_page.has_table = True
        mock_page.has_images = False
        mock_page.quality_ratio = 0.85
        mock_page.ocr_applied = True

        mock_proto = MagicMock()
        mock_proto.file_id = "file123"
        mock_proto.pages = [mock_page]
        mock_proto.total_pages = 1
        mock_proto.ocr_applied = True
        mock_proto.source = "ocr"
        mock_proto.processing_time_ms = 500
        mock_proto.rust_version = "1.0.0"

        result = client._convert_extraction_result(mock_proto)

        assert result.file_id == "file123"
        assert result.total_pages == 1
        assert result.ocr_applied is True
        assert result.source == "ocr"
        assert len(result.pages) == 1
        assert result.pages[0].text == "Text content"
        assert result.pages[0].has_table is True

    def test_convert_extraction_result_empty_rust_version(self, client):
        """Test conversion with empty rust_version."""
        mock_proto = MagicMock()
        mock_proto.file_id = "file123"
        mock_proto.pages = []
        mock_proto.total_pages = 0
        mock_proto.ocr_applied = False
        mock_proto.source = "python"
        mock_proto.processing_time_ms = 100
        mock_proto.rust_version = ""

        result = client._convert_extraction_result(mock_proto)

        assert result.rust_version is None


class TestSingletonFunctions:
    """Test singleton accessor functions."""

    @pytest.mark.asyncio
    async def test_get_file_manager_grpc_client_no_grpc(self):
        """Test get_file_manager_grpc_client raises when gRPC unavailable."""
        import src.clients.file_manager_grpc as module

        with patch.object(module, "GRPC_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="gRPC modules not available"):
                await module.get_file_manager_grpc_client()

    @pytest.mark.asyncio
    async def test_get_file_manager_grpc_client_creates_singleton(self):
        """Test get_file_manager_grpc_client creates singleton."""
        import src.clients.file_manager_grpc as module

        original = module._grpc_client
        module._grpc_client = None

        try:
            with patch.object(module, "GRPC_AVAILABLE", True):
                client1 = await module.get_file_manager_grpc_client()
                client2 = await module.get_file_manager_grpc_client()

                assert client1 is client2
        finally:
            module._grpc_client = original

    @pytest.mark.asyncio
    async def test_close_file_manager_grpc_client(self):
        """Test close_file_manager_grpc_client."""
        import src.clients.file_manager_grpc as module

        mock_client = MagicMock()
        mock_client.close = AsyncMock()

        original = module._grpc_client
        module._grpc_client = mock_client

        try:
            await module.close_file_manager_grpc_client()

            mock_client.close.assert_called_once()
            assert module._grpc_client is None
        finally:
            module._grpc_client = original


class TestIsGrpcAvailable:
    """Test is_grpc_available function."""

    def test_is_grpc_available(self):
        """Test is_grpc_available returns module constant."""
        from src.clients.file_manager_grpc import is_grpc_available, GRPC_AVAILABLE

        result = is_grpc_available()
        assert result == GRPC_AVAILABLE
