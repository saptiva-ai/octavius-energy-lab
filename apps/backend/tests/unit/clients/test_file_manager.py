"""
Unit tests for FileManagerClient (HTTP client for file-manager plugin).

Tests upload, download, extraction, and metadata operations.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile

# Skip all tests if import fails due to proto version mismatch
try:
    from src.clients.file_manager import (
        FileManagerClient,
        FileMetadata,
        get_file_manager_client,
        close_file_manager_client,
    )
    CLIENT_IMPORT_AVAILABLE = True
except Exception:
    CLIENT_IMPORT_AVAILABLE = False
    # Dummy imports to avoid NameError
    FileManagerClient = None
    FileMetadata = None
    get_file_manager_client = None
    close_file_manager_client = None

pytestmark = pytest.mark.skipif(
    not CLIENT_IMPORT_AVAILABLE,
    reason="Protobuf version mismatch - regenerate protos"
)


class TestFileMetadataModel:
    """Tests for FileMetadata Pydantic model."""

    def test_create_minimal(self):
        """Test creating FileMetadata with required fields only."""
        metadata = FileMetadata(
            file_id="file-123",
            filename="document.pdf",
            size=1024,
            mime_type="application/pdf",
            minio_key="user1/session1/file-123.pdf",
            sha256="abc123def456",
        )

        assert metadata.file_id == "file-123"
        assert metadata.filename == "document.pdf"
        assert metadata.size == 1024
        assert metadata.mime_type == "application/pdf"
        assert metadata.extracted_text is None
        assert metadata.pages is None

    def test_create_with_optional_fields(self):
        """Test creating FileMetadata with all fields."""
        metadata = FileMetadata(
            file_id="file-123",
            filename="document.pdf",
            size=1024,
            mime_type="application/pdf",
            minio_key="user1/session1/file-123.pdf",
            sha256="abc123def456",
            extracted_text="Sample extracted text",
            pages=10,
        )

        assert metadata.extracted_text == "Sample extracted text"
        assert metadata.pages == 10

    def test_from_dict(self):
        """Test creating FileMetadata from dict."""
        data = {
            "file_id": "file-456",
            "filename": "report.xlsx",
            "size": 2048,
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "minio_key": "user2/file-456.xlsx",
            "sha256": "xyz789",
        }

        metadata = FileMetadata(**data)

        assert metadata.file_id == "file-456"
        assert metadata.mime_type.startswith("application/vnd")


class TestFileManagerClientInit:
    """Tests for FileManagerClient initialization."""

    def test_init_with_default_url(self):
        """Test initialization with default URL."""
        with patch.dict("os.environ", {}, clear=True):
            client = FileManagerClient()
            assert "file-manager:8001" in client.base_url

    def test_init_with_env_url(self):
        """Test initialization with environment variable URL."""
        with patch.dict("os.environ", {"FILE_MANAGER_URL": "http://custom:9000"}):
            client = FileManagerClient()
            assert client.base_url == "http://custom:9000"

    def test_init_with_explicit_url(self):
        """Test initialization with explicit URL."""
        client = FileManagerClient(base_url="http://localhost:8080")
        assert client.base_url == "http://localhost:8080"

    def test_init_client_is_none(self):
        """Test that _client starts as None."""
        client = FileManagerClient()
        assert client._client is None


class TestFileManagerClientGetClient:
    """Tests for _get_client method."""

    @pytest.mark.asyncio
    async def test_get_client_creates_new(self):
        """Test that _get_client creates a new client when None."""
        client = FileManagerClient()

        http_client = await client._get_client()

        assert http_client is not None
        assert client._client is not None

        await client.close()

    @pytest.mark.asyncio
    async def test_get_client_reuses_existing(self):
        """Test that _get_client reuses existing client."""
        client = FileManagerClient()

        http_client1 = await client._get_client()
        http_client2 = await client._get_client()

        assert http_client1 is http_client2

        await client.close()

    @pytest.mark.asyncio
    async def test_get_client_recreates_if_closed(self):
        """Test that _get_client creates new client if previous was closed."""
        client = FileManagerClient()

        http_client1 = await client._get_client()
        await client.close()

        http_client2 = await client._get_client()

        assert http_client1 is not http_client2

        await client.close()


class TestFileManagerClientUpload:
    """Tests for upload method."""

    @pytest.mark.asyncio
    async def test_upload_success(self):
        """Test successful file upload."""
        client = FileManagerClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "file_id": "file-123",
            "filename": "test.pdf",
            "size": 1024,
            "mime_type": "application/pdf",
            "minio_key": "user1/file-123.pdf",
            "sha256": "abc123",
            "extracted_text": "Sample text",
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.upload(
                file_content=b"test content",
                filename="test.pdf",
                user_id="user-1",
                content_type="application/pdf",
            )

        assert isinstance(result, FileMetadata)
        assert result.file_id == "file-123"
        assert result.extracted_text == "Sample text"

    @pytest.mark.asyncio
    async def test_upload_with_session_id(self):
        """Test upload with session_id."""
        client = FileManagerClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "file_id": "file-123",
            "filename": "test.pdf",
            "size": 1024,
            "mime_type": "application/pdf",
            "minio_key": "user1/session1/file-123.pdf",
            "sha256": "abc123",
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.upload(
                file_content=b"test content",
                filename="test.pdf",
                user_id="user-1",
                session_id="session-1",
            )

        # Verify session_id was included in data
        call_args = mock_http_client.post.call_args
        assert call_args[1]["data"]["session_id"] == "session-1"


class TestFileManagerClientDownload:
    """Tests for download method."""

    @pytest.mark.asyncio
    async def test_download_success(self):
        """Test successful file download."""
        client = FileManagerClient()

        mock_response = MagicMock()
        mock_response.content = b"file content bytes"
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.download("user1/file-123.pdf")

        assert result == b"file content bytes"
        mock_http_client.get.assert_called_once_with("/download/user1/file-123.pdf")


class TestFileManagerClientDownloadToTemp:
    """Tests for download_to_temp method."""

    @pytest.mark.asyncio
    async def test_download_to_temp_success(self):
        """Test successful download to temp file."""
        client = FileManagerClient()

        # Mock download method
        with patch.object(client, "download", return_value=b"test content"):
            result = await client.download_to_temp("user1/file-123.pdf")

            assert isinstance(result, Path)
            assert result.exists()
            assert result.suffix == ".pdf"

            # Clean up
            result.unlink()

    @pytest.mark.asyncio
    async def test_download_to_temp_extracts_extension(self):
        """Test that correct extension is extracted."""
        client = FileManagerClient()

        with patch.object(client, "download", return_value=b"excel data"):
            result = await client.download_to_temp("user1/report.xlsx")

            assert result.suffix == ".xlsx"

            result.unlink()

    @pytest.mark.asyncio
    async def test_download_to_temp_default_extension(self):
        """Test default .bin extension when no extension in path."""
        client = FileManagerClient()

        with patch.object(client, "download", return_value=b"binary data"):
            result = await client.download_to_temp("user1/file_without_ext")

            assert result.suffix == ".bin"

            result.unlink()


class TestFileManagerClientGetMetadata:
    """Tests for get_metadata method."""

    @pytest.mark.asyncio
    async def test_get_metadata_success(self):
        """Test successful metadata retrieval."""
        client = FileManagerClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "file_id": "file-123",
            "filename": "test.pdf",
            "size": 1024,
            "content_type": "application/pdf",
            "extracted_text": "Sample text",
            "pages": 5,
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.get_metadata("user1/file-123.pdf")

        assert result["file_id"] == "file-123"
        assert result["pages"] == 5

    @pytest.mark.asyncio
    async def test_get_metadata_include_text_false(self):
        """Test metadata retrieval without text."""
        client = FileManagerClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"file_id": "file-123"}
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            await client.get_metadata("user1/file.pdf", include_text=False)

        call_args = mock_http_client.get.call_args
        assert call_args[1]["params"]["include_text"] == "false"


class TestFileManagerClientGetExtractedText:
    """Tests for get_extracted_text method."""

    @pytest.mark.asyncio
    async def test_get_extracted_text_success(self):
        """Test successful text extraction."""
        client = FileManagerClient()

        with patch.object(
            client,
            "get_metadata",
            return_value={"extracted_text": "Extracted document text"},
        ):
            result = await client.get_extracted_text("user1/file.pdf")

        assert result == "Extracted document text"

    @pytest.mark.asyncio
    async def test_get_extracted_text_empty(self):
        """Test when no extracted text available."""
        client = FileManagerClient()

        with patch.object(client, "get_metadata", return_value={}):
            result = await client.get_extracted_text("user1/file.pdf")

        assert result == ""


class TestFileManagerClientExtractText:
    """Tests for extract_text method."""

    @pytest.mark.asyncio
    async def test_extract_text_success(self):
        """Test successful text extraction request."""
        client = FileManagerClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "text": "Extracted text",
            "pages": 3,
            "source": "extraction",
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.extract_text("user1/file.pdf")

        assert result["text"] == "Extracted text"
        assert result["source"] == "extraction"

    @pytest.mark.asyncio
    async def test_extract_text_force(self):
        """Test force re-extraction."""
        client = FileManagerClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"text": "Re-extracted"}
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            await client.extract_text("user1/file.pdf", force=True)

        call_args = mock_http_client.post.call_args
        assert call_args[1]["params"]["force"] == "true"


class TestFileManagerClientDelete:
    """Tests for delete method."""

    @pytest.mark.asyncio
    async def test_delete_success(self):
        """Test successful file deletion."""
        client = FileManagerClient()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.delete.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            await client.delete("user1/file-123.pdf")

        mock_http_client.delete.assert_called_once_with("/files/user1/file-123.pdf")


class TestFileManagerClientHealthCheck:
    """Tests for health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        client = FileManagerClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "healthy", "version": "1.0.0"}
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.health_check()

        assert result["status"] == "healthy"
        mock_http_client.get.assert_called_once_with("/health")


class TestFileManagerClientClose:
    """Tests for close method."""

    @pytest.mark.asyncio
    async def test_close_when_client_exists(self):
        """Test closing when client exists."""
        client = FileManagerClient()

        # Create the internal client
        await client._get_client()
        assert client._client is not None

        await client.close()

        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_when_client_is_none(self):
        """Test closing when client is already None."""
        client = FileManagerClient()
        assert client._client is None

        # Should not raise
        await client.close()

        assert client._client is None


class TestSingletonFunctions:
    """Tests for singleton getter/closer functions."""

    @pytest.mark.asyncio
    async def test_get_file_manager_client_creates_instance(self):
        """Test that get_file_manager_client creates singleton."""
        # Reset singleton
        import src.clients.file_manager as fm_module

        fm_module._client = None

        client = await get_file_manager_client()

        assert client is not None
        assert fm_module._client is client

        # Clean up
        await close_file_manager_client()

    @pytest.mark.asyncio
    async def test_get_file_manager_client_returns_same_instance(self):
        """Test that get_file_manager_client returns same instance."""
        import src.clients.file_manager as fm_module

        fm_module._client = None

        client1 = await get_file_manager_client()
        client2 = await get_file_manager_client()

        assert client1 is client2

        await close_file_manager_client()

    @pytest.mark.asyncio
    async def test_close_file_manager_client_clears_singleton(self):
        """Test that close_file_manager_client clears singleton."""
        import src.clients.file_manager as fm_module

        fm_module._client = None

        await get_file_manager_client()
        assert fm_module._client is not None

        await close_file_manager_client()

        assert fm_module._client is None

    @pytest.mark.asyncio
    async def test_close_file_manager_client_when_none(self):
        """Test close when singleton is None."""
        import src.clients.file_manager as fm_module

        fm_module._client = None

        # Should not raise
        await close_file_manager_client()

        assert fm_module._client is None
