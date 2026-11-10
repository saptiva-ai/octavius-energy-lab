"""
Unit tests for EmbeddingServiceGrpcClient.

Tests gRPC client functionality with mocked proto modules.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os

# Skip all tests if proto import fails due to version mismatch
try:
    from src.clients.embedding_service_grpc import EmbeddedChunk
    GRPC_IMPORT_AVAILABLE = True
except Exception:
    GRPC_IMPORT_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not GRPC_IMPORT_AVAILABLE,
    reason="gRPC proto modules have version mismatch - regenerate protos"
)


class TestEmbeddedChunk:
    """Test EmbeddedChunk dataclass."""

    def test_embedded_chunk_creation(self):
        """Test EmbeddedChunk creation."""
        from src.clients.embedding_service_grpc import EmbeddedChunk

        chunk = EmbeddedChunk(
            chunk_id=1,
            text="Hello world",
            embedding=[0.1, 0.2, 0.3],
            page=2,
            metadata={"key": "value"},
        )

        assert chunk.chunk_id == 1
        assert chunk.text == "Hello world"
        assert chunk.embedding == [0.1, 0.2, 0.3]
        assert chunk.page == 2
        assert chunk.metadata == {"key": "value"}

    def test_embedded_chunk_defaults(self):
        """Test EmbeddedChunk default values."""
        from src.clients.embedding_service_grpc import EmbeddedChunk

        chunk = EmbeddedChunk(
            chunk_id=0,
            text="test",
            embedding=[],
        )

        assert chunk.page == 0
        assert chunk.metadata == {}


class TestModelInfo:
    """Test ModelInfo dataclass."""

    def test_model_info_creation(self):
        """Test ModelInfo creation."""
        from src.clients.embedding_service_grpc import ModelInfo

        info = ModelInfo(
            model_name="text-embedding-3-small",
            dimension=1536,
            device="cuda",
            chunk_size_tokens=512,
            chunk_overlap_tokens=50,
            cache_size=1000,
            cache_used=500,
        )

        assert info.model_name == "text-embedding-3-small"
        assert info.dimension == 1536
        assert info.device == "cuda"
        assert info.chunk_size_tokens == 512
        assert info.chunk_overlap_tokens == 50
        assert info.cache_size == 1000
        assert info.cache_used == 500

    def test_model_info_default_cache_used(self):
        """Test ModelInfo default cache_used."""
        from src.clients.embedding_service_grpc import ModelInfo

        info = ModelInfo(
            model_name="test",
            dimension=768,
            device="cpu",
            chunk_size_tokens=256,
            chunk_overlap_tokens=25,
            cache_size=100,
        )

        assert info.cache_used == 0


class TestEmbeddingServiceGrpcClientInit:
    """Test EmbeddingServiceGrpcClient initialization."""

    def test_init_defaults(self):
        """Test initialization with defaults."""
        from src.clients.embedding_service_grpc import EmbeddingServiceGrpcClient

        with patch.dict(os.environ, {}, clear=True):
            client = EmbeddingServiceGrpcClient()

        assert client.host == "embedding-service"
        assert client.port == 50053
        assert client._channel is None
        assert client._stub is None

    def test_init_with_custom_host_port(self):
        """Test initialization with custom host and port."""
        from src.clients.embedding_service_grpc import EmbeddingServiceGrpcClient

        client = EmbeddingServiceGrpcClient(host="localhost", port=9999)

        assert client.host == "localhost"
        assert client.port == 9999

    def test_init_from_env_vars(self):
        """Test initialization from environment variables."""
        from src.clients.embedding_service_grpc import EmbeddingServiceGrpcClient

        with patch.dict(
            os.environ,
            {
                "EMBEDDING_SERVICE_GRPC_HOST": "custom-host",
                "EMBEDDING_SERVICE_GRPC_PORT": "12345",
            },
        ):
            client = EmbeddingServiceGrpcClient()

        assert client.host == "custom-host"
        assert client.port == 12345


class TestEmbeddingServiceGrpcClientGetStub:
    """Test _get_stub method."""

    @pytest.fixture
    def client(self):
        """Create client for testing."""
        from src.clients.embedding_service_grpc import EmbeddingServiceGrpcClient

        return EmbeddingServiceGrpcClient(host="localhost", port=50053)

    @pytest.mark.asyncio
    async def test_get_stub_no_grpc_raises(self, client):
        """Test _get_stub raises when gRPC not available."""
        with patch("src.clients.embedding_service_grpc.GRPC_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="gRPC modules not available"):
                await client._get_stub()

    @pytest.mark.asyncio
    async def test_get_stub_creates_channel(self, client):
        """Test _get_stub creates channel when needed."""
        mock_channel = MagicMock()
        mock_channel.get_state.return_value = MagicMock()  # Not SHUTDOWN
        mock_stub = MagicMock()

        with patch("src.clients.embedding_service_grpc.GRPC_AVAILABLE", True):
            with patch("grpc.aio.insecure_channel", return_value=mock_channel):
                with patch(
                    "src.clients.embedding_service_grpc.embedding_service_pb2_grpc"
                ) as mock_grpc:
                    mock_grpc.EmbeddingServiceStub.return_value = mock_stub

                    stub = await client._get_stub()

                    assert stub == mock_stub
                    assert client._channel == mock_channel

    @pytest.mark.asyncio
    async def test_get_stub_reuses_channel(self, client):
        """Test _get_stub reuses existing channel."""
        mock_channel = MagicMock()
        mock_channel.get_state.return_value = MagicMock()  # Not SHUTDOWN
        mock_stub = MagicMock()

        client._channel = mock_channel
        client._stub = mock_stub

        with patch("src.clients.embedding_service_grpc.GRPC_AVAILABLE", True):
            stub = await client._get_stub()

            assert stub == mock_stub


class TestEmbeddingServiceGrpcClientHealthCheck:
    """Test health_check method."""

    @pytest.fixture
    def client(self):
        from src.clients.embedding_service_grpc import EmbeddingServiceGrpcClient

        return EmbeddingServiceGrpcClient()

    @pytest.mark.asyncio
    async def test_health_check_success(self, client):
        """Test successful health check."""
        mock_response = MagicMock()
        mock_response.status = "ok"
        mock_response.model_loaded = True
        mock_response.model_name = "test-model"
        mock_response.dimension = 768
        mock_response.model_load_time_ms = 1500

        mock_stub = MagicMock()
        mock_stub.Health = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.embedding_service_grpc.embedding_service_pb2") as mock_pb2:
                mock_pb2.HealthRequest.return_value = MagicMock()

                result = await client.health_check()

                assert result["status"] == "ok"
                assert result["model_loaded"] is True
                assert result["model_name"] == "test-model"
                assert result["dimension"] == 768
                assert result["model_load_time_ms"] == 1500


class TestEmbeddingServiceGrpcClientEncode:
    """Test encode method."""

    @pytest.fixture
    def client(self):
        from src.clients.embedding_service_grpc import EmbeddingServiceGrpcClient

        return EmbeddingServiceGrpcClient()

    @pytest.mark.asyncio
    async def test_encode_empty_list(self, client):
        """Test encode with empty list returns empty."""
        result = await client.encode([])
        assert result == []

    @pytest.mark.asyncio
    async def test_encode_success(self, client):
        """Test successful encoding."""
        mock_embedding1 = MagicMock()
        mock_embedding1.values = [0.1, 0.2, 0.3]
        mock_embedding2 = MagicMock()
        mock_embedding2.values = [0.4, 0.5, 0.6]

        mock_response = MagicMock()
        mock_response.embeddings = [mock_embedding1, mock_embedding2]
        mock_response.dimension = 3
        mock_response.processing_time_ms = 50

        mock_stub = MagicMock()
        mock_stub.Encode = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.embedding_service_grpc.embedding_service_pb2") as mock_pb2:
                mock_pb2.EncodeRequest.return_value = MagicMock()

                result = await client.encode(["text1", "text2"])

                assert len(result) == 2
                assert result[0] == [0.1, 0.2, 0.3]
                assert result[1] == [0.4, 0.5, 0.6]


class TestEmbeddingServiceGrpcClientEncodeSingle:
    """Test encode_single method."""

    @pytest.fixture
    def client(self):
        from src.clients.embedding_service_grpc import EmbeddingServiceGrpcClient

        return EmbeddingServiceGrpcClient()

    @pytest.mark.asyncio
    async def test_encode_single_success(self, client):
        """Test successful single encoding."""
        mock_embedding = MagicMock()
        mock_embedding.values = [0.1, 0.2, 0.3]
        mock_embedding.dimension = 3

        mock_response = MagicMock()
        mock_response.embedding = mock_embedding
        mock_response.cached = False

        mock_stub = MagicMock()
        mock_stub.EncodeSingle = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.embedding_service_grpc.embedding_service_pb2") as mock_pb2:
                mock_pb2.EncodeSingleRequest.return_value = MagicMock()

                result = await client.encode_single("test text")

                assert result == [0.1, 0.2, 0.3]


class TestEmbeddingServiceGrpcClientChunkAndEmbed:
    """Test chunk_and_embed method."""

    @pytest.fixture
    def client(self):
        from src.clients.embedding_service_grpc import EmbeddingServiceGrpcClient

        return EmbeddingServiceGrpcClient()

    @pytest.mark.asyncio
    async def test_chunk_and_embed_empty_text(self, client):
        """Test chunk_and_embed with empty text."""
        result = await client.chunk_and_embed("")
        assert result == []

    @pytest.mark.asyncio
    async def test_chunk_and_embed_whitespace_only(self, client):
        """Test chunk_and_embed with whitespace only."""
        result = await client.chunk_and_embed("   ")
        assert result == []

    @pytest.mark.asyncio
    async def test_chunk_and_embed_success(self, client):
        """Test successful chunk and embed."""
        mock_embedding = MagicMock()
        mock_embedding.values = [0.1, 0.2]

        mock_chunk = MagicMock()
        mock_chunk.chunk_id = 0
        mock_chunk.text = "chunk text"
        mock_chunk.embedding = mock_embedding
        mock_chunk.page = 1
        mock_chunk.metadata = {"key": "value"}

        mock_response = MagicMock()
        mock_response.chunks = [mock_chunk]
        mock_response.total_chunks = 1
        mock_response.dimension = 2
        mock_response.processing_time_ms = 100

        mock_stub = MagicMock()
        mock_stub.ChunkAndEmbed = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.embedding_service_grpc.embedding_service_pb2") as mock_pb2:
                mock_pb2.ChunkAndEmbedRequest.return_value = MagicMock()

                result = await client.chunk_and_embed(
                    "Some text to chunk",
                    page=1,
                    metadata={"source": "test"},
                )

                assert len(result) == 1
                assert result[0]["chunk_id"] == 0
                assert result[0]["text"] == "chunk text"
                assert result[0]["embedding"] == [0.1, 0.2]
                assert result[0]["page"] == 1


class TestEmbeddingServiceGrpcClientBatchChunkAndEmbed:
    """Test batch_chunk_and_embed method."""

    @pytest.fixture
    def client(self):
        from src.clients.embedding_service_grpc import EmbeddingServiceGrpcClient

        return EmbeddingServiceGrpcClient()

    @pytest.mark.asyncio
    async def test_batch_chunk_and_embed_success(self, client):
        """Test successful batch chunk and embed."""
        mock_embedding = MagicMock()
        mock_embedding.values = [0.1, 0.2]

        mock_chunk = MagicMock()
        mock_chunk.chunk_id = 0
        mock_chunk.text = "chunk"
        mock_chunk.embedding = mock_embedding
        mock_chunk.page = 0
        mock_chunk.metadata = {}

        mock_result = MagicMock()
        mock_result.document_id = "doc1"
        mock_result.chunks = [mock_chunk]
        mock_result.success = True
        mock_result.error = ""

        async def mock_stream(*args):
            yield mock_result

        mock_stub = MagicMock()
        mock_stub.BatchChunkAndEmbed = mock_stream

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.embedding_service_grpc.embedding_service_pb2") as mock_pb2:
                mock_pb2.Document.return_value = MagicMock()
                mock_pb2.BatchChunkAndEmbedRequest.return_value = MagicMock()

                documents = [{"id": "doc1", "text": "test text"}]
                results = []
                async for result in client.batch_chunk_and_embed(documents):
                    results.append(result)

                assert len(results) == 1
                assert results[0]["document_id"] == "doc1"
                assert results[0]["success"] is True


class TestEmbeddingServiceGrpcClientGetModelInfo:
    """Test get_model_info method."""

    @pytest.fixture
    def client(self):
        from src.clients.embedding_service_grpc import EmbeddingServiceGrpcClient

        return EmbeddingServiceGrpcClient()

    @pytest.mark.asyncio
    async def test_get_model_info_success(self, client):
        """Test successful get_model_info."""
        from src.clients.embedding_service_grpc import ModelInfo

        mock_response = MagicMock()
        mock_response.model_name = "test-model"
        mock_response.dimension = 768
        mock_response.device = "cuda"
        mock_response.chunk_size_tokens = 512
        mock_response.chunk_overlap_tokens = 50
        mock_response.cache_size = 1000
        mock_response.cache_used = 200

        mock_stub = MagicMock()
        mock_stub.GetModelInfo = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.embedding_service_grpc.embedding_service_pb2") as mock_pb2:
                mock_pb2.ModelInfoRequest.return_value = MagicMock()

                result = await client.get_model_info()

                assert isinstance(result, ModelInfo)
                assert result.model_name == "test-model"
                assert result.dimension == 768
                assert result.device == "cuda"


class TestEmbeddingServiceGrpcClientClearCache:
    """Test clear_cache method."""

    @pytest.fixture
    def client(self):
        from src.clients.embedding_service_grpc import EmbeddingServiceGrpcClient

        return EmbeddingServiceGrpcClient()

    @pytest.mark.asyncio
    async def test_clear_cache_success(self, client):
        """Test successful cache clear."""
        mock_response = MagicMock()
        mock_response.entries_removed = 150

        mock_stub = MagicMock()
        mock_stub.ClearCache = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_stub", AsyncMock(return_value=mock_stub)):
            with patch("src.clients.embedding_service_grpc.embedding_service_pb2") as mock_pb2:
                mock_pb2.ClearCacheRequest.return_value = MagicMock()

                result = await client.clear_cache()

                assert result == 150


class TestEmbeddingServiceGrpcClientClose:
    """Test close method."""

    @pytest.fixture
    def client(self):
        from src.clients.embedding_service_grpc import EmbeddingServiceGrpcClient

        return EmbeddingServiceGrpcClient()

    @pytest.mark.asyncio
    async def test_close_with_channel(self, client):
        """Test close when channel exists."""
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
        """Test close when no channel exists."""
        client._channel = None
        client._stub = None

        # Should not raise
        await client.close()


class TestSingletonFunctions:
    """Test singleton accessor functions."""

    @pytest.mark.asyncio
    async def test_get_embedding_grpc_client(self):
        """Test get_embedding_grpc_client creates singleton."""
        import src.clients.embedding_service_grpc as module

        # Reset singleton
        original = module._grpc_client
        module._grpc_client = None

        try:
            client1 = await module.get_embedding_grpc_client()
            client2 = await module.get_embedding_grpc_client()

            assert client1 is client2
        finally:
            module._grpc_client = original

    @pytest.mark.asyncio
    async def test_close_embedding_grpc_client(self):
        """Test close_embedding_grpc_client closes and clears singleton."""
        import src.clients.embedding_service_grpc as module

        # Create mock client
        mock_client = MagicMock()
        mock_client.close = AsyncMock()

        original = module._grpc_client
        module._grpc_client = mock_client

        try:
            await module.close_embedding_grpc_client()

            mock_client.close.assert_called_once()
            assert module._grpc_client is None
        finally:
            module._grpc_client = original


class TestIsGrpcAvailable:
    """Test is_grpc_available function."""

    def test_is_grpc_available(self):
        """Test is_grpc_available returns correct value."""
        from src.clients.embedding_service_grpc import is_grpc_available, GRPC_AVAILABLE

        result = is_grpc_available()
        assert result == GRPC_AVAILABLE
